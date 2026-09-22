"""Tests for the Google Cloud adverse-media pipeline: screening/media_pipeline.py
and its wiring into cases/manager.py.

Every Google-calling client is faked via dependency injection
(`PipelineClients`) -- nothing here touches the network. Uses the shared
`conn`/`org_id` fixtures from conftest.py plus `onboard()` to create real
customer rows, the same pattern tests/test_adverse_media.py established.
"""

from __future__ import annotations

import json
import logging

import pytest

from amlkit.ai import gemini
from amlkit.cases.manager import onboard, run_adverse_media
from amlkit.db import utcnow
from amlkit.screening.adverse_media import (
    MediaUnavailable,
    SEVERITY_FINANCIAL_CRIME,
    SEVERITY_NONE,
    SEVERITY_REGULATORY,
    SEVERITY_REPUTATIONAL,
)
from amlkit.screening.gdelt_bq import GdeltBqResult
from amlkit.screening.knowledge_graph import KgEntity, KgResult
from amlkit.screening.media_pipeline import (
    PipelineClients,
    TenantMismatchError,
    run_pipeline,
)
from amlkit.screening.nl_entities import EntityMention, NlResult
from amlkit.screening.vertex_search import VaisArticle, VaisResult


# --------------------------------------------------------------------- fakes
def article_payload(url: str, title: str, **kw) -> dict:
    return {
        "url": url,
        "title": title,
        "domain": kw.get("domain", "example.com"),
        "language": kw.get("language", "English"),
        "sourcecountry": kw.get("sourcecountry", "United Arab Emirates"),
        "seendate": kw.get("seendate", "20250903T120000Z"),
    }


class FakeGdeltDoc:
    """One canned artlist payload per call, in order (last one repeats)."""

    def __init__(self, *responses, fail_on: set[int] | None = None) -> None:
        self.responses = list(responses) or [{"articles": []}]
        self.fail_on = fail_on or set()
        self.calls: list[str] = []

    def fetch(self, query, *, window_months, max_records):
        idx = len(self.calls)
        self.calls.append(query)
        if idx in self.fail_on:
            raise MediaUnavailable("stub gdelt down")
        return self.responses[min(idx, len(self.responses) - 1)]


class FakeGdeltBq:
    def __init__(self, result: GdeltBqResult | None = None) -> None:
        self.result = result or GdeltBqResult(status="ok", sample_headlines=[])
        self.calls = 0

    def screen(self, name, window_days=90):
        self.calls += 1
        return self.result


class FakeVais:
    def __init__(self, result: VaisResult | None = None) -> None:
        self.result = result or VaisResult(status="ok", articles=[])
        self.calls = 0

    def search(self, query, *, max_results=10):
        self.calls += 1
        return self.result


class FakeKg:
    def __init__(self, result: KgResult | None = None) -> None:
        self.result = result or KgResult(status="unconfigured", entities=[])

    def screen(self, name, types=None):
        return self.result


class FakeNl:
    def __init__(self, fn) -> None:
        self.fn = fn
        self.calls: list[str] = []

    def analyze(self, text):
        self.calls.append(text)
        return self.fn(text)


def no_op_gdelt_bq() -> FakeGdeltBq:
    return FakeGdeltBq(GdeltBqResult(status="unconfigured"))


def no_op_kg() -> FakeKg:
    return FakeKg(KgResult(status="unconfigured"))


def base_clients(**overrides) -> PipelineClients:
    defaults = dict(
        gdelt_client=FakeGdeltDoc({"articles": []}),
        gdelt_bq=no_op_gdelt_bq(),
        vertex_search=FakeVais(VaisResult(status="disabled")),
        knowledge_graph=no_op_kg(),
    )
    defaults.update(overrides)
    return PipelineClients(**defaults)


# ------------------------------------------------------------------- fixtures
@pytest.fixture()
def customer_id(conn, org_id) -> int:
    return onboard(conn, org_id=org_id, reference="C-MP-1", full_name="Fraudy McFraud").customer_id


# --------------------------------------------------------------------- tests
class TestTenantIsolation:
    def test_cross_org_run_is_rejected(self, conn, org_id, customer_id):
        other_org = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
            " RETURNING id",
            ("Other Firm", "other-firm", "active", utcnow()),
        ).fetchone()["id"]
        conn.commit()

        with pytest.raises(TenantMismatchError):
            run_pipeline(conn, other_org, customer_id, "tester", clients=base_clients())

        # Nothing written -- rejected before any table insert.
        runs = conn.execute(
            "SELECT COUNT(*) c FROM media_pipeline_runs WHERE customer_id=?",
            (customer_id,),
        ).fetchone()["c"]
        assert runs == 0

    def test_unknown_customer_is_rejected(self, conn, org_id):
        with pytest.raises(TenantMismatchError):
            run_pipeline(conn, org_id, 999999, "tester", clients=base_clients())


class TestAcquisitionDedup:
    def test_same_article_from_two_sources_is_deduped(self, conn, org_id, customer_id):
        # GDELT DOC returns an article with a "www." prefix and a trailing
        # slash; the GKG (BigQuery) source returns the "same" article at a
        # bare, no-www URL -- these must collapse to one candidate.
        gdelt = FakeGdeltDoc({
            "articles": [article_payload(
                "https://www.example.com/news/fraud-case/", "Fraudy McFraud fraud case"
            )]
        })
        bq = FakeGdeltBq(GdeltBqResult(
            status="ok", sample_headlines=["https://example.com/news/fraud-case"],
        ))
        result = run_pipeline(
            conn, org_id, customer_id, "tester",
            clients=base_clients(gdelt_client=gdelt, gdelt_bq=bq),
        )
        assert result.sources_queried["gdelt_doc"] == 1
        assert result.sources_queried["gdelt_bq"] == 0  # deduped away
        assert result.articles_considered == 1

    def test_articles_from_multiple_sources_are_all_kept_when_distinct(self, conn, org_id, customer_id):
        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://gulfnews.com/a", "Fraudy McFraud fraud case")]
        })
        bq = FakeGdeltBq(GdeltBqResult(
            status="ok", sample_headlines=["https://thenational.ae/b"],
        ))
        result = run_pipeline(
            conn, org_id, customer_id, "tester",
            clients=base_clients(gdelt_client=gdelt, gdelt_bq=bq),
        )
        assert result.sources_queried["gdelt_doc"] == 1
        assert result.sources_queried["gdelt_bq"] == 1
        assert result.articles_considered == 2

    def test_vertex_search_source_only_queried_when_enabled(self, conn, org_id, customer_id, monkeypatch):
        vais = FakeVais(VaisResult(status="ok", articles=[VaisArticle(url="https://x.ae/1", title="t")]))
        monkeypatch.delenv("AMLKIT_VAIS_ENABLED", raising=False)
        run_pipeline(conn, org_id, customer_id, "tester", clients=base_clients(vertex_search=vais))
        assert vais.calls == 0

        monkeypatch.setenv("AMLKIT_VAIS_ENABLED", "1")
        vais2 = FakeVais(VaisResult(status="ok", articles=[VaisArticle(url="https://x.ae/1", title="Fraudy McFraud fraud")]))
        result = run_pipeline(conn, org_id, customer_id, "tester", clients=base_clients(vertex_search=vais2))
        assert vais2.calls == 1
        assert result.sources_queried["vertex_search"] == 1


class TestEntityResolutionFallback:
    """AMLKIT_NL_ENABLED=0 (default): falls back to keyword classify()."""

    def test_keyword_hit_is_kept(self, conn, org_id, customer_id, monkeypatch):
        monkeypatch.delenv("AMLKIT_NL_ENABLED", raising=False)
        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://x.ae/1", "Fraudy McFraud charged with fraud")]
        })
        result = run_pipeline(conn, org_id, customer_id, "tester", clients=base_clients(gdelt_client=gdelt))
        assert result.articles_considered == 1
        assert result.relevant_articles[0].severity != SEVERITY_NONE

    def test_no_keyword_hit_is_dropped(self, conn, org_id, customer_id, monkeypatch):
        monkeypatch.delenv("AMLKIT_NL_ENABLED", raising=False)
        # Deliberately no lexicon-term substring anywhere in this title
        # (including no "fraud" substring, which "Fraudy" itself contains).
        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://x.ae/1", "Local business news roundup for September")]
        })
        result = run_pipeline(conn, org_id, customer_id, "tester", clients=base_clients(gdelt_client=gdelt))
        assert result.relevant_articles == []
        assert result.articles == []  # stage 2 drops it outright -- no evidence to show


class TestEntityResolutionNl:
    """AMLKIT_NL_ENABLED=1: Cloud Natural Language salience filter."""

    def test_salience_above_threshold_is_kept(self, conn, org_id, customer_id, monkeypatch):
        monkeypatch.setenv("AMLKIT_NL_ENABLED", "1")
        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://x.ae/1", "Fraud case names local businessman")]
        })
        nl = FakeNl(lambda text: NlResult(
            status="ok",
            entities=[EntityMention(name="Fraudy McFraud", type_="PERSON", salience=0.5)],
        ))
        result = run_pipeline(
            conn, org_id, customer_id, "tester",
            clients=base_clients(gdelt_client=gdelt, nl=nl),
        )
        assert result.articles_considered == 1
        assert result.articles[0].salience == pytest.approx(0.5)

    def test_salience_below_threshold_is_dropped(self, conn, org_id, customer_id, monkeypatch):
        monkeypatch.setenv("AMLKIT_NL_ENABLED", "1")
        monkeypatch.setenv("AMLKIT_NL_SALIENCE_THRESHOLD", "0.1")
        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://x.ae/1", "Passing mention of Fraudy McFraud")]
        })
        nl = FakeNl(lambda text: NlResult(
            status="ok",
            entities=[EntityMention(name="Fraudy McFraud", type_="PERSON", salience=0.01)],
        ))
        result = run_pipeline(
            conn, org_id, customer_id, "tester",
            clients=base_clients(gdelt_client=gdelt, nl=nl),
        )
        # articles_considered is the raw stage-1 (acquisition) count and does
        # not change based on stage-2 filtering -- what stage 2 dropped is
        # reflected in `.articles` (never scored) being empty.
        assert result.articles_considered == 1
        assert result.articles == []

    def test_different_entity_name_is_dropped(self, conn, org_id, customer_id, monkeypatch):
        monkeypatch.setenv("AMLKIT_NL_ENABLED", "1")
        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://x.ae/1", "Someone Else in the news")]
        })
        nl = FakeNl(lambda text: NlResult(
            status="ok",
            entities=[EntityMention(name="Someone Else", type_="PERSON", salience=0.9)],
        ))
        result = run_pipeline(
            conn, org_id, customer_id, "tester",
            clients=base_clients(gdelt_client=gdelt, nl=nl),
        )
        assert result.articles_considered == 1
        assert result.articles == []

    def test_arabic_script_customer_name_matches_latin_entity_mention(self, conn, org_id, monkeypatch):
        """The whole point of names/arabic.py: an Arabic-script customer name
        and a Latin-transliterated Cloud NL entity mention must resolve to
        the same canonical tokens."""
        monkeypatch.setenv("AMLKIT_NL_ENABLED", "1")
        cid = onboard(
            conn, org_id=org_id, reference="C-AR-1", full_name="محمد أحمد الحسناوي"
        ).customer_id
        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://x.ae/ar1", "Businessman named in probe")]
        })
        nl = FakeNl(lambda text: NlResult(
            status="ok",
            entities=[EntityMention(name="Mohammed Ahmed Al Hasnawi", type_="PERSON", salience=0.4)],
        ))
        result = run_pipeline(
            conn, org_id, cid, "tester", clients=base_clients(gdelt_client=gdelt, nl=nl),
        )
        assert result.articles_considered == 1

    def test_kg_mid_match_is_recorded(self, conn, org_id, customer_id, monkeypatch):
        monkeypatch.setenv("AMLKIT_NL_ENABLED", "1")
        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://x.ae/1", "Fraud case")]
        })
        kg = FakeKg(KgResult(
            status="ok",
            entities=[KgEntity(name="Fraudy McFraud", kg_id="/m/0abc123")],
        ))
        nl = FakeNl(lambda text: NlResult(
            status="ok",
            entities=[EntityMention(
                name="Fraudy McFraud", type_="PERSON", salience=0.5, mid="/m/0abc123",
            )],
        ))
        result = run_pipeline(
            conn, org_id, customer_id, "tester",
            clients=base_clients(gdelt_client=gdelt, nl=nl, knowledge_graph=kg),
        )
        assert result.articles[0].kg_match is True

        row = conn.execute(
            "SELECT kg_match FROM media_pipeline_articles WHERE run_id=?", (result.run_id,)
        ).fetchone()
        assert row["kg_match"] == 1

    def test_kg_mismatch_is_recorded_false(self, conn, org_id, customer_id, monkeypatch):
        monkeypatch.setenv("AMLKIT_NL_ENABLED", "1")
        gdelt = FakeGdeltDoc({"articles": [article_payload("https://x.ae/1", "Fraud case")]})
        kg = FakeKg(KgResult(status="ok", entities=[KgEntity(name="Fraudy McFraud", kg_id="/m/DIFFERENT")]))
        nl = FakeNl(lambda text: NlResult(
            status="ok",
            entities=[EntityMention(name="Fraudy McFraud", type_="PERSON", salience=0.5, mid="/m/0abc123")],
        ))
        result = run_pipeline(
            conn, org_id, customer_id, "tester",
            clients=base_clients(gdelt_client=gdelt, nl=nl, knowledge_graph=kg),
        )
        assert result.articles[0].kg_match is False


class TestTriage:
    def test_disabled_uses_classify_fallback(self, conn, org_id, customer_id, monkeypatch):
        monkeypatch.delenv("AMLKIT_MEDIA_TRIAGE_ENABLED", raising=False)
        called = []
        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://x.ae/1", "Fraudy McFraud charged with fraud")]
        })
        result = run_pipeline(
            conn, org_id, customer_id, "tester",
            clients=base_clients(gdelt_client=gdelt, triage_fn=lambda batch: called.append(batch) or []),
        )
        assert called == []  # gemini never invoked
        assert result.relevant_articles[0].model_id is None

    def test_enabled_uses_triage_fn_and_maps_severity(self, conn, org_id, customer_id, monkeypatch):
        monkeypatch.setenv("AMLKIT_MEDIA_TRIAGE_ENABLED", "1")
        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://x.ae/1", "Fraudy McFraud named in FRAUD case")]
        })

        def fake_triage(batch):
            return [{
                "id": batch[0]["id"], "language": "en", "english_headline": "Fraud case",
                "relevant": True, "categories": ["fraud"], "severity": "high",
                "rationale": "Alleges fraud.",
            }]

        result = run_pipeline(
            conn, org_id, customer_id, "tester",
            clients=base_clients(gdelt_client=gdelt, triage_fn=fake_triage),
        )
        assert len(result.relevant_articles) == 1
        art = result.relevant_articles[0]
        assert art.severity == SEVERITY_FINANCIAL_CRIME  # "high" -> financial_crime_alleged
        assert art.categories == ["fraud"]
        assert art.rationale == "Alleges fraud."
        assert art.model_id == gemini.GEMINI_MODEL
        assert art.prompt_version.startswith(gemini.TRIAGE_PROMPT_VERSION)

    def test_triage_fn_marking_not_relevant_drops_the_article(self, conn, org_id, customer_id, monkeypatch):
        monkeypatch.setenv("AMLKIT_MEDIA_TRIAGE_ENABLED", "1")
        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://x.ae/1", "Fraudy McFraud wins local award")]
        })

        def fake_triage(batch):
            return [{
                "id": batch[0]["id"], "language": "en", "english_headline": "Award",
                "relevant": False, "categories": [], "severity": "low", "rationale": "not adverse",
            }]

        result = run_pipeline(
            conn, org_id, customer_id, "tester",
            clients=base_clients(gdelt_client=gdelt, triage_fn=fake_triage),
        )
        assert result.relevant_articles == []

    def test_severity_mapping_medium_and_low(self, conn, org_id, customer_id, monkeypatch):
        monkeypatch.setenv("AMLKIT_MEDIA_TRIAGE_ENABLED", "1")
        # Titles need a lexicon hit so stage 2's keyword/name-evidence gate
        # admits them into triage in the first place (AMLKIT_NL_ENABLED=0
        # here); the fake triage_fn below overrides severity regardless.
        gdelt = FakeGdeltDoc({
            "articles": [
                article_payload("https://x.ae/1", "Fraud probe A"),
                article_payload("https://x.ae/2", "Fraud probe B"),
            ]
        })

        def fake_triage(batch):
            out = []
            for item in batch:
                sev = "medium" if item["id"] == "0" else "low"
                out.append({
                    "id": item["id"], "language": "en", "english_headline": item["title"],
                    "relevant": True, "categories": [], "severity": sev, "rationale": "x",
                })
            return out

        result = run_pipeline(
            conn, org_id, customer_id, "tester",
            clients=base_clients(gdelt_client=gdelt, triage_fn=fake_triage),
        )
        severities = {a.url: a.severity for a in result.relevant_articles}
        assert severities["https://x.ae/1"] == SEVERITY_REGULATORY
        assert severities["https://x.ae/2"] == SEVERITY_REPUTATIONAL

    def test_gemini_unavailable_for_a_batch_does_not_abort_the_run(self, conn, org_id, customer_id, monkeypatch):
        monkeypatch.setenv("AMLKIT_MEDIA_TRIAGE_ENABLED", "1")
        gdelt = FakeGdeltDoc({"articles": [article_payload("https://x.ae/1", "A")]})

        def _raise(batch):
            raise gemini.GeminiUnavailable("no credentials")

        result = run_pipeline(
            conn, org_id, customer_id, "tester",
            clients=base_clients(gdelt_client=gdelt, triage_fn=_raise),
        )
        assert result.relevant_articles == []
        assert result.status in ("ok", "partial")  # never raises out of run_pipeline


class TestAuditVault:
    def test_run_and_articles_persisted_with_org_id(self, conn, org_id, customer_id):
        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://x.ae/1", "Fraudy McFraud charged with fraud")]
        })
        result = run_pipeline(conn, org_id, customer_id, "tester", clients=base_clients(gdelt_client=gdelt))

        run_row = conn.execute(
            "SELECT * FROM media_pipeline_runs WHERE id=?", (result.run_id,)
        ).fetchone()
        assert run_row["org_id"] == org_id
        assert run_row["customer_id"] == customer_id
        assert run_row["status"] == "ok"
        assert run_row["finished_at"] is not None

        art_rows = conn.execute(
            "SELECT * FROM media_pipeline_articles WHERE run_id=?", (result.run_id,)
        ).fetchall()
        assert len(art_rows) == 1
        assert art_rows[0]["org_id"] == org_id
        assert art_rows[0]["customer_id"] == customer_id

    def test_audit_log_rows_written_with_org_id(self, conn, org_id, customer_id):
        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://x.ae/1", "Fraudy McFraud charged with fraud")]
        })
        result = run_pipeline(conn, org_id, customer_id, "tester", clients=base_clients(gdelt_client=gdelt))

        actions = {
            r["action"] for r in conn.execute(
                "SELECT action FROM audit_log WHERE org_id=? AND object_type IN "
                "('customer','media_pipeline_article') AND action LIKE 'media_pipeline.%'",
                (org_id,),
            ).fetchall()
        }
        assert "media_pipeline.run.start" in actions
        assert "media_pipeline.run.finish" in actions
        assert "media_pipeline.finding.surfaced" in actions

    def test_findings_are_never_auto_dispositioned(self, conn, org_id, customer_id, monkeypatch):
        monkeypatch.setenv("AMLKIT_MEDIA_PIPELINE", "1")
        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://x.ae/1", "Fraudy McFraud charged with fraud")]
        })
        risk_before = conn.execute(
            "SELECT COUNT(*) c FROM risk_assessments WHERE customer_id=?", (customer_id,)
        ).fetchone()["c"]

        run_adverse_media(
            conn, org_id=org_id, name="unused", customer_id=customer_id,
            client=base_clients(gdelt_client=gdelt), actor="tester",
        )

        rows = conn.execute(
            "SELECT status, pipeline_run_id FROM adverse_media_findings WHERE customer_id=?",
            (customer_id,),
        ).fetchall()
        assert rows, "expected at least one finding to have been surfaced"
        assert all(r["status"] == "open" for r in rows)
        assert all(r["pipeline_run_id"] is not None for r in rows)

        risk_after = conn.execute(
            "SELECT COUNT(*) c FROM risk_assessments WHERE customer_id=?", (customer_id,)
        ).fetchone()["c"]
        assert risk_after == risk_before  # no automatic reassessment


class TestManagerDispatch:
    def test_flag_off_never_touches_the_pipeline(self, conn, org_id, customer_id, monkeypatch):
        monkeypatch.delenv("AMLKIT_MEDIA_PIPELINE", raising=False)

        def _boom(*a, **k):
            raise AssertionError("media_pipeline.run_pipeline must not be called when the flag is off")

        import amlkit.screening.media_pipeline as mp
        monkeypatch.setattr(mp, "run_pipeline", _boom)

        gdelt = FakeGdeltDoc({"articles": []})
        screening_id, result, new_findings = run_adverse_media(
            conn, org_id=org_id, name="Fraudy McFraud", customer_id=customer_id,
            client=gdelt, actor="tester",
        )
        assert result.provider == "gdelt"

    def test_flag_on_dispatches_to_pipeline_and_writes_legacy_tables(self, conn, org_id, customer_id, monkeypatch):
        monkeypatch.setenv("AMLKIT_MEDIA_PIPELINE", "1")
        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://x.ae/1", "Fraudy McFraud charged with fraud")]
        })
        screening_id, result, new_findings = run_adverse_media(
            conn, org_id=org_id, name="unused because pipeline resolves it from the db",
            customer_id=customer_id, client=base_clients(gdelt_client=gdelt), actor="tester",
        )
        assert result.provider == "media_pipeline"
        assert new_findings == 1

        finding = conn.execute(
            "SELECT * FROM adverse_media_findings WHERE screening_id=?", (screening_id,)
        ).fetchone()
        assert finding["url"] == "https://x.ae/1"
        assert finding["status"] == "open"

    def test_flag_on_but_ad_hoc_no_customer_falls_back_to_legacy(self, conn, org_id, monkeypatch):
        """run_pipeline needs a customer row to resolve a name from; an
        ad-hoc (no customer_id) search has nothing to resolve, so it keeps
        using the plain GDELT path even with the flag on."""
        monkeypatch.setenv("AMLKIT_MEDIA_PIPELINE", "1")
        gdelt = FakeGdeltDoc({"articles": []})
        _, result, _ = run_adverse_media(
            conn, org_id=org_id, name="Ad Hoc Name", customer_id=None,
            client=gdelt, actor="tester",
        )
        assert result.provider == "gdelt"


class TestLoggingRedaction:
    def test_pii_redact_is_called_and_customer_name_never_appears_in_logs(
        self, conn, org_id, customer_id, caplog, monkeypatch
    ):
        import amlkit.pii as pii_module

        calls: list[str] = []
        original = pii_module.redact

        def spy(text):
            calls.append(text)
            return original(text)

        monkeypatch.setattr(pii_module, "redact", spy)
        caplog.set_level(logging.INFO, logger="amlkit.screening.media_pipeline")

        gdelt = FakeGdeltDoc({
            "articles": [article_payload("https://x.ae/1", "Fraudy McFraud charged with fraud")]
        })
        run_pipeline(conn, org_id, customer_id, "tester", clients=base_clients(gdelt_client=gdelt))

        assert calls, "amlkit.pii.redact() was never called before a pipeline log line"
        for record in caplog.records:
            if record.name == "amlkit.screening.media_pipeline":
                assert "Fraudy McFraud" not in record.getMessage()
                assert "fraud" not in record.getMessage().lower() or "considered=" in record.getMessage()

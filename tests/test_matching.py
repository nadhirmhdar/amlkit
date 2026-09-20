"""Scoring and screening-engine tests.

Hermetic: builds its own in-memory database from a synthetic watchlist rather
than depending on downloaded sanctions data, so the suite runs offline and
gives identical results regardless of what the real lists contain today.

The false-positive suite matters as much as the match suite. An engine that
alerts on everything is compliant and useless; alert fatigue is the mechanism
by which real hits get missed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect, upsert_dataset, utcnow  # noqa: E402
from amlkit.match.engine import rescreen_all, screen  # noqa: E402
from amlkit.match.scorer import DEFAULT_THRESHOLD, name_score, score_entity  # noqa: E402
from amlkit.names.arabic import blocking_keys, canonical_key  # noqa: E402

# Synthetic listed entities. Names are fictional but structurally realistic:
# Arabic name chains with particles, plus Arabic-script aliases.
WATCHLIST = [
    ("SYN-1", "Person", "AHMED ABD AL-JALEEL AL-HASNAWI", ["أحمد عبد الجليل الحسناوي"], "ly", "1975-03-12", "male"),
    ("SYN-2", "Person", "BILAL ALI AL-WAFI", ["بلال علي الوافي"], "ly", None, "male"),
    ("SYN-3", "Person", "MOHAMMAD DAWOOD MUZAMMIL", ["محمد داود مزمل"], "pk", "1980-01-01", "male"),
    ("SYN-4", "Organization", "AL-IHSAN CHARITABLE SOCIETY", ["جمعية الإحسان الخيرية"], "ae", None, None),
    ("SYN-5", "Person", "FOAD SALEHI", ["فؤاد صالحي"], "ir", "1968-07-20", "male"),
]


@pytest.fixture()
def org_id(conn) -> int:
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
        ("Test Firm", "test-firm", "active", utcnow()),
    ).fetchone()
    conn.commit()
    return row["id"]


@pytest.fixture()
def customer_id(conn, org_id) -> int:
    now = utcnow()
    row = conn.execute(
        """INSERT INTO customers
           (org_id, reference, customer_type, full_name, canonical_key,
            status, onboarded_at, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?) RETURNING id""",
        (org_id, "C-1", "natural", "FOAD SALEHI", canonical_key("FOAD SALEHI"),
         "active", now, now, now),
    ).fetchone()
    conn.commit()
    return row["id"]


@pytest.fixture()
def conn():
    c = connect(":memory:")
    ds = upsert_dataset(c, "test_list", "Synthetic Test List", is_mandatory=True)
    now = utcnow()
    for sid, schema, caption, aliases, country, dob, gender in WATCHLIST:
        cur = c.execute(
            """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
               countries, birth_date, gender, topics, raw, first_seen, last_seen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (ds, sid, schema, caption, f'["{country}"]', dob, gender, '["sanction"]', "{}", now, now),
        )
        eid = cur.lastrowid
        for i, nm in enumerate([caption, *aliases]):
            c.execute(
                "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
                " VALUES (?,?,?,?,?)",
                (eid, nm, "primary" if i == 0 else "alias", canonical_key(nm),
                 "arabic" if i else "latin"),
            )
            for tok in blocking_keys(nm):
                c.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)", (tok, eid))
    # Make dataset fresh for consistency (though this test doesn't call onboard)
    c.execute("UPDATE datasets SET last_refresh=?, entity_count=? WHERE id=?",
              (now, len(WATCHLIST), ds))
    c.commit()
    yield c
    c.close()


class TestNameScore:
    def test_identical_scores_one(self) -> None:
        s, _ = name_score("Ahmed Al Hasnawi", "Ahmed Al Hasnawi")
        assert s == 1.0

    def test_variant_scores_one(self) -> None:
        s, _ = name_score("Ahmed Al-Hasnawi", "Ahmad al Hasnawi")
        assert s == 1.0

    def test_unrelated_scores_low(self) -> None:
        s, _ = name_score("John Smith", "Ahmed Al Hasnawi")
        assert s < 0.3

    def test_single_token_does_not_clear_threshold(self) -> None:
        """Regression: 'Mohammed' vs 'Mohammad Dawood' scored 0.875 and alerted.

        Roughly every third name in this market contains 'Mohammed', so a
        one-token query clearing the threshold floods the queue.
        """
        s, detail = name_score("Mohammed", "Mohammad Dawood")
        assert s < DEFAULT_THRESHOLD, f"single token scored {s}"
        assert "low_confidence_query" in detail

    def test_partial_name_still_reviewable(self) -> None:
        """Two of three tokens should alert -- that is a genuine possible match."""
        s, _ = name_score("Ahmed Al Hasnawi", "Ahmed Abd Al-Jaleel Al-Hasnawi")
        assert s >= DEFAULT_THRESHOLD, f"partial name scored only {s}"


class TestFeatureAdjustments:
    def _base(self, **kw):
        return score_entity("Ahmed Al Hasnawi", ["Ahmed Al Hasnawi"], **kw)

    def test_gender_mismatch_penalised(self) -> None:
        clean = self._base().score
        mismatch = self._base(query_gender="female", cand_gender="male").score
        assert mismatch < clean

    def test_dob_year_mismatch_penalised(self) -> None:
        clean = self._base().score
        mismatch = self._base(query_birth_date="1975-03-12", cand_birth_date="1988-03-12").score
        assert mismatch < clean

    def test_matching_dob_not_penalised(self) -> None:
        r = self._base(query_birth_date="1975-03-12", cand_birth_date="1975-03-12")
        assert "adjustments" not in r.features

    def test_identifier_match_overrides_weak_name(self) -> None:
        """A shared passport number is not a coincidence."""
        r = score_entity(
            "A. Hasnawi", ["Ahmed Abd Al-Jaleel Al-Hasnawi"],
            query_identifiers=[("passport", "X123456")],
            cand_identifiers=[("passport", "x123456")],
        )
        assert r.score >= 0.95
        assert "identifier_match" in r.features

    def test_score_stays_in_range(self) -> None:
        r = self._base(
            query_gender="female", cand_gender="male",
            query_birth_date="1900-01-01", cand_birth_date="2000-12-31",
            query_country="us", cand_countries=["ly"],
        )
        assert 0.0 <= r.score <= 1.0


class TestScreeningEngine:
    @pytest.mark.parametrize("query", [w[2] for w in WATCHLIST])
    def test_exact_listed_names_alert(self, conn, org_id, query: str) -> None:
        res = screen(conn, query, org_id=org_id, persist=False)
        assert res.hits, f"listed name produced no hit: {query}"
        assert max(h.score for h in res.hits) >= 0.95

    @pytest.mark.parametrize(
        "query",
        [
            "Ahmad Abd al Jaleel al Hasnawi",   # transliteration drift
            "AHMED ABD AL JALEEL AL HASNAWI",   # case + particles spaced
            "Hasnawi Ahmed Abd Al Jaleel",      # reordered chain
            "Ahmed Abd Aljaleel Alhasnawi",     # particles fused
        ],
    )
    def test_mangled_variants_still_alert(self, conn, org_id, query: str) -> None:
        res = screen(conn, query, org_id=org_id, persist=False)
        assert res.hits, f"variant missed: {query}"

    def test_arabic_query_finds_latin_record(self, conn, org_id) -> None:
        res = screen(conn, "أحمد عبد الجليل الحسناوي", org_id=org_id, persist=False)
        assert res.hits
        assert res.hits[0].caption == "AHMED ABD AL-JALEEL AL-HASNAWI"

    @pytest.mark.parametrize(
        "name",
        [
            "Ahmed Al Mansoori",
            "Fatima Hassan Al Zaabi",
            "Mohammed Abdullah Al Suwaidi",
            "Sara Khalid Al Nuaimi",
            "John Michael Smith",
            "Rajesh Kumar Sharma",
            "Omar Saeed Al Shamsi",
            "Layla Ibrahim Al Balushi",
            "Ali Hassan Al Marzooqi",
            "Noura Sultan Al Qassimi",
        ],
    )
    def test_false_positive_suite(self, conn, org_id, name: str) -> None:
        """Common UAE names that share tokens with listed entities but are not them."""
        res = screen(conn, name, org_id=org_id, persist=False)
        assert not res.hits, (
            f"false positive on {name!r}: "
            f"{[(h.caption, round(h.score, 3)) for h in res.hits]}"
        )

    def test_screening_is_persisted_with_evidence(self, conn, org_id) -> None:
        """A clear result must still be recorded -- it is the compliance evidence."""
        res = screen(conn, "Ahmed Al Mansoori", org_id=org_id, trigger="onboarding")
        assert res.screening_id is not None
        row = conn.execute(
            "SELECT trigger, hits, candidates FROM screenings WHERE id=?", (res.screening_id,)
        ).fetchone()
        assert row["trigger"] == "onboarding"
        assert row["hits"] == 0

    def test_alert_stores_score_breakdown(self, conn, org_id) -> None:
        """An examiner must be able to see why an alert fired."""
        res = screen(conn, "FOAD SALEHI", org_id=org_id, trigger="onboarding")
        row = conn.execute(
            "SELECT score_detail FROM alerts WHERE screening_id=?", (res.screening_id,)
        ).fetchone()
        assert row and "features" in row["score_detail"]

    def test_invalid_trigger_rejected(self, conn, org_id) -> None:
        with pytest.raises(ValueError):
            screen(conn, "Ahmed Al Hasnawi", org_id=org_id, trigger="whenever", persist=False)

    def test_audit_log_written(self, conn, org_id) -> None:
        screen(conn, "FOAD SALEHI", org_id=org_id, trigger="periodic")
        n = conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE action='screening.run' AND org_id=?",
            (org_id,),
        ).fetchone()["c"]
        assert n >= 1

    def test_screening_requires_org_id(self, conn) -> None:
        """org_id has no default -- an unpersisted ad-hoc screening is still
        shown to one specific firm's operator, and must not silently accept a
        caller that forgot which firm it is running for."""
        with pytest.raises(TypeError):
            screen(conn, "Ahmed Al Hasnawi", persist=False)  # type: ignore[call-arg]


class TestAlertDedup:
    """rescreen_all() re-runs the same query for every customer after every
    dataset refresh (roughly every 20h in production) -- a match nobody has
    reviewed yet must not accumulate a fresh duplicate alert on every run."""

    def test_rescreen_does_not_duplicate_open_alert(self, conn, org_id, customer_id) -> None:
        first = screen(
            conn, "FOAD SALEHI", org_id=org_id, trigger="onboarding", customer_id=customer_id
        )
        assert first.alerts_created == 1

        second = screen(
            conn, "FOAD SALEHI", org_id=org_id, trigger="list_update", customer_id=customer_id
        )
        assert second.alerts_created == 0

        n = conn.execute("SELECT COUNT(*) c FROM alerts WHERE org_id=?", (org_id,)).fetchone()["c"]
        assert n == 1

    def test_new_alert_allowed_once_prior_is_dispositioned(self, conn, org_id, customer_id) -> None:
        """Dedup only suppresses *open* duplicates -- once a reviewer has
        actually dispositioned the earlier alert, a fresh match must still
        raise a new one rather than being silently swallowed forever."""
        first = screen(
            conn, "FOAD SALEHI", org_id=org_id, trigger="onboarding", customer_id=customer_id
        )
        conn.execute(
            "UPDATE alerts SET status='false_positive' WHERE screening_id=?",
            (first.screening_id,),
        )
        conn.commit()

        second = screen(
            conn, "FOAD SALEHI", org_id=org_id, trigger="list_update", customer_id=customer_id
        )
        assert second.alerts_created == 1

    def test_rescreen_all_reports_only_genuinely_new_alerts(self, conn, org_id, customer_id) -> None:
        first = rescreen_all(conn, org_id)
        assert first["alerts"] == 1

        second = rescreen_all(conn, org_id)
        assert second["alerts"] == 0


class TestAuditImmutability:
    def test_update_blocked(self, conn) -> None:
        conn.execute(
            "INSERT INTO audit_log (ts, actor, action) VALUES (?,?,?)", (utcnow(), "t", "x")
        )
        with pytest.raises(Exception, match="append-only"):
            conn.execute("UPDATE audit_log SET actor='tampered'")

    def test_delete_blocked(self, conn) -> None:
        conn.execute(
            "INSERT INTO audit_log (ts, actor, action) VALUES (?,?,?)", (utcnow(), "t", "x")
        )
        with pytest.raises(Exception, match="append-only"):
            conn.execute("DELETE FROM audit_log")


class TestArabicNameMatching:
    """Issue #139: Arabic names starting with Alef-Lam must match their Latin equivalents."""

    def test_ilyas_arabic_matches_latin(self) -> None:
        """الياس (Ilyas in Arabic) should match 'Ilyas' in Latin."""
        score, _ = name_score("الياس", "Ilyas")
        assert score >= 0.85, f"Expected high match score for الياس vs Ilyas, got {score}"

    def test_ilyas_hamza_matches_elias(self) -> None:
        """إلياس (Ilyas with hamza-below) should match 'Elias'."""
        score, _ = name_score("إلياس", "Elias")
        assert score >= 0.85, f"Expected high match score for إلياس vs Elias, got {score}"

    def test_ilham_arabic_matches_latin(self) -> None:
        """إلهام (Ilham) should match 'Ilham'."""
        score, _ = name_score("إلهام", "Ilham")
        assert score >= 0.85, f"Expected high match score for إلهام vs Ilham, got {score}"

    def test_almas_arabic_matches_latin(self) -> None:
        """الماس (Almas) should match 'Almas'."""
        score, _ = name_score("الماس", "Almas")
        assert score >= 0.85, f"Expected high match score for الماس vs Almas, got {score}"

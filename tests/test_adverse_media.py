"""Adverse media screening tests.

Nothing here touches the network. `StubClient` stands in for `GDELTClient`
through the `MediaClient` protocol, which is the whole reason that seam
exists -- a test suite that depended on a free public news API would be slow,
flaky, and rate-limited to one request every five seconds.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import (  # noqa: E402
    adverse_media_due,
    adverse_media_severity,
    close_relationship,
    disposition_adverse_media_finding,
    onboard,
    run_adverse_media,
    run_due_adverse_media,
)
from amlkit.db import connect, utcnow  # noqa: E402
from amlkit.screening.adverse_media import (  # noqa: E402
    SEVERITY_FINANCIAL_CRIME,
    SEVERITY_NONE,
    SEVERITY_REGULATORY,
    SEVERITY_REPUTATIONAL,
    GDELTClient,
    MediaUnavailable,
    build_query,
    classify,
    parse_articles,
    search,
    worst_severity,
)


def article(url: str, title: str, **kw) -> dict:
    return {
        "url": url,
        "title": title,
        "domain": kw.get("domain", "example.com"),
        "language": kw.get("language", "English"),
        "sourcecountry": kw.get("sourcecountry", "United Arab Emirates"),
        "seendate": kw.get("seendate", "20250903T120000Z"),
    }


class StubClient:
    """Canned GDELT responses, one per query in order (last one repeats)."""

    def __init__(self, *responses, fail_on: set[int] | None = None) -> None:
        self.responses = list(responses) or [{"articles": []}]
        self.fail_on = fail_on or set()
        self.queries: list[str] = []

    def fetch(self, query, *, window_months, max_records):
        idx = len(self.queries)
        self.queries.append(query)
        if idx in self.fail_on:
            raise MediaUnavailable("stub provider down")
        return self.responses[min(idx, len(self.responses) - 1)]


@pytest.fixture()
def conn():
    c = connect(":memory:")
    yield c
    c.close()


@pytest.fixture()
def org_id(conn) -> int:
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
        " RETURNING id",
        ("Test Firm", "test-firm", "active", utcnow()),
    ).fetchone()
    conn.commit()
    return row["id"]


@pytest.fixture()
def customer_id(conn, org_id) -> int:
    return onboard(
        conn, org_id=org_id, reference="C-AM-1", full_name="Mohammed Al Mansoori",
        name_arabic="محمد المنصوري", customer_type="natural", nationality="ae",
    ).customer_id


class TestClassification:
    def test_financial_crime_beats_lesser_tiers(self) -> None:
        severity, terms = classify("Tycoon convicted in money laundering case")
        assert severity == SEVERITY_FINANCIAL_CRIME
        assert "money laundering" in terms

    def test_regulatory_action_tier(self) -> None:
        severity, terms = classify("Regulator fined the brokerage over reporting failings")
        assert severity == SEVERITY_REGULATORY
        assert "fined" in terms

    def test_reputational_tier(self) -> None:
        severity, _ = classify("Executive stepped down amid a growing scandal")
        assert severity == SEVERITY_REPUTATIONAL

    def test_neutral_coverage_is_not_adverse(self) -> None:
        assert classify("Company opens a new Dubai office")[0] == SEVERITY_NONE

    def test_arabic_terms_classify(self) -> None:
        severity, terms = classify("غرامة على الشركة بعد تحقيق")
        assert severity == SEVERITY_REGULATORY
        assert "غرامة" in terms

    def test_arabic_financial_crime_outranks_regulatory(self) -> None:
        # Both tiers present: the laundering allegation is the fact that
        # matters, not the fine that accompanied it.
        severity, _ = classify("غرامة في قضية غسل الأموال")
        assert severity == SEVERITY_FINANCIAL_CRIME

    def test_severity_ranking(self) -> None:
        assert worst_severity([SEVERITY_REGULATORY, SEVERITY_FINANCIAL_CRIME]) == (
            SEVERITY_FINANCIAL_CRIME
        )
        assert worst_severity([SEVERITY_REPUTATIONAL]) == SEVERITY_REPUTATIONAL
        assert worst_severity([]) == SEVERITY_NONE

    def test_severity_ranking_accepts_a_generator(self) -> None:
        # Regression: every real caller passes a generator (a cursor, a
        # comprehension over findings). Scanning it once per tier exhausted
        # it on the first, so anything below financial-crime scored `none` --
        # a risk factor silently reading zero. A list argument hides this.
        assert worst_severity(s for s in [SEVERITY_REGULATORY]) == SEVERITY_REGULATORY
        assert worst_severity(s for s in [SEVERITY_REPUTATIONAL]) == SEVERITY_REPUTATIONAL


class TestQueryBuilding:
    def test_name_is_phrase_quoted(self) -> None:
        # Unquoted, "Ahmed Al Mansoori" would match every article containing
        # "Ahmed" -- the exact false-positive mode this codebase exists to avoid.
        assert build_query("Ahmed Al Mansoori").startswith('"Ahmed Al Mansoori" (')

    def test_query_carries_risk_terms(self) -> None:
        q = build_query("Someone")
        assert "laundering" in q and "OR" in q


class TestParsing:
    def test_missing_optional_fields_do_not_drop_the_article(self) -> None:
        arts = parse_articles({"articles": [{"url": "https://a/1", "title": "Fraud charge"}]})
        assert len(arts) == 1
        assert arts[0].domain == ""

    def test_article_without_url_is_dropped(self) -> None:
        # A finding with no link is not evidence of anything.
        assert parse_articles({"articles": [{"title": "no link"}]}) == []

    def test_seendate_becomes_iso(self) -> None:
        arts = parse_articles({"articles": [article("https://a/1", "Fraud")]})
        assert arts[0].published_at == "2025-09-03T12:00:00+00:00"

    def test_empty_payload(self) -> None:
        assert parse_articles({}) == []


class TestSearch:
    def test_neutral_articles_are_not_findings(self) -> None:
        client = StubClient({"articles": [article("https://a/1", "Firm opens Dubai office")]})
        res = search("Ahmed Al Mansoori", client=client)
        assert res.status == "ok"
        assert res.clear
        assert res.articles_considered == 1

    def test_name_in_headline_is_stronger_evidence(self) -> None:
        client = StubClient({"articles": [
            article("https://a/1", "Mohd Al-Mansouri convicted of fraud"),
            article("https://a/2", "Dubai brokerage fined by regulator"),
        ]})
        res = search("Mohammed Al Mansoori", client=client)
        by_url = {f.article.url: f for f in res.findings}
        # Arabic-aware canonicalisation: "Mohd Al-Mansouri" in the headline is
        # recognised as the customer recorded as "Mohammed Al Mansoori".
        assert by_url["https://a/1"].name_evidence == "title"
        assert by_url["https://a/2"].name_evidence == "body"

    def test_findings_sorted_worst_first(self) -> None:
        client = StubClient({"articles": [
            article("https://a/1", "Executive faces a scandal"),
            article("https://a/2", "Executive convicted of bribery"),
        ]})
        res = search("Some Person", client=client)
        assert res.findings[0].severity == SEVERITY_FINANCIAL_CRIME
        assert res.severity == SEVERITY_FINANCIAL_CRIME

    def test_arabic_name_triggers_a_second_query(self) -> None:
        client = StubClient({"articles": []})
        search("Mohammed Al Mansoori", name_arabic="محمد المنصوري", client=client)
        assert len(client.queries) == 2
        assert "محمد المنصوري" in client.queries[1]

    def test_same_article_from_both_scripts_is_deduped(self) -> None:
        client = StubClient({"articles": [article("https://a/1", "Convicted of fraud")]})
        res = search("Mohammed Al Mansoori", name_arabic="محمد المنصوري", client=client)
        assert len(res.findings) == 1

    def test_total_provider_failure_is_unavailable_not_clear(self) -> None:
        # The distinction this whole module is built around: "checked, found
        # nothing" must never look like "the check could not run".
        client = StubClient(fail_on={0})
        res = search("Someone", client=client)
        assert res.status == "unavailable"
        assert not res.clear
        assert "stub provider down" in res.error

    def test_partial_failure_stays_ok_but_records_the_gap(self) -> None:
        client = StubClient({"articles": [article("https://a/1", "Convicted of fraud")]},
                            fail_on={1})
        res = search("Mohammed Al Mansoori", name_arabic="محمد المنصوري", client=client)
        assert res.status == "ok"
        assert res.findings
        assert res.error  # the Arabic half is recorded as missed, not ignored

    def test_empty_name_is_a_programming_error(self) -> None:
        with pytest.raises(ValueError):
            search("   ")


class TestPersistence:
    def test_run_records_screening_and_findings(self, conn, org_id, customer_id) -> None:
        client = StubClient({"articles": [
            article("https://a/1", "Mohd Al-Mansouri convicted of money laundering"),
            article("https://a/2", "Unrelated firm opens an office"),
        ]})
        sid, res, new = run_adverse_media(
            conn, org_id=org_id, customer_id=customer_id,
            name="Mohammed Al Mansoori", trigger="adhoc", client=client, actor="tester",
        )
        row = conn.execute(
            "SELECT * FROM adverse_media_screenings WHERE id=?", (sid,)
        ).fetchone()
        assert row["status"] == "ok"
        assert row["articles_considered"] == 2
        assert row["findings"] == 1
        assert row["severity"] == SEVERITY_FINANCIAL_CRIME
        assert new == 1

    def test_failed_run_is_still_recorded(self, conn, org_id, customer_id) -> None:
        sid, res, new = run_adverse_media(
            conn, org_id=org_id, customer_id=customer_id, name="Mohammed Al Mansoori",
            client=StubClient(fail_on={0}), actor="tester",
        )
        row = conn.execute(
            "SELECT status, error, findings FROM adverse_media_screenings WHERE id=?", (sid,)
        ).fetchone()
        assert row["status"] == "unavailable"
        assert row["error"]
        assert row["findings"] == 0
        assert new == 0

    def test_rerun_does_not_duplicate_a_known_article(self, conn, org_id, customer_id) -> None:
        client = StubClient({"articles": [article("https://a/1", "Convicted of fraud")]})
        run_adverse_media(conn, org_id=org_id, customer_id=customer_id,
                          name="Mohammed Al Mansoori", client=client, actor="tester")
        _, _, new = run_adverse_media(conn, org_id=org_id, customer_id=customer_id,
                                      name="Mohammed Al Mansoori", client=client, actor="tester")
        assert new == 0
        count = conn.execute(
            "SELECT COUNT(*) c FROM adverse_media_findings WHERE customer_id=?", (customer_id,)
        ).fetchone()["c"]
        assert count == 1

    def test_run_is_audited(self, conn, org_id, customer_id) -> None:
        run_adverse_media(conn, org_id=org_id, customer_id=customer_id,
                          name="Mohammed Al Mansoori",
                          client=StubClient({"articles": []}), actor="tester")
        row = conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE action='adverse_media.screen' AND org_id=?",
            (org_id,),
        ).fetchone()
        assert row["c"] == 1


class TestDispositionAndRisk:
    def _one_finding(self, conn, org_id, customer_id, title="Convicted of money laundering"):
        run_adverse_media(
            conn, org_id=org_id, customer_id=customer_id, name="Mohammed Al Mansoori",
            client=StubClient({"articles": [article("https://a/1", title)]}), actor="tester",
        )
        return conn.execute(
            "SELECT id FROM adverse_media_findings WHERE customer_id=?", (customer_id,)
        ).fetchone()["id"]

    def test_open_finding_does_not_move_the_risk_rating(self, conn, org_id, customer_id) -> None:
        before = conn.execute(
            "SELECT score FROM risk_assessments WHERE customer_id=? ORDER BY id DESC LIMIT 1",
            (customer_id,),
        ).fetchone()["score"]
        self._one_finding(conn, org_id, customer_id)
        after = conn.execute(
            "SELECT score FROM risk_assessments WHERE customer_id=? ORDER BY id DESC LIMIT 1",
            (customer_id,),
        ).fetchone()["score"]
        # An unreviewed news article is a lead, not a finding about a customer.
        assert after == before
        assert adverse_media_severity(conn, customer_id, org_id) == SEVERITY_NONE

    def test_confirming_relevant_re_rates_the_customer(self, conn, org_id, customer_id) -> None:
        fid = self._one_finding(conn, org_id, customer_id)
        before = conn.execute(
            "SELECT score FROM risk_assessments WHERE customer_id=? ORDER BY id DESC LIMIT 1",
            (customer_id,),
        ).fetchone()["score"]
        rating = disposition_adverse_media_finding(
            conn, fid, org_id, status="relevant", note="Same DOB and passport", actor="tester",
        )
        assert rating
        row = conn.execute(
            "SELECT score, factors FROM risk_assessments WHERE customer_id=? ORDER BY id DESC LIMIT 1",
            (customer_id,),
        ).fetchone()
        assert row["score"] == before + 35  # ruleset: financial_crime_alleged
        assert SEVERITY_FINANCIAL_CRIME in row["factors"]
        assert adverse_media_severity(conn, customer_id, org_id) == SEVERITY_FINANCIAL_CRIME

    def test_not_relevant_leaves_the_rating_alone(self, conn, org_id, customer_id) -> None:
        fid = self._one_finding(conn, org_id, customer_id)
        before = conn.execute(
            "SELECT score FROM risk_assessments WHERE customer_id=? ORDER BY id DESC LIMIT 1",
            (customer_id,),
        ).fetchone()["score"]
        disposition_adverse_media_finding(
            conn, fid, org_id, status="not_relevant", note="Different person", actor="tester",
        )
        after = conn.execute(
            "SELECT score FROM risk_assessments WHERE customer_id=? ORDER BY id DESC LIMIT 1",
            (customer_id,),
        ).fetchone()["score"]
        assert after == before

    def test_reassessment_preserves_other_factors(self, conn, org_id) -> None:
        # The re-rating must change exactly one factor. A real-estate customer
        # who was already carrying 25 sector points keeps them.
        cid = onboard(conn, org_id=org_id, reference="C-AM-2", full_name="Sara Hassan",
                      sector="real_estate", delivery_channel="remote_verified").customer_id
        fid = self._one_finding(conn, org_id, cid, title="Sara Hassan fined by the regulator")
        disposition_adverse_media_finding(conn, fid, org_id, status="relevant", actor="tester")
        import json
        factors = json.loads(conn.execute(
            "SELECT factors FROM risk_assessments WHERE customer_id=? ORDER BY id DESC LIMIT 1",
            (cid,),
        ).fetchone()["factors"])
        assert factors["sector"]["value"] == "real_estate"
        assert factors["delivery_channel"]["value"] == "remote_verified"
        assert factors["adverse_media"]["value"] == SEVERITY_REGULATORY

    def test_invalid_status_rejected(self, conn, org_id, customer_id) -> None:
        fid = self._one_finding(conn, org_id, customer_id)
        with pytest.raises(ValueError):
            disposition_adverse_media_finding(conn, fid, org_id, status="true_positive")

    def test_cross_tenant_finding_is_not_dispositionable(self, conn, org_id, customer_id) -> None:
        fid = self._one_finding(conn, org_id, customer_id)
        other = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
            " RETURNING id", ("Other", "other", "active", utcnow()),
        ).fetchone()["id"]
        with pytest.raises(ValueError):
            disposition_adverse_media_finding(conn, fid, other, status="relevant")


class TestGDELTClientErrorHandling:
    """The transport, exercised without hitting the network."""

    def _client_returning(self, monkeypatch, status_code: int, text: str):
        import httpx

        class FakeResponse:
            def __init__(self) -> None:
                self.status_code = status_code
                self.text = text

        monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse())
        return GDELTClient()

    def test_rate_limit_is_reported_as_such(self, monkeypatch) -> None:
        client = self._client_returning(monkeypatch, 429, "Please limit requests")
        with pytest.raises(MediaUnavailable, match="rate limit"):
            client.fetch("q", window_months=24, max_records=10)

    def test_html_error_page_with_http_200_is_caught(self, monkeypatch) -> None:
        # GDELT answers a malformed query with 200 + HTML rather than an error
        # status. Without this check the failure surfaces as "invalid JSON",
        # which sends whoever debugs it looking in the wrong place.
        client = self._client_returning(monkeypatch, 200, "<html>bad query</html>")
        with pytest.raises(MediaUnavailable, match="rejected the query"):
            client.fetch("q", window_months=24, max_records=10)

    def test_empty_body_is_caught(self, monkeypatch) -> None:
        client = self._client_returning(monkeypatch, 200, "   ")
        with pytest.raises(MediaUnavailable, match="empty body"):
            client.fetch("q", window_months=24, max_records=10)

    def test_server_error_is_caught(self, monkeypatch) -> None:
        client = self._client_returning(monkeypatch, 503, "down")
        with pytest.raises(MediaUnavailable, match="HTTP 503"):
            client.fetch("q", window_months=24, max_records=10)

    def test_transport_error_is_caught(self, monkeypatch) -> None:
        import httpx

        def boom(*a, **k):
            raise httpx.ConnectError("no route to host")

        monkeypatch.setattr(httpx, "get", boom)
        with pytest.raises(MediaUnavailable, match="request failed"):
            GDELTClient().fetch("q", window_months=24, max_records=10)


class TestWebRoutes:
    """Exercises the routes and the templates they render.

    A Jinja error in the new customer/evidence panels would not show up in
    any of the tests above -- they never render a page -- so the templates
    are exercised here rather than assumed to work.
    """

    @pytest.fixture()
    def web(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "web.db"))
        monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_api import _register  # reuse the registration+verification flow

        from fastapi.testclient import TestClient

        from amlkit.api.app import app

        client = TestClient(app)
        _register(client, "AM Firm", "alice", "alice@amfirm.ae")
        return client

    def _csrf(self, client) -> str:
        return client.cookies.get("amlkit_csrf")

    def _customer(self, client) -> int:
        client.get("/customers/new")
        client.post("/customers", data={
            "reference": "C-WEB-1", "full_name": "Mohammed Al Mansoori",
            "customer_type": "natural", "sector": "real_estate",
            "csrf_token": self._csrf(client),
        }, follow_redirects=True)
        import os
        import sqlite3
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT id FROM customers ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        return row["id"]

    def test_customer_page_renders_the_panel_before_any_check(self, web) -> None:
        cid = self._customer(web)
        r = web.get(f"/customers/{cid}")
        assert r.status_code == 200
        assert "Adverse media" in r.text
        assert "Never checked." in r.text
        # GDELT's terms require the citation and link wherever its data is
        # used -- rendered by the template, not left to a developer.
        assert "gdeltproject.org" in r.text

    def test_run_and_disposition_through_the_web(self, web, monkeypatch) -> None:
        cid = self._customer(web)

        import amlkit.cases.manager as mgr

        stub = StubClient({"articles": [
            article("https://a/1", "Mohd Al-Mansouri convicted of money laundering"),
        ]})
        real_search = mgr.search
        monkeypatch.setattr(
            mgr, "search",
            lambda name, **kw: real_search(name, **{**kw, "client": stub}),
        )

        r = web.post(f"/customers/{cid}/adverse-media",
                     data={"window_months": "24", "csrf_token": self._csrf(web)},
                     follow_redirects=True)
        assert r.status_code == 200
        assert "financial crime alleged" in r.text

        import os
        import sqlite3
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        conn.row_factory = sqlite3.Row
        fid = conn.execute("SELECT id FROM adverse_media_findings").fetchone()["id"]
        conn.close()

        r = web.post(f"/adverse-media/{fid}/disposition",
                     data={"status": "relevant", "note": "Confirmed by passport",
                           "customer_id": str(cid), "csrf_token": self._csrf(web)},
                     follow_redirects=True)
        assert r.status_code == 200
        assert "re-rated" in r.text

        # And the evidence pack renders the same record.
        r = web.get(f"/customers/{cid}/evidence")
        assert r.status_code == 200
        assert "Adverse media" in r.text
        assert "https://a/1" in r.text

    def test_dashboard_shows_due_and_batch_runs(self, web, monkeypatch) -> None:
        cid = self._customer(web)
        r = web.get("/dashboard")
        assert r.status_code == 200
        assert "Adverse media due" in r.text
        assert "never checked" in r.text

        import amlkit.cases.manager as mgr

        stub = StubClient({"articles": [
            article("https://a/1", "Mohd Al-Mansouri convicted of money laundering"),
        ]})
        real_search = mgr.search
        monkeypatch.setattr(
            mgr, "search",
            lambda name, **kw: real_search(name, **{**kw, "client": stub}),
        )
        r = web.post("/adverse-media/run-due",
                     data={"limit": "5", "csrf_token": self._csrf(web)},
                     follow_redirects=True)
        assert r.status_code == 200
        assert "checked 1" in r.text
        assert "0 still due" in r.text

    def test_run_due_requires_a_session(self, web) -> None:
        web.post("/logout", data={"csrf_token": self._csrf(web)})
        r = web.post("/adverse-media/run-due",
                     data={"csrf_token": self._csrf(web)}, follow_redirects=False)
        assert r.headers["location"] == "/login"

    def test_disposition_requires_csrf(self, web) -> None:
        cid = self._customer(web)
        r = web.post(f"/adverse-media/1/disposition",
                     data={"status": "relevant", "customer_id": str(cid)},
                     follow_redirects=False)
        assert r.status_code in (303, 307)

    def test_run_requires_a_session(self, web) -> None:
        cid = self._customer(web)
        web.post("/logout", data={"csrf_token": self._csrf(web)})
        r = web.post(f"/customers/{cid}/adverse-media",
                     data={"csrf_token": self._csrf(web)}, follow_redirects=False)
        assert r.headers["location"] == "/login"


class TestMobileApi:
    """The JSON API the Android client uses, kept at parity with the web app."""

    @pytest.fixture()
    def api(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "api.db"))
        monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
        from fastapi.testclient import TestClient

        from amlkit.api.app import app

        client = TestClient(app)
        r = client.post("/api/v1/auth/register-organization", json={
            "org_name": "API Firm", "name": "alice", "email": "alice@apifirm.ae",
            "password": "a-strong-password-1",
        })
        token = r.json()["dev_verification_token"]
        r = client.post("/api/v1/auth/verify-email", json={"token": token})
        return client, {"Authorization": f"Bearer {r.json()['token']}"}

    def test_run_and_disposition(self, api, monkeypatch) -> None:
        client, headers = api
        cid = client.post("/api/v1/customers", headers=headers, json={
            "reference": "C-API-1", "full_name": "Mohammed Al Mansoori",
            "customer_type": "natural", "sector": "real_estate",
        }).json()["customer_id"]

        import amlkit.cases.manager as mgr

        stub = StubClient({"articles": [
            article("https://a/1", "Mohd Al-Mansouri convicted of money laundering"),
        ]})
        real_search = mgr.search
        monkeypatch.setattr(
            mgr, "search",
            lambda name, **kw: real_search(name, **{**kw, "client": stub}),
        )

        r = client.post(f"/api/v1/customers/{cid}/adverse-media",
                        headers=headers, json={"window_months": 24})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok"
        assert body["findings"] == 1
        assert body["severity"] == SEVERITY_FINANCIAL_CRIME
        # GDELT's terms require the citation to travel with the data, so the
        # native client is handed it rather than expected to hardcode it.
        assert "gdeltproject.org" in body["attribution"]

        detail = client.get(f"/api/v1/customers/{cid}", headers=headers).json()
        assert len(detail["adverse_media"]) == 1
        assert detail["adverse_media_runs"][0]["status"] == "ok"
        fid = detail["adverse_media"][0]["id"]

        r = client.post(f"/api/v1/adverse-media/{fid}/disposition",
                        headers=headers, json={"status": "relevant", "note": "Confirmed"})
        assert r.status_code == 200
        assert r.json()["risk_rating"] == "high"

    def test_invalid_disposition_is_a_clean_400(self, api) -> None:
        client, headers = api
        r = client.post("/api/v1/adverse-media/999/disposition",
                        headers=headers, json={"status": "nonsense"})
        assert r.status_code == 400

    def test_requires_a_token(self, api) -> None:
        client, _ = api
        assert client.post("/api/v1/customers/1/adverse-media", json={}).status_code == 401


class TestPeriodicRecheck:
    """The cadence control: who is due, and the bounded batch that works it."""

    def _backdate(self, conn, customer_id: int, days: int) -> None:
        from datetime import datetime, timedelta, timezone
        when = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        conn.execute(
            "UPDATE adverse_media_screenings SET run_at=? WHERE customer_id=?",
            (when, customer_id),
        )
        conn.commit()

    def test_never_checked_customer_is_due(self, conn, org_id, customer_id) -> None:
        due = adverse_media_due(conn, org_id)
        assert [d["id"] for d in due] == [customer_id]
        assert due[0]["reason"] == "never"
        assert due[0]["last_checked"] is None

    def test_interval_comes_from_the_rating(self, conn, org_id) -> None:
        # real_estate (25) + predominantly_cash (25) = 50 -> high -> 3 months;
        # a bare natural person -> low -> 12. The cadence is risk-based, which
        # is the whole point of keeping it in ruleset.yaml beside review_months.
        high = onboard(conn, org_id=org_id, reference="C-H", full_name="High Risk",
                       sector="real_estate", cash_level="predominantly_cash").customer_id
        low = onboard(conn, org_id=org_id, reference="C-L", full_name="Low Risk").customer_id
        by_id = {d["id"]: d for d in adverse_media_due(conn, org_id)}
        assert by_id[high]["rating"] == "high"
        assert by_id[high]["interval_months"] == 3
        assert by_id[low]["rating"] == "low"
        assert by_id[low]["interval_months"] == 12

    def test_successful_check_clears_the_customer(self, conn, org_id, customer_id) -> None:
        run_adverse_media(conn, org_id=org_id, customer_id=customer_id,
                          name="Mohammed Al Mansoori",
                          client=StubClient({"articles": []}), actor="tester")
        assert adverse_media_due(conn, org_id) == []

    def test_failed_check_does_NOT_clear_the_customer(self, conn, org_id, customer_id) -> None:
        # The rule this control turns on: an outage is not evidence about a
        # customer. Letting a failed attempt reset the clock would convert a
        # provider being down into a clean bill of health.
        run_adverse_media(conn, org_id=org_id, customer_id=customer_id,
                          name="Mohammed Al Mansoori",
                          client=StubClient(fail_on={0}), actor="tester")
        due = adverse_media_due(conn, org_id)
        assert [d["id"] for d in due] == [customer_id]
        assert due[0]["reason"] == "never"

    def test_stale_check_becomes_due_again(self, conn, org_id, customer_id) -> None:
        run_adverse_media(conn, org_id=org_id, customer_id=customer_id,
                          name="Mohammed Al Mansoori",
                          client=StubClient({"articles": []}), actor="tester")
        assert adverse_media_due(conn, org_id) == []
        self._backdate(conn, customer_id, 400)   # past the 12-month low-risk interval
        due = adverse_media_due(conn, org_id)
        assert [d["id"] for d in due] == [customer_id]
        assert due[0]["reason"] == "stale"
        assert due[0]["last_checked"]

    def test_recent_check_is_not_stale(self, conn, org_id, customer_id) -> None:
        run_adverse_media(conn, org_id=org_id, customer_id=customer_id,
                          name="Mohammed Al Mansoori",
                          client=StubClient({"articles": []}), actor="tester")
        self._backdate(conn, customer_id, 30)
        assert adverse_media_due(conn, org_id) == []

    def test_never_checked_sorts_before_stale(self, conn, org_id, customer_id) -> None:
        run_adverse_media(conn, org_id=org_id, customer_id=customer_id,
                          name="Mohammed Al Mansoori",
                          client=StubClient({"articles": []}), actor="tester")
        self._backdate(conn, customer_id, 400)
        fresh = onboard(conn, org_id=org_id, reference="C-NEW", full_name="Never Checked").customer_id
        due = adverse_media_due(conn, org_id)
        assert [d["id"] for d in due] == [fresh, customer_id]

    def test_closed_customer_is_not_due(self, conn, org_id, customer_id) -> None:
        close_relationship(conn, customer_id, org_id=org_id, actor="tester")
        assert adverse_media_due(conn, org_id) == []

    def test_due_list_is_org_scoped(self, conn, org_id, customer_id) -> None:
        other = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
            " RETURNING id", ("Other", "other", "active", utcnow()),
        ).fetchone()["id"]
        conn.commit()
        assert adverse_media_due(conn, other) == []

    def test_batch_is_bounded_by_limit(self, conn, org_id) -> None:
        for i in range(4):
            onboard(conn, org_id=org_id, reference=f"C-B{i}", full_name=f"Person {i}")
        out = run_due_adverse_media(conn, org_id, limit=2,
                                    client=StubClient({"articles": []}), actor="tester")
        assert out["attempted"] == 2
        assert out["checked"] == 2
        assert out["still_due"] == 2

    def test_batch_reports_findings_and_clears_the_queue(self, conn, org_id, customer_id) -> None:
        client = StubClient({"articles": [
            article("https://a/1", "Mohd Al-Mansouri convicted of money laundering"),
        ]})
        out = run_due_adverse_media(conn, org_id, limit=5, client=client, actor="tester")
        assert out == {"attempted": 1, "checked": 1, "failed": 0,
                       "new_findings": 1, "still_due": 0}

    def test_provider_outage_does_not_abort_the_batch(self, conn, org_id) -> None:
        # One unreachable moment must not lose the customers queued behind it.
        for i in range(3):
            onboard(conn, org_id=org_id, reference=f"C-F{i}", full_name=f"Person {i}")
        out = run_due_adverse_media(conn, org_id, limit=3,
                                    client=StubClient({"articles": []}, fail_on={0}),
                                    actor="tester")
        assert out["attempted"] == 3
        assert out["failed"] == 1
        assert out["checked"] == 2
        # The one that failed is still due; the two that succeeded are not.
        assert out["still_due"] == 1

    def test_batch_records_the_periodic_trigger(self, conn, org_id, customer_id) -> None:
        run_due_adverse_media(conn, org_id, limit=1,
                              client=StubClient({"articles": []}), actor="tester")
        row = conn.execute(
            "SELECT trigger FROM adverse_media_screenings WHERE customer_id=?", (customer_id,)
        ).fetchone()
        assert row["trigger"] == "periodic"

    def test_dashboard_surfaces_the_due_list(self, conn, org_id, customer_id) -> None:
        from amlkit import queries
        assert [c["id"] for c in queries.dashboard(conn, org_id)["adverse_media_due"]] == [customer_id]

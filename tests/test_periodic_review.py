"""Periodic CDD review (L-70, L-71, L-72, L-73): only an explicit review resets
`next_review`; event-driven re-assessments carry it forward."""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_adverse_media import StubClient, article  # noqa: E402
from test_adverse_media import conn, customer_id, org_id  # noqa: E402,F401  (fixtures)
from test_api import _add_operator, _csrf, _login, _register, client  # noqa: E402,F401
from test_mobile_api import api  # noqa: E402,F401

from amlkit.cases.manager import (  # noqa: E402
    complete_periodic_review,
    disposition_adverse_media_finding,
    due_for_review,
    onboard,
    periodic_reviews,
    record_transaction,
    run_adverse_media,
)
from amlkit.risk.model import review_date_for, ruleset  # noqa: E402

OVERDUE = "2026-01-01"
NOTE = "Refreshed ID, source of funds and ownership; no change."


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _make_overdue(conn, customer_id) -> None:
    conn.execute("UPDATE risk_assessments SET next_review=? WHERE customer_id=?",
                 (OVERDUE, customer_id))
    conn.commit()


def _latest(conn, customer_id):
    return conn.execute(
        "SELECT rating, next_review FROM risk_assessments WHERE customer_id=?"
        " ORDER BY id DESC LIMIT 1", (customer_id,)).fetchone()


def _is_due(conn, org_id, customer_id) -> bool:
    return customer_id in [r["id"] for r in due_for_review(conn, org_id)]


class TestReviewClockServiceLevel:
    def test_cash_transaction_alert_does_not_clear_overdue(self, conn, org_id, customer_id):
        _make_overdue(conn, customer_id)
        assert _is_due(conn, org_id, customer_id)
        _, triggered = record_transaction(conn, customer_id, org_id, direction="in",
                                          method="cash", amount=60000, currency="AED")
        conn.commit()
        assert triggered, "the fixture transaction must raise an alert"
        assert _is_due(conn, org_id, customer_id)
        assert _latest(conn, customer_id)["next_review"] == OVERDUE

    def test_not_relevant_adverse_media_ruling_does_not_clear_overdue(
            self, conn, org_id, customer_id):
        run_adverse_media(conn, org_id=org_id, customer_id=customer_id,
                          name="Mohammed Al Mansoori",
                          client=StubClient({"articles": [article("https://a/1", "Convicted of money laundering")]}),
                          actor="tester")
        fid = conn.execute("SELECT id FROM adverse_media_findings WHERE customer_id=?",
                           (customer_id,)).fetchone()["id"]
        _make_overdue(conn, customer_id)
        disposition_adverse_media_finding(conn, fid, org_id, status="not_relevant",
                                          note="Different person", actor="tester")
        assert _is_due(conn, org_id, customer_id)
        assert _latest(conn, customer_id)["next_review"] == OVERDUE

    def test_complete_review_writes_row_audit_and_moves_next_review(
            self, conn, org_id, customer_id):
        _make_overdue(conn, customer_id)
        rating = _latest(conn, customer_id)["rating"]
        rid = complete_periodic_review(conn, org_id, customer_id, "alice", "no_change", NOTE)
        rows = conn.execute("SELECT * FROM periodic_reviews WHERE customer_id=?",
                            (customer_id,)).fetchall()
        assert [r["id"] for r in rows] == [rid]
        assert (rows[0]["reviewer_name"], rows[0]["outcome"], rows[0]["note"]) == (
            "alice", "no_change", NOTE)
        audits = conn.execute("SELECT org_id FROM audit_log WHERE action='review.completed'"
                              " AND object_id=?", (customer_id,)).fetchall()
        assert len(audits) == 1 and audits[0]["org_id"] == org_id
        months = ruleset()["review_months"][rating]
        expected = (_today() + timedelta(days=30 * months)).isoformat()
        assert _latest(conn, customer_id)["next_review"] == expected == review_date_for(rating)
        assert not _is_due(conn, org_id, customer_id)
        assert [r["id"] for r in periodic_reviews(conn, customer_id, org_id)] == [rid]

    def test_risk_changed_reassesses_and_uses_new_tier_interval(
            self, conn, org_id, customer_id):
        # A confirmed adverse-media finding pushes the rating up; the review
        # then re-rates and the interval follows the resulting rating.
        _make_overdue(conn, customer_id)
        complete_periodic_review(conn, org_id, customer_id, "alice", "risk_changed", NOTE)
        latest = _latest(conn, customer_id)
        assert latest["next_review"] == review_date_for(latest["rating"])
        row = conn.execute("SELECT new_risk_rating FROM periodic_reviews").fetchone()
        assert row["new_risk_rating"] == latest["rating"]

    def test_short_note_rejected_and_nothing_written(self, conn, org_id, customer_id):
        _make_overdue(conn, customer_id)
        with pytest.raises(ValueError):
            complete_periodic_review(conn, org_id, customer_id, "alice", "no_change", "too short")
        assert conn.execute("SELECT COUNT(*) c FROM periodic_reviews").fetchone()["c"] == 0
        assert _latest(conn, customer_id)["next_review"] == OVERDUE

    def test_other_org_customer_not_found(self, conn, org_id, customer_id):
        other = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES"
            " ('Other','other','active','2026-01-01') RETURNING id").fetchone()["id"]
        with pytest.raises(LookupError):
            complete_periodic_review(conn, other, customer_id, "bob", "no_change", NOTE)


def _web_customer() -> int:
    from amlkit.db import connect
    c = connect(os.environ["AMLKIT_DB"])
    try:
        org = c.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()[0]
        return onboard(c, org_id=org, reference="C-PR-1", full_name="Layla Haddad",
                       actor="test").customer_id
    finally:
        c.close()


def _set_next_review(cid: int, value: str) -> None:
    c = sqlite3.connect(os.environ["AMLKIT_DB"])
    c.execute("UPDATE risk_assessments SET next_review=? WHERE customer_id=?", (value, cid))
    c.commit()
    c.close()


def _post_review(client, cid, note=NOTE, outcome="no_change"):
    client.get(f"/customers/{cid}")
    return client.post(f"/customers/{cid}/periodic-review", data={
        "outcome": outcome, "note": note, "csrf_token": _csrf(client)},
        follow_redirects=False)


class TestWeb:
    def test_overdue_badge_rendered_only_when_overdue(self, client):
        cid = _web_customer()
        assert "Overdue" not in client.get(f"/customers/{cid}").text
        _set_next_review(cid, OVERDUE)
        html = client.get(f"/customers/{cid}").text
        assert "Overdue" in html
        assert "Complete periodic review" in html

    def test_complete_review_clears_overdue_and_lists_review(self, client):
        cid = _web_customer()
        _set_next_review(cid, OVERDUE)
        r = _post_review(client, cid)
        assert r.status_code == 303
        html = client.get(f"/customers/{cid}").text
        assert "Overdue" not in html
        assert "Periodic reviews" in html
        assert NOTE in html and "alice" in html and "No change" in html
        c = sqlite3.connect(os.environ["AMLKIT_DB"])
        assert c.execute("SELECT COUNT(*) FROM periodic_reviews").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM audit_log WHERE action='review.completed'"
                         ).fetchone()[0] == 1

    def test_short_note_is_400(self, client):
        cid = _web_customer()
        assert _post_review(client, cid, note="short").status_code == 400

    def test_bad_outcome_is_400(self, client):
        cid = _web_customer()
        assert _post_review(client, cid, outcome="bogus").status_code == 400

    def test_missing_csrf_does_not_record(self, client):
        cid = _web_customer()
        client.post(f"/customers/{cid}/periodic-review",
                    data={"outcome": "no_change", "note": NOTE, "csrf_token": "bad"},
                    follow_redirects=False)
        c = sqlite3.connect(os.environ["AMLKIT_DB"])
        assert c.execute("SELECT COUNT(*) FROM periodic_reviews").fetchone()[0] == 0

    def test_other_orgs_customer_is_404(self, client):
        cid = _web_customer()
        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        other = TestClient(app)
        _register(other, "Other Firm", "bob", "bob@otherfirm.ae")
        assert _post_review(other, cid).status_code == 404
        c = sqlite3.connect(os.environ["AMLKIT_DB"])
        assert c.execute("SELECT COUNT(*) FROM periodic_reviews").fetchone()[0] == 0

    def test_officer_role_may_complete_review(self, client):
        cid = _web_customer()
        _add_operator(client, "olive", "olive@testfirm.ae", role="officer")
        client.post("/logout", data={"csrf_token": _csrf(client)})
        _login(client, "olive@testfirm.ae", "a-strong-password-2")
        assert _post_review(client, cid).status_code == 303


class TestMobile:
    def _cust(self):
        return _web_customer()

    def test_periodic_review_endpoint_writes_same_row(self, api):
        c, h = api
        cid = self._cust()
        _set_next_review(cid, OVERDUE)
        r = c.post(f"/api/v1/customers/{cid}/periodic-review", headers=h,
                   json={"outcome": "no_change", "note": NOTE})
        assert r.status_code == 200, r.text
        assert r.json()["next_review"] > _today().isoformat()
        db = sqlite3.connect(os.environ["AMLKIT_DB"])
        row = db.execute("SELECT outcome, note, reviewer_name FROM periodic_reviews").fetchall()
        assert row == [("no_change", NOTE, "alice")]

    def test_short_note_400_and_unknown_customer_404(self, api):
        c, h = api
        cid = self._cust()
        assert c.post(f"/api/v1/customers/{cid}/periodic-review", headers=h,
                      json={"outcome": "no_change", "note": "x"}).status_code == 400
        assert c.post("/api/v1/customers/99999/periodic-review", headers=h,
                      json={"outcome": "no_change", "note": NOTE}).status_code == 404

    def test_old_risk_route_no_longer_resets_review_date(self, api):
        c, h = api
        cid = self._cust()
        _set_next_review(cid, OVERDUE)
        r = c.post(f"/api/v1/customers/{cid}/risk", headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["next_review"] == OVERDUE
        db = sqlite3.connect(os.environ["AMLKIT_DB"])
        assert db.execute("SELECT COUNT(*) FROM periodic_reviews").fetchone()[0] == 0

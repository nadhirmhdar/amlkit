"""Cross-tenant / IDOR isolation tests for the mobile bearer-token JSON API.

The mobile API (amlkit/api/mobile.py) is the only non-browser way into every
customer, alert, report, transaction and document route, and authenticates
with a bearer token rather than a cookie session. Tenant isolation here is a
hard regulatory requirement: one DNFBP must never see or mutate another firm's
customer data. The existing test_mobile_api.py suite exercises only a single
org and never attempts a cross-org access.

This file fills that gap: it stands up TWO independently-registered orgs over
the JSON API and asserts that org B, holding a valid bearer token of its own,
cannot read or mutate any object owned by org A. Every route is expected to
treat a cross-tenant id as not found (404) or, for write-helpers that raise
ValueError on a mismatched owner, a clean 400 -- never a silent success and
never a 500. Assertions match the CURRENT behaviour; these tests pin it so a
future regression that drops an org_id filter fails loudly here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_api import _seed_sanctions_data  # noqa: E402


def _register_and_verify(client, *, org_name, name, email, password):
    r = client.post("/api/v1/auth/register-organization", json={
        "org_name": org_name, "name": name, "email": email, "password": password,
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "verification_required"
    verify_token = r.json()["dev_verification_token"]
    r2 = client.post("/api/v1/auth/verify-email", json={"token": verify_token})
    assert r2.status_code == 200, r2.text
    return {"Authorization": "Bearer " + r2.json()["token"]}


@pytest.fixture()
def two_orgs(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    c = TestClient(app)
    a = _register_and_verify(c, org_name="Alpha Firm", name="alice",
                             email="alice@alpha.ae", password="alpha-strong-pw-1")
    b = _register_and_verify(c, org_name="Bravo Firm", name="bob",
                             email="bob@bravo.ae", password="bravo-strong-pw-1")
    return c, a, b


def _make_customer(client, headers, *, reference, full_name="Ordinary Person",
                   customer_type="natural"):
    r = client.post("/api/v1/customers", headers=headers, json={
        "reference": reference, "full_name": full_name,
        "customer_type": customer_type,
    })
    assert r.status_code == 200, r.text
    return r.json()["customer_id"]


class TestCustomerIsolation:
    def test_org_b_cannot_read_org_a_customer(self, two_orgs):
        client, a, b = two_orgs
        cid = _make_customer(client, a, reference="A-CUST-1")
        assert client.get(f"/api/v1/customers/{cid}", headers=a).status_code == 200
        r = client.get(f"/api/v1/customers/{cid}", headers=b)
        assert r.status_code == 404, r.text

    def test_org_a_customer_absent_from_org_b_list(self, two_orgs):
        client, a, b = two_orgs
        _make_customer(client, a, reference="A-CUST-2")
        r = client.get("/api/v1/customers", headers=b)
        assert r.status_code == 200
        refs = [c["reference"] for c in r.json()["customers"]]
        assert "A-CUST-2" not in refs

    def test_org_b_cannot_read_org_a_customer_evidence(self, two_orgs):
        client, a, b = two_orgs
        cid = _make_customer(client, a, reference="A-CUST-3")
        r = client.get(f"/api/v1/customers/{cid}/evidence", headers=b)
        assert r.status_code == 404, r.text

    def test_org_b_cannot_close_org_a_customer(self, two_orgs):
        client, a, b = two_orgs
        cid = _make_customer(client, a, reference="A-CUST-4")
        client.post(f"/api/v1/customers/{cid}/close", headers=b)
        detail = client.get(f"/api/v1/customers/{cid}", headers=a)
        assert detail.status_code == 200
        assert detail.json()["customer"]["status"] != "closed"

    def test_org_b_cannot_reassess_org_a_customer_risk(self, two_orgs):
        client, a, b = two_orgs
        cid = _make_customer(client, a, reference="A-CUST-5")
        r = client.post(f"/api/v1/customers/{cid}/risk", headers=b)
        assert r.status_code == 404, r.text


class TestCaseFileIsolation:
    def test_org_b_cannot_add_note_to_org_a_customer(self, two_orgs):
        client, a, b = two_orgs
        cid = _make_customer(client, a, reference="A-CUST-6")
        r = client.post(f"/api/v1/customers/{cid}/notes", headers=b,
                        json={"body": "injected cross-tenant note"})
        assert r.status_code == 400, r.text

    def test_org_b_cannot_add_ubo_to_org_a_customer(self, two_orgs):
        client, a, b = two_orgs
        cid = _make_customer(client, a, reference="A-CUST-7",
                             full_name="Alpha Holding LLC", customer_type="legal")
        r = client.post(f"/api/v1/customers/{cid}/ubo", headers=b,
                        json={"person_name": "Injected Owner", "ownership_pct": 50})
        assert r.status_code == 400, r.text

    def test_org_b_cannot_add_transaction_to_org_a_customer(self, two_orgs):
        client, a, b = two_orgs
        cid = _make_customer(client, a, reference="A-CUST-8")
        r = client.post(f"/api/v1/customers/{cid}/transactions", headers=b, json={
            "direction": "in", "method": "cash", "amount": 1000.0,
        })
        assert r.status_code == 400, r.text

    def test_org_b_cannot_list_org_a_customer_transactions(self, two_orgs):
        client, a, b = two_orgs
        cid = _make_customer(client, a, reference="A-CUST-9")
        r = client.get(f"/api/v1/customers/{cid}/transactions", headers=b)
        assert r.status_code == 404, r.text

    def test_org_b_cannot_list_org_a_customer_documents(self, two_orgs):
        client, a, b = two_orgs
        cid = _make_customer(client, a, reference="A-CUST-10")
        r = client.get(f"/api/v1/customers/{cid}/documents", headers=b)
        assert r.status_code == 404, r.text


class TestAlertIsolation:
    def _sanctioned_customer_alert(self, client, headers):
        from tests.test_api import LISTED
        r = client.post("/api/v1/customers", headers=headers, json={
            "reference": "HIT-1", "full_name": LISTED, "customer_type": "natural",
        })
        assert r.status_code == 200, r.text
        cid = r.json()["customer_id"]
        alerts = client.get("/api/v1/alerts", headers=headers, params={"status": "open"})
        assert alerts.status_code == 200
        items = alerts.json()["alerts"]
        assert items, "expected a sanctions alert for a listed name"
        return cid, items[0]["id"]

    def test_org_b_cannot_read_org_a_alert(self, two_orgs):
        client, a, b = two_orgs
        _, alert_id = self._sanctioned_customer_alert(client, a)
        assert client.get(f"/api/v1/alerts/{alert_id}", headers=a).status_code == 200
        r = client.get(f"/api/v1/alerts/{alert_id}", headers=b)
        assert r.status_code == 404, r.text

    def test_org_a_alert_absent_from_org_b_queue(self, two_orgs):
        client, a, b = two_orgs
        _, alert_id = self._sanctioned_customer_alert(client, a)
        r = client.get("/api/v1/alerts", headers=b, params={"status": "open"})
        assert r.status_code == 200
        assert alert_id not in [al["id"] for al in r.json()["alerts"]]

    def test_org_b_cannot_disposition_org_a_alert(self, two_orgs):
        client, a, b = two_orgs
        _, alert_id = self._sanctioned_customer_alert(client, a)
        r = client.post(f"/api/v1/alerts/{alert_id}/disposition", headers=b, json={
            "status": "false_positive", "reason_code": "no_match",
            "narrative": "cross-tenant tamper attempt",
        })
        assert r.status_code == 400, r.text
        detail = client.get(f"/api/v1/alerts/{alert_id}", headers=a)
        assert detail.status_code == 200
        assert detail.json()["status"] == "open"

    def test_org_b_cannot_assign_org_a_alert(self, two_orgs):
        client, a, b = two_orgs
        _, alert_id = self._sanctioned_customer_alert(client, a)
        r = client.post(f"/api/v1/alerts/{alert_id}/assign", headers=b,
                        json={"operator": "bob"})
        assert r.status_code == 400, r.text


class TestReportIsolation:
    def _draft_report(self, client, headers, customer_id):
        r = client.post("/api/v1/reports", headers=headers, json={
            "customer_id": customer_id, "report_type": "STR",
            "reporting_entity_name": "Alpha Firm", "entity_reference": "RE-1",
            "reporter_name": "alice", "reporter_email": "alice@alpha.ae",
            "first_name": "Ordinary",
        })
        assert r.status_code == 200, r.text
        return r.json()["report_id"]

    def test_org_b_cannot_save_report_against_org_a_customer(self, two_orgs):
        client, a, b = two_orgs
        cid = _make_customer(client, a, reference="A-CUST-11")
        r = client.post("/api/v1/reports", headers=b, json={
            "customer_id": cid, "report_type": "STR",
            "reporting_entity_name": "Bravo Firm", "entity_reference": "RE-X",
            "reporter_name": "bob", "reporter_email": "bob@bravo.ae",
            "first_name": "Someone",
        })
        assert r.status_code == 404, r.text

    def test_org_b_cannot_read_org_a_report(self, two_orgs):
        client, a, b = two_orgs
        cid = _make_customer(client, a, reference="A-CUST-12")
        rid = self._draft_report(client, a, cid)
        assert client.get(f"/api/v1/reports/{rid}", headers=a).status_code == 200
        r = client.get(f"/api/v1/reports/{rid}", headers=b)
        assert r.status_code == 404, r.text

    def test_org_a_report_absent_from_org_b_list(self, two_orgs):
        client, a, b = two_orgs
        cid = _make_customer(client, a, reference="A-CUST-13")
        rid = self._draft_report(client, a, cid)
        r = client.get("/api/v1/reports", headers=b)
        assert r.status_code == 200
        assert rid not in [rep["id"] for rep in r.json()["reports"]]

    def test_org_b_cannot_submit_org_a_report(self, two_orgs):
        client, a, b = two_orgs
        cid = _make_customer(client, a, reference="A-CUST-14")
        rid = self._draft_report(client, a, cid)
        r = client.post(f"/api/v1/reports/{rid}/submit", headers=b)
        assert r.status_code == 404, r.text
        detail = client.get(f"/api/v1/reports/{rid}", headers=a)
        assert detail.status_code == 200
        assert detail.json()["status"] == "draft"

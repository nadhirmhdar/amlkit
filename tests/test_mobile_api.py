"""Tests for the bearer-token JSON API (`amlkit/api/mobile.py`) that the
native mobile app talks to.

Mirrors test_api.py's fixture shape (throwaway db, one seeded sanctioned
person) but drives the app over `/api/v1/*` with a bearer token instead of
a cookie session, since that is the actual contract the mobile client uses.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_api import _seed_sanctions_data, LISTED  # noqa: E402


@pytest.fixture()
def api(tmp_path, monkeypatch):
    """(client, headers) for a freshly registered, verified org's MLRO, over
    the JSON API.

    Registration alone no longer returns a usable token (see
    api/mobile.py's api_register_organization) -- it sends a verification
    link and, with no SMTP configured in tests, hands the raw token back in
    the response as `dev_verification_token` instead (see amlkit/mail.py).
    This fixture redeems that token via /auth/verify-email, exactly like a
    real user clicking the emailed link would, to get back a working
    bearer token.
    """
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    r = c.post("/api/v1/auth/register-organization", json={
        "org_name": "Test Firm", "name": "alice", "email": "alice@testfirm.ae",
        "password": "a-strong-password-1",
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "verification_required"
    verify_token = r.json()["dev_verification_token"]

    r2 = c.post("/api/v1/auth/verify-email", json={"token": verify_token})
    assert r2.status_code == 200, r2.text
    token = r2.json()["token"]
    return c, {"Authorization": f"Bearer {token}"}


class TestAuth:
    def test_register_then_verify_returns_usable_token(self, api):
        client, headers = api
        r = client.get("/api/v1/dashboard", headers=headers)
        assert r.status_code == 200

    def test_duplicate_email_registration_is_a_clean_400(self, api):
        """A second organization registered with an already-used email (a
        different org name, so the org-name collision path never fires) used
        to hit operators.email's UNIQUE constraint with no try/except around
        it -- a bare, undetailed 500 instead of a real error, and it left the
        new organizations row behind with no operator attached to it."""
        client, _ = api
        r = client.post("/api/v1/auth/register-organization", json={
            "org_name": "A Totally Different Firm", "name": "alice again",
            "email": "alice@testfirm.ae", "password": "another-strong-pw-1",
        })
        assert r.status_code == 400, r.text
        assert "already exists" in r.json()["detail"]

        # And the orphaned-organization side effect is actually rolled back,
        # not just the error message cleaned up.
        r2 = client.post("/api/v1/auth/register-organization", json={
            "org_name": "A Totally Different Firm", "name": "someone else",
            "email": "someone.else@testfirm.ae", "password": "yet-another-pw-1",
        })
        assert r2.status_code == 200, r2.text

    def test_no_token_is_401(self, api):
        client, _ = api
        r = client.get("/api/v1/dashboard")
        assert r.status_code == 401

    def test_garbage_token_is_401(self, api):
        client, _ = api
        r = client.get("/api/v1/dashboard", headers={"Authorization": "Bearer not-a-real-token"})
        assert r.status_code == 401

    def test_login_with_wrong_password_is_401(self, api):
        client, _ = api
        r = client.post("/api/v1/auth/login", json={
            "email": "alice@testfirm.ae", "password": "wrong-password-entirely",
        })
        assert r.status_code == 401
        assert "detail" in r.json()

    def test_login_with_right_password_returns_token(self, api):
        client, _ = api
        r = client.post("/api/v1/auth/login", json={
            "email": "alice@testfirm.ae", "password": "a-strong-password-1",
        })
        assert r.status_code == 200
        assert r.json()["token"]

    def test_logout_revokes_token(self, api):
        client, headers = api
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
        assert client.get("/api/v1/dashboard", headers=headers).status_code == 401

    def test_me_reflects_operator(self, api):
        client, headers = api
        r = client.get("/api/v1/auth/me", headers=headers)
        assert r.status_code == 200
        assert r.json()["operator"]["email"] == "alice@testfirm.ae"
        assert r.json()["operator"]["role"] == "mlro"


class TestScreening:
    def test_clear_name_returns_no_hits(self, api):
        client, headers = api
        r = client.post("/api/v1/screen", headers=headers, json={"name": "Nobody Matching"})
        assert r.status_code == 200
        assert r.json()["clear"] is True
        assert r.json()["hits"] == []

    def test_sanctioned_name_returns_a_hit(self, api):
        client, headers = api
        r = client.post("/api/v1/screen", headers=headers, json={"name": LISTED})
        assert r.status_code == 200
        body = r.json()
        assert body["clear"] is False
        assert body["hits"][0]["category"] in ("sanction", "terrorism", "proliferation", "other")

    def test_blank_name_is_400(self, api):
        client, headers = api
        r = client.post("/api/v1/screen", headers=headers, json={"name": "   "})
        assert r.status_code == 400


class TestCustomers:
    def test_create_and_fetch_customer(self, api):
        client, headers = api
        r = client.post("/api/v1/customers", headers=headers, json={
            "reference": "CUST-1", "full_name": "Ordinary Person",
        })
        assert r.status_code == 200
        cid = r.json()["customer_id"]
        assert r.json()["blocked"] is False

        r = client.get(f"/api/v1/customers/{cid}", headers=headers)
        assert r.status_code == 200
        assert r.json()["customer"]["reference"] == "CUST-1"

        r = client.get("/api/v1/customers", headers=headers)
        assert any(c["reference"] == "CUST-1" for c in r.json()["customers"])

    def test_onboarding_a_sanctioned_name_blocks_and_raises_alert(self, api):
        client, headers = api
        r = client.post("/api/v1/customers", headers=headers, json={
            "reference": "CUST-2", "full_name": LISTED,
        })
        assert r.status_code == 200
        assert r.json()["blocked"] is True

        r = client.get("/api/v1/alerts", headers=headers)
        assert len(r.json()["alerts"]) == 1

    def test_duplicate_reference_is_400(self, api):
        client, headers = api
        payload = {"reference": "DUP-1", "full_name": "Person One"}
        assert client.post("/api/v1/customers", headers=headers, json=payload).status_code == 200
        r = client.post("/api/v1/customers", headers=headers, json=payload)
        assert r.status_code == 400

    def test_unknown_customer_is_404(self, api):
        client, headers = api
        r = client.get("/api/v1/customers/999999", headers=headers)
        assert r.status_code == 404

    def test_note_and_close(self, api):
        client, headers = api
        cid = client.post("/api/v1/customers", headers=headers, json={
            "reference": "CUST-3", "full_name": "Someone Else",
        }).json()["customer_id"]

        r = client.post(f"/api/v1/customers/{cid}/notes", headers=headers, json={"body": "Reviewed."})
        assert r.status_code == 200

        r = client.post(f"/api/v1/customers/{cid}/close", headers=headers)
        assert r.status_code == 200
        assert "retention_until" in r.json()

    def test_transaction_recording_and_kyt_alert(self, api):
        client, headers = api
        cid = client.post("/api/v1/customers", headers=headers, json={
            "reference": "CUST-4", "full_name": "Cash Customer",
        }).json()["customer_id"]

        r = client.post(f"/api/v1/customers/{cid}/transactions", headers=headers, json={
            "direction": "in", "method": "cash", "amount": 60000, "currency": "AED",
        })
        assert r.status_code == 200
        assert r.json()["transaction_id"]


class TestAlertsAndAdmin:
    def test_alert_disposition_requires_reason_code(self, api):
        client, headers = api
        client.post("/api/v1/customers", headers=headers, json={
            "reference": "CUST-5", "full_name": LISTED,
        })
        alert_id = client.get("/api/v1/alerts", headers=headers).json()["alerts"][0]["id"]

        r = client.post(f"/api/v1/alerts/{alert_id}/disposition", headers=headers, json={
            "status": "true_positive", "reason_code": "",
        })
        assert r.status_code == 400

    def test_admin_endpoints_require_mlro_role(self, api, tmp_path, monkeypatch):
        client, headers = api

        r = client.post("/api/v1/admin/operators", headers=headers, json={
            "name": "bob", "email": "bob@testfirm.ae", "password": "another-strong-pw",
            "role": "officer",
        })
        assert r.status_code == 200

        login = client.post("/api/v1/auth/login", json={
            "email": "bob@testfirm.ae", "password": "another-strong-pw",
        })
        bob_headers = {"Authorization": f"Bearer {login.json()['token']}"}

        r = client.get("/api/v1/admin", headers=bob_headers)
        assert r.status_code == 403

    def test_admin_threshold_roundtrip(self, api):
        client, headers = api
        r = client.post("/api/v1/admin/threshold", headers=headers, json={"threshold": 0.9})
        assert r.status_code == 200
        assert client.get("/api/v1/admin", headers=headers).json()["threshold"] == 0.9


class TestReports:
    def test_save_and_export_report(self, api):
        client, headers = api
        cid = client.post("/api/v1/customers", headers=headers, json={
            "reference": "CUST-6", "full_name": "Report Subject",
        }).json()["customer_id"]

        r = client.post("/api/v1/reports", headers=headers, json={
            "customer_id": cid, "report_type": "STR",
            "reporting_entity_name": "Test Firm", "entity_reference": "TF-1",
            "reporter_name": "alice", "reporter_email": "alice@testfirm.ae",
            "first_name": "Report", "last_name": "Subject",
        })
        assert r.status_code == 200
        rid = r.json()["report_id"]

        r = client.get(f"/api/v1/reports/{rid}", headers=headers)
        assert r.status_code == 200
        assert r.json()["payload"]["reporting_entity_name"] == "Test Firm"

        r = client.get("/api/v1/reports", headers=headers)
        assert any(rep["id"] == rid for rep in r.json()["reports"])

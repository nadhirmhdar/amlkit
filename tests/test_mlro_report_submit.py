"""Issue #161: MLRO role enforcement on report submission.

Only the MLRO should be allowed to submit reports to the FIU.
Officers must receive 403 (mobile API) or be redirected with error (web app).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_api import _seed_sanctions_data  # noqa: E402


@pytest.fixture()
def api(tmp_path, monkeypatch):
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
    verify_token = r.json()["dev_verification_token"]
    r2 = c.post("/api/v1/auth/verify-email", json={"token": verify_token})
    assert r2.status_code == 200, r2.text
    mlro_token = r2.json()["token"]
    mlro_headers = {"Authorization": f"Bearer {mlro_token}"}

    r3 = c.post("/api/v1/admin/operators", headers=mlro_headers, json={
        "name": "bob", "email": "bob@testfirm.ae",
        "password": "another-strong-pw-1", "role": "officer",
    })
    assert r3.status_code == 200, r3.text
    login = c.post("/api/v1/auth/login", json={
        "email": "bob@testfirm.ae", "password": "another-strong-pw-1",
    })
    assert login.status_code == 200, login.text
    officer_headers = {"Authorization": f"Bearer {login.json()['token']}"}

    return c, mlro_headers, officer_headers


def _create_report(client, headers):
    cid = client.post("/api/v1/customers", headers=headers, json={
        "reference": "CUST-RPT", "full_name": "Report Subject",
    }).json()["customer_id"]
    r = client.post("/api/v1/reports", headers=headers, json={
        "customer_id": cid, "report_type": "STR",
        "reporting_entity_name": "Test Firm", "entity_reference": "TF-1",
        "reporter_name": "alice", "reporter_email": "alice@testfirm.ae",
        "first_name": "Report", "last_name": "Subject",
    })
    assert r.status_code == 200, r.text
    return r.json()["report_id"]


class TestMlroReportSubmitAPI:
    """Mobile/JSON API: POST /api/v1/reports/{id}/submit"""

    def test_officer_cannot_submit_report(self, api) -> None:
        client, mlro_headers, officer_headers = api
        rid = _create_report(client, mlro_headers)
        r = client.post(f"/api/v1/reports/{rid}/submit", headers=officer_headers)
        assert r.status_code == 403

    def test_mlro_can_submit_report(self, api) -> None:
        client, mlro_headers, _ = api
        rid = _create_report(client, mlro_headers)
        r = client.post(f"/api/v1/reports/{rid}/submit", headers=mlro_headers)
        assert r.status_code == 200

"""Issues #97 and #98: UBO ownership HTTP-level validation.

#97: Total UBO ownership >100% on POST /customers must return 422.
#98: Negative UBO percentage must return 422 (not 500).

These test the HTTP layer specifically — the ValueError from manager.py
must be caught and returned as 422, not bubble up as 500.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))



@pytest.fixture()
def api(tmp_path, monkeypatch):
    from tests.test_api import _seed_sanctions_data
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from amlkit.api.app import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.post("/api/v1/auth/register-organization", json={
        "org_name": "UBO Test Firm", "name": "tester",
        "email": "tester@ubofirm.ae", "password": "StrongPass123!", "invite_code": "test-invite",
    })
    assert r.status_code == 200, r.text
    verify_token = r.json()["dev_verification_token"]
    r2 = client.post("/api/v1/auth/verify-email", json={"token": verify_token})
    assert r2.status_code == 200, r2.text
    token = r2.json()["token"]
    from conftest import unlock_mobile_mfa  # p15: MLRO tokens start locked
    unlock_mobile_mfa(client, token)
    yield client, {"Authorization": f"Bearer {token}"}


class TestIssue97UboOver100:
    def test_onboard_ubo_sum_over_100_returns_422(self, api) -> None:
        client, headers = api
        r = client.post("/api/v1/customers", headers=headers, json={
            "reference": "CUST-OVER",
            "full_name": "Over Corp",
            "ubos": [
                {"person_name": "Owner A", "ownership_pct": 60.0},
                {"person_name": "Owner B", "ownership_pct": 50.0},
            ],
        })
        assert r.status_code == 422, f"Expected 422 for >100%, got {r.status_code}"

    def test_onboard_ubo_sum_exactly_100_ok(self, api) -> None:
        client, headers = api
        r = client.post("/api/v1/customers", headers=headers, json={
            "reference": "CUST-100",
            "full_name": "Exact Corp",
            "ubos": [
                {"person_name": "Owner A", "ownership_pct": 60.0},
                {"person_name": "Owner B", "ownership_pct": 40.0},
            ],
        })
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_add_ubo_exceeding_100_returns_422(self, api) -> None:
        client, headers = api
        r = client.post("/api/v1/customers", headers=headers, json={
            "reference": "CUST-PARTIAL",
            "full_name": "Partial Corp",
            "ubos": [{"person_name": "Owner A", "ownership_pct": 80.0}],
        })
        assert r.status_code == 200
        cid = r.json()["customer_id"]

        r2 = client.post(f"/api/v1/customers/{cid}/ubo", headers=headers, json={
            "person_name": "Owner B",
            "ownership_pct": 30.0,
        })
        assert r2.status_code == 422, f"Expected 422, got {r2.status_code}"


class TestIssue98NegativePercentage:
    def test_onboard_negative_ubo_pct_returns_422(self, api) -> None:
        client, headers = api
        r = client.post("/api/v1/customers", headers=headers, json={
            "reference": "CUST-NEG",
            "full_name": "Negative Corp",
            "ubos": [{"person_name": "Bad Owner", "ownership_pct": -10.0}],
        })
        assert r.status_code == 422, f"Expected 422 for negative pct, got {r.status_code}"

    def test_add_ubo_negative_pct_returns_422(self, api) -> None:
        client, headers = api
        r = client.post("/api/v1/customers", headers=headers, json={
            "reference": "CUST-OK",
            "full_name": "Good Corp",
        })
        assert r.status_code == 200
        cid = r.json()["customer_id"]

        r2 = client.post(f"/api/v1/customers/{cid}/ubo", headers=headers, json={
            "person_name": "Bad Owner",
            "ownership_pct": -5.0,
        })
        assert r2.status_code == 422, f"Expected 422, got {r2.status_code}"

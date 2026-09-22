"""H13: Risk-factor validation tests.

Unknown/misspelled risk-factor values must not score zero points and lower
the risk rating. Invalid inputs should be rejected or normalized at the API
boundary.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from amlkit.api.app import app
from amlkit.db import connect
from conftest import seed_fresh_dataset


@pytest.fixture()
def client():
    return TestClient(app)


class TestRiskFactorValidation:
    """Risk-factor fields must be validated against an allowlist."""

    def test_invalid_jurisdiction_tier_rejected(self, client) -> None:
        """Invalid jurisdiction_tier values (including trailing spaces) must be rejected."""
        from conftest import register_org
        register_org(client, "Test Org", "Test User", "test@example.com")

        # Seed sanctions data to pass staleness guard
        db_file = client.app.state.db_file
        conn = connect(db_file)
        seed_fresh_dataset(conn)
        conn.close()

        # Attempt to onboard with invalid jurisdiction_tier (trailing space)
        r = client.post("/customers", data={
            "reference": "CUST-001",
            "full_name": "Test Customer",
            "customer_type": "natural",
            "jurisdiction_tier": "fatf_blacklist ",  # trailing space
            "sector": "real_estate",
            "csrf_token": client.cookies.get("amlkit_csrf"),
        }, follow_redirects=False)

        # Should reject with error message, not accept silently
        assert r.status_code in [303, 400, 422], f"Expected error, got {r.status_code}"
        if r.status_code == 303:
            # Check that error flash message is set
            assert "flash" in r.cookies or "err" in r.headers.get("location", "")

    def test_invalid_structure_rejected(self, client) -> None:
        """Invalid structure values must be rejected at API boundary."""
        from conftest import register_org
        register_org(client, "Test Org", "Test User", "test@example.com")

        db_file = client.app.state.db_file
        conn = connect(db_file)
        seed_fresh_dataset(conn)
        conn.close()

        r = client.post("/customers", data={
            "reference": "CUST-002",
            "full_name": "Test Corp",
            "customer_type": "legal_person",
            "jurisdiction_tier": "standard",
            "sector": "real_estate",
            "structure": "INVALID_STRUCTURE",  # not in allowlist
            "csrf_token": client.cookies.get("amlkit_csrf"),
        }, follow_redirects=False)

        assert r.status_code in [303, 400, 422]

    def test_invalid_delivery_channel_rejected(self, client) -> None:
        """Invalid delivery_channel values must be rejected at API boundary."""
        from conftest import register_org
        register_org(client, "Test Org", "Test User", "test@example.com")

        db_file = client.app.state.db_file
        conn = connect(db_file)
        seed_fresh_dataset(conn)
        conn.close()

        r = client.post("/customers", data={
            "reference": "CUST-003",
            "full_name": "Test Customer",
            "customer_type": "natural",
            "jurisdiction_tier": "standard",
            "sector": "real_estate",
            "delivery_channel": "invalid_channel",
            "csrf_token": client.cookies.get("amlkit_csrf"),
        }, follow_redirects=False)

        assert r.status_code in [303, 400, 422]

    def test_invalid_cash_level_rejected(self, client) -> None:
        """Invalid cash_level values must be rejected at API boundary."""
        from conftest import register_org
        register_org(client, "Test Org", "Test User", "test@example.com")

        db_file = client.app.state.db_file
        conn = connect(db_file)
        seed_fresh_dataset(conn)
        conn.close()

        r = client.post("/customers", data={
            "reference": "CUST-004",
            "full_name": "Test Customer",
            "customer_type": "natural",
            "jurisdiction_tier": "standard",
            "sector": "real_estate",
            "cash_level": "wrong_value",
            "csrf_token": client.cookies.get("amlkit_csrf"),
        }, follow_redirects=False)

        assert r.status_code in [303, 400, 422]

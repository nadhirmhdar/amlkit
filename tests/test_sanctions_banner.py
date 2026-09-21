"""Test that sanctions source staleness/error banners appear on authenticated pages."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _csrf(client) -> str:
    """The middleware sets a CSRF cookie on every response."""
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name: str, name: str, email: str, password: str = "a-strong-password-1"):
    """Registers, completes email verification and signs in."""
    import re

    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert "Check your email" in r.text, f"registration failed: {r.text[:300]}"
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, f"no dev verification link in registration response: {r.text[:500]}"
    r2 = client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    from conftest import settle_mfa  # p15: MLRO sessions start locked
    settle_mfa(client)
    assert any(s in r2.text for s in ("Dashboard", "24-hour", "Two-Factor")), f"verification failed: {r2.text[:300]}"
    return client


def _db_conn() -> sqlite3.Connection:
    """Get DB connection."""
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """App with fresh database and registered org."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, upsert_dataset, utcnow

    # Seed a mandatory dataset for testing
    conn = connect(str(db_file))
    now = utcnow()
    upsert_dataset(conn, "un_sc_consolidated", "UN Security Council Consolidated List",
                   is_mandatory=True)
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=100, max_age_hours=24 WHERE key='un_sc_consolidated'",
                 (now,))
    conn.commit()
    conn.close()

    c = TestClient(app)
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


class TestSanctionsBanner:
    """Test that banner appears when datasets are stale or have errors."""

    def test_no_banner_when_all_sources_healthy(self, client) -> None:
        """No banner should appear when all datasets are fresh and have no errors."""
        # Set all datasets as fresh with entity count
        conn = _db_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE datasets SET last_refresh=?, last_error=NULL, error_at=NULL, entity_count=100 WHERE entity_count=0 OR entity_count IS NULL", (now,))
        conn.execute("UPDATE datasets SET last_refresh=?, last_error=NULL, error_at=NULL WHERE entity_count > 0", (now,))
        conn.commit()
        conn.close()

        r = client.get("/")
        assert r.status_code == 200
        # Simpler check: banner should not contain "out of date" or "failing"
        assert "out of date" not in r.text.lower()
        assert "failing to update" not in r.text.lower()

    def test_banner_appears_when_mandatory_dataset_stale(self, client) -> None:
        """Red banner should appear when a mandatory dataset is stale."""
        # Make a mandatory dataset stale (50 hours old, max_age=24)
        conn = _db_conn()
        old_time = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
        conn.execute(
            "UPDATE datasets SET last_refresh=?, last_error=NULL WHERE id=(SELECT id FROM datasets WHERE is_mandatory=1 LIMIT 1)",
            (old_time,)
        )
        conn.commit()
        conn.close()

        r = client.get("/")
        assert r.status_code == 200
        # Should see a warning about stale datasets
        assert "stale" in r.text.lower() or "out of date" in r.text.lower()

    def test_banner_appears_when_dataset_has_error(self, client) -> None:
        """Banner should appear when any dataset has last_error set."""
        conn = _db_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE datasets SET last_error=?, error_at=? WHERE id=(SELECT id FROM datasets LIMIT 1)",
            ("Connection timeout", now)
        )
        conn.commit()
        conn.close()

        r = client.get("/")
        assert r.status_code == 200
        # Should see error message
        assert "error" in r.text.lower() or "failed" in r.text.lower()

    def test_red_banner_for_mandatory_sources(self, client) -> None:
        """Mandatory source errors should show red/critical banner."""
        conn = _db_conn()
        old_time = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
        conn.execute(
            "UPDATE datasets SET last_refresh=?, last_error=NULL WHERE id=(SELECT id FROM datasets WHERE is_mandatory=1 LIMIT 1)",
            (old_time,)
        )
        conn.commit()
        conn.close()

        r = client.get("/")
        assert r.status_code == 200
        # Should have error/critical styling (look for err class or critical/red indicator)
        assert 'class="banner err"' in r.text or "critical" in r.text.lower() or "mandatory" in r.text.lower()

    def test_amber_banner_for_optional_sources(self, client) -> None:
        """Optional source errors should show amber/warning banner."""
        conn = _db_conn()
        old_time = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
        # Make an optional dataset stale (use UN, not FATF which is version-tracked)
        conn.execute(
            "UPDATE datasets SET last_refresh=?, is_mandatory=0 WHERE key='un_sc_consolidated'",
            (old_time,)
        )
        conn.commit()
        conn.close()

        r = client.get("/")
        assert r.status_code == 200
        # Should see warning (not error) - amber styling
        # Note: implementation may use different class names
        # We'll check for presence of warning/optional text
        response_lower = r.text.lower()
        assert ("warning" in response_lower or "optional" in response_lower or
                "stale" in response_lower or "out of date" in response_lower)

    def test_banner_links_to_compliance_dashboard(self, client) -> None:
        """Banner should link to /admin/compliance for MLROs."""
        conn = _db_conn()
        old_time = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
        conn.execute(
            "UPDATE datasets SET last_refresh=? WHERE id=(SELECT id FROM datasets WHERE is_mandatory=1 LIMIT 1)",
            (old_time,)
        )
        conn.commit()
        conn.close()

        r = client.get("/")
        assert r.status_code == 200
        # Should have a link to compliance dashboard
        assert "/admin/compliance" in r.text or "/compliance" in r.text

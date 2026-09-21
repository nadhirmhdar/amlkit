"""Tests for EU FSF token configuration warnings in admin dashboard."""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register_and_login(client, org_name: str, name: str, email: str, password: str = "a-strong-password-1"):
    """Registers, verifies email, and logs in as MLRO."""
    import re

    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client), "invite_code": "test-invite",
    }, follow_redirects=True)
    assert "Check your email" in r.text
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m
    client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    from conftest import settle_mfa  # p15: MLRO sessions start locked
    settle_mfa(client)
    return client


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """App with fresh database, registered org, logged in as MLRO."""
    from amlkit.db import connect

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    # Initialize database with eu_sanctions dataset
    conn = connect(str(db_file))
    from amlkit.db import upsert_dataset
    upsert_dataset(conn, "eu_sanctions", "EU Consolidated Sanctions List", is_mandatory=False)
    conn.commit()
    conn.close()

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register_and_login(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


class TestEuTokenWarning:
    """Tests for EU FSF token configuration warnings."""

    def test_warning_shown_when_token_unset(self, client, monkeypatch) -> None:
        """Admin dashboard shows warning when AMLKIT_EU_FSF_TOKEN is unset."""
        monkeypatch.delenv("AMLKIT_EU_FSF_TOKEN", raising=False)
        r = client.get("/admin")
        assert r.status_code == 200
        assert "EU Sanctions Configuration" in r.text
        assert "demo token" in r.text
        assert "webgate.ec.europa.eu/fsd/fsf" in r.text

    def test_warning_shown_when_using_demo_token(self, client, monkeypatch) -> None:
        """Admin dashboard shows warning when using the default demo token."""
        demo_token = "dG9rZW4tMjAxNy0xMS0xMw"
        monkeypatch.setenv("AMLKIT_EU_FSF_TOKEN", demo_token)
        r = client.get("/admin")
        assert r.status_code == 200
        assert "EU Sanctions Configuration" in r.text
        assert "demo token" in r.text

    def test_no_warning_when_custom_token_set_and_no_errors(self, client, monkeypatch) -> None:
        """No warning when custom token is set and EU refresh is working."""
        monkeypatch.setenv("AMLKIT_EU_FSF_TOKEN", "custom-production-token-12345")
        r = client.get("/admin")
        assert r.status_code == 200
        assert "EU Sanctions Configuration" not in r.text

    def test_warning_shown_when_eu_refresh_failing_over_3_days(self, client, monkeypatch) -> None:
        """Warning shown when EU refresh has been failing for >3 days."""
        monkeypatch.setenv("AMLKIT_EU_FSF_TOKEN", "custom-production-token-12345")

        # Set error in database that's 4 days old
        conn = _db()
        four_days_ago = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
        conn.execute(
            "UPDATE datasets SET last_error=?, error_at=? WHERE key='eu_sanctions'",
            ("401 Unauthorized - invalid token", four_days_ago)
        )
        conn.commit()
        conn.close()

        r = client.get("/admin")
        assert r.status_code == 200
        assert "EU Sanctions Configuration" in r.text
        assert ("failing for >3 days" in r.text or "failing for &gt;3 days" in r.text)
        assert "401 Unauthorized" in r.text

    def test_no_warning_when_eu_refresh_recently_failed(self, client, monkeypatch) -> None:
        """No warning when EU refresh failed but <3 days ago (transient failure)."""
        monkeypatch.setenv("AMLKIT_EU_FSF_TOKEN", "custom-production-token-12345")

        # Set error in database that's only 1 day old
        conn = _db()
        one_day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        conn.execute(
            "UPDATE datasets SET last_error=?, error_at=? WHERE key='eu_sanctions'",
            ("500 Internal Server Error", one_day_ago)
        )
        conn.commit()
        conn.close()

        r = client.get("/admin")
        assert r.status_code == 200
        # No warning for transient failures <3 days
        assert "EU Sanctions Configuration" not in r.text

    def test_no_warning_after_successful_refresh(self, client, monkeypatch) -> None:
        """No warning after a previously failing refresh succeeds (error cleared)."""
        monkeypatch.setenv("AMLKIT_EU_FSF_TOKEN", "custom-production-token-12345")

        # Simulate successful refresh by clearing error
        conn = _db()
        conn.execute(
            "UPDATE datasets SET last_error=NULL, error_at=NULL WHERE key='eu_sanctions'"
        )
        conn.commit()
        conn.close()

        r = client.get("/admin")
        assert r.status_code == 200
        assert "EU Sanctions Configuration" not in r.text

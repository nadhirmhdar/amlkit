"""Tests for admin route RBAC enforcement - Issue #99.

POST /admin/* routes should return HTTP 403 for officer role, not 200 with
error message. Proper REST semantics: authorization failures are 403, not
success responses with error payloads.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register_and_login(client, org_name: str, name: str, email: str, password: str = "a-strong-password-1"):
    """Registers, verifies email, and logs in."""
    import re

    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert "Check your email" in r.text
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m
    client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    return client


def _add_operator(client, name: str, email: str, password: str = "a-strong-password-2",
                  role: str = "officer") -> None:
    """MLRO creates a second operator."""
    client.post("/admin/operators", data={
        "name": name, "email": email, "password": password, "role": role,
        "csrf_token": _csrf(client),
    })


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

    conn = connect(str(db_file))
    conn.commit()
    conn.close()

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register_and_login(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


class TestAdminRBAC:
    """Tests for admin POST route RBAC enforcement."""

    def test_mlro_can_set_threshold(self, client) -> None:
        """MLRO can POST to /admin/threshold."""
        r = client.post("/admin/threshold", data={
            "threshold": "0.85", "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r.status_code in (303, 200)  # Redirect or success

    def test_officer_cannot_set_threshold(self, client) -> None:
        """Officer gets 403 on POST /admin/threshold."""
        # Create officer and log in as them
        _add_operator(client, "bob1", "bob1@testfirm.ae", role="officer")
        client.cookies.delete("amlkit_session")
        client.post("/login", data={
            "email": "bob1@testfirm.ae", "password": "a-strong-password-2",
            "csrf_token": _csrf(client),
        })

        r = client.post("/admin/threshold", data={
            "threshold": "0.85", "csrf_token": _csrf(client),
        }, follow_redirects=False)
        # Should be 403, not 303 redirect or 200 with error
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"

    def test_officer_cannot_create_operator(self, client) -> None:
        """Officer gets 403 on POST /admin/operators."""
        _add_operator(client, "bob2", "bob2@testfirm.ae", role="officer")
        client.cookies.delete("amlkit_session")
        client.post("/login", data={
            "email": "bob2@testfirm.ae", "password": "a-strong-password-2",
            "csrf_token": _csrf(client),
        })

        r = client.post("/admin/operators", data={
            "name": "charlie", "email": "charlie@testfirm.ae",
            "password": "a-strong-password-3", "role": "officer",
            "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r.status_code == 403

    def test_officer_cannot_reset_password(self, client) -> None:
        """Officer gets 403 on POST /admin/operators/{id}/reset-password."""
        _add_operator(client, "bob3", "bob3@testfirm.ae", role="officer")

        # Get bob3's operator ID
        conn = _db()
        bob_id = conn.execute("SELECT id FROM operators WHERE email='bob3@testfirm.ae'").fetchone()["id"]
        conn.close()

        # Log in as bob3
        client.cookies.delete("amlkit_session")
        client.post("/login", data={
            "email": "bob3@testfirm.ae", "password": "a-strong-password-2",
            "csrf_token": _csrf(client),
        })

        r = client.post(f"/admin/operators/{bob_id}/reset-password", data={
            "new_password": "new-password-123", "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r.status_code == 403

    def test_officer_cannot_deactivate_operator(self, client) -> None:
        """Officer gets 403 on POST /admin/operators/{id}/deactivate."""
        _add_operator(client, "bob4", "bob4@testfirm.ae", role="officer")
        _add_operator(client, "charlie4", "charlie4@testfirm.ae", role="officer")

        conn = _db()
        charlie_id = conn.execute("SELECT id FROM operators WHERE email='charlie4@testfirm.ae'").fetchone()["id"]
        conn.close()

        # Log in as bob4 (officer)
        client.cookies.delete("amlkit_session")
        client.post("/login", data={
            "email": "bob4@testfirm.ae", "password": "a-strong-password-2",
            "csrf_token": _csrf(client),
        })

        r = client.post(f"/admin/operators/{charlie_id}/deactivate", data={
            "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r.status_code == 403

    def test_officer_cannot_refresh_sanctions(self, client) -> None:
        """Officer gets 403 on POST /admin/refresh."""
        _add_operator(client, "bob5", "bob5@testfirm.ae", role="officer")
        client.cookies.delete("amlkit_session")
        client.post("/login", data={
            "email": "bob5@testfirm.ae", "password": "a-strong-password-2",
            "csrf_token": _csrf(client),
        })

        r = client.post("/admin/refresh", data={
            "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r.status_code == 403

    def test_officer_cannot_rescreen(self, client) -> None:
        """Officer gets 403 on POST /admin/rescreen."""
        _add_operator(client, "bob6", "bob6@testfirm.ae", role="officer")
        client.cookies.delete("amlkit_session")
        client.post("/login", data={
            "email": "bob6@testfirm.ae", "password": "a-strong-password-2",
            "csrf_token": _csrf(client),
        })

        r = client.post("/admin/rescreen", data={
            "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r.status_code == 403

    def test_officer_cannot_update_rule_config(self, client) -> None:
        """Officer gets 403 on POST /admin/rule-config."""
        _add_operator(client, "bob7", "bob7@testfirm.ae", role="officer")
        client.cookies.delete("amlkit_session")
        client.post("/login", data={
            "email": "bob7@testfirm.ae", "password": "a-strong-password-2",
            "csrf_token": _csrf(client),
        })

        r = client.post("/admin/rule-config", data={
            "large_cash_threshold_aed": "50000",
            "structuring_window_days": "7",
            "velocity_window_hours": "24",
            "velocity_max_count": "3",
            "high_risk_countries": "AF, IR",
            "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r.status_code == 403

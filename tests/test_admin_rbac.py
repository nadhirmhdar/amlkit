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
        "csrf_token": _csrf(client), "invite_code": "test-invite",
    }, follow_redirects=True)
    assert "Check your email" in r.text
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m
    client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    from conftest import settle_mfa  # p15: MLRO sessions start locked
    settle_mfa(client)
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
        from conftest import settle_mfa  # p15: MLRO sessions start locked
        settle_mfa(client)

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
        from conftest import settle_mfa  # p15: MLRO sessions start locked
        settle_mfa(client)

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
        from conftest import settle_mfa  # p15: MLRO sessions start locked
        settle_mfa(client)

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
        from conftest import settle_mfa  # p15: MLRO sessions start locked
        settle_mfa(client)

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
        from conftest import settle_mfa  # p15: MLRO sessions start locked
        settle_mfa(client)

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
        from conftest import settle_mfa  # p15: MLRO sessions start locked
        settle_mfa(client)

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
        from conftest import settle_mfa  # p15: MLRO sessions start locked
        settle_mfa(client)

        r = client.post("/admin/rule-config", data={
            "large_cash_threshold_aed": "50000",
            "structuring_window_days": "7",
            "velocity_window_hours": "24",
            "velocity_max_count": "3",
            "high_risk_countries": "AF, IR",
            "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r.status_code == 403

    def test_mlro_rule_config_page_renders(self, client) -> None:
        """GET /admin/rule-config renders the configuration form body.

        Regression test: the template previously declared {% block content %}
        while base.html renders {% block body %}, so the page rendered blank
        (200 OK, empty body) for every MLRO.
        """
        r = client.get("/admin/rule-config")
        assert r.status_code == 200
        assert "Transaction Monitoring Rules" in r.text
        assert "large_cash_threshold_aed" in r.text


class TestMlroLockout:
    """Regression tests for finding #8 (2026-09-21 deployed-site review):
    an org's only active MLRO could deactivate themselves (or the last
    other active MLRO) with no reactivate route or UI, losing policy
    upload, operator management, resets and refresh until someone edited
    the database directly."""

    def test_solo_mlro_cannot_deactivate_self(self, client) -> None:
        """The `client` fixture registers alice as the org's only MLRO."""
        alice_id = _db().execute(
            "SELECT id FROM operators WHERE email='alice@testfirm.ae'"
        ).fetchone()["id"]

        r = client.post(f"/admin/operators/{alice_id}/deactivate", data={
            "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r.status_code == 303

        row = _db().execute("SELECT is_active FROM operators WHERE id=?", (alice_id,)).fetchone()
        assert row["is_active"] == 1, "the org's only active MLRO must not be deactivated"

    def test_deactivating_last_active_mlro_is_blocked_even_by_another_mlro(self, client) -> None:
        """Two MLROs: deactivating the second-to-last is fine, but the org
        must never be left with zero active MLROs."""
        _add_operator(client, "bob8", "bob8@testfirm.ae", role="mlro")
        conn = _db()
        alice_id = conn.execute("SELECT id FROM operators WHERE email='alice@testfirm.ae'").fetchone()["id"]
        bob_id = conn.execute("SELECT id FROM operators WHERE email='bob8@testfirm.ae'").fetchone()["id"]

        # Alice deactivates Bob: one MLRO (Alice) remains active -- allowed.
        r1 = client.post(f"/admin/operators/{bob_id}/deactivate", data={
            "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r1.status_code == 303
        assert _db().execute("SELECT is_active FROM operators WHERE id=?", (bob_id,)).fetchone()["is_active"] == 0

        # Alice tries to deactivate herself: she is now the last active MLRO -- blocked.
        r2 = client.post(f"/admin/operators/{alice_id}/deactivate", data={
            "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r2.status_code == 303
        assert _db().execute("SELECT is_active FROM operators WHERE id=?", (alice_id,)).fetchone()["is_active"] == 1

    def test_deactivating_an_officer_is_unaffected(self, client) -> None:
        """The last-MLRO guard must not block deactivating a non-MLRO."""
        _add_operator(client, "charlie8", "charlie8@testfirm.ae", role="officer")
        charlie_id = _db().execute(
            "SELECT id FROM operators WHERE email='charlie8@testfirm.ae'"
        ).fetchone()["id"]

        r = client.post(f"/admin/operators/{charlie_id}/deactivate", data={
            "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r.status_code == 303
        assert _db().execute(
            "SELECT is_active FROM operators WHERE id=?", (charlie_id,)
        ).fetchone()["is_active"] == 0

    def test_officer_cannot_reactivate_operator(self, client) -> None:
        """POST /admin/operators/{id}/reactivate is MLRO-only, like deactivate."""
        _add_operator(client, "dave8", "dave8@testfirm.ae", role="officer")
        client.cookies.delete("amlkit_session")
        client.post("/login", data={
            "email": "dave8@testfirm.ae", "password": "a-strong-password-2",
            "csrf_token": _csrf(client),
        })
        from conftest import settle_mfa  # p15: MLRO sessions start locked
        settle_mfa(client)

        r = client.post("/admin/operators/1/reactivate", data={
            "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r.status_code == 403

    def test_mlro_can_reactivate_a_deactivated_operator(self, client) -> None:
        """A deactivated operator can be brought back via the new reactivate
        route, and can log in again afterwards."""
        _add_operator(client, "erin8", "erin8@testfirm.ae", role="officer")
        erin_id = _db().execute(
            "SELECT id FROM operators WHERE email='erin8@testfirm.ae'"
        ).fetchone()["id"]

        client.post(f"/admin/operators/{erin_id}/deactivate", data={
            "csrf_token": _csrf(client),
        })
        assert _db().execute(
            "SELECT is_active FROM operators WHERE id=?", (erin_id,)
        ).fetchone()["is_active"] == 0

        r = client.post(f"/admin/operators/{erin_id}/reactivate", data={
            "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r.status_code == 303
        assert _db().execute(
            "SELECT is_active FROM operators WHERE id=?", (erin_id,)
        ).fetchone()["is_active"] == 1

        # Erin can log in again now.
        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        fresh = TestClient(app)
        fresh.get("/login")
        login_r = fresh.post("/login", data={
            "email": "erin8@testfirm.ae", "password": "a-strong-password-2",
            "csrf_token": _csrf(fresh),
        }, follow_redirects=True)
        assert login_r.status_code == 200
        assert "Invalid" not in login_r.text

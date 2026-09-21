"""Tests for p11: auth_log.ip population.

Verifies that login attempts (success and failure) and logout actions
record the client IP address in the auth_log table for forensic investigation.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _seed_sanctions_data(db_file) -> None:
    from amlkit.db import connect, upsert_dataset, utcnow
    conn = connect(db_file)
    ds = upsert_dataset(conn, "test_list", "Test Sanctions List", is_mandatory=True)
    conn.commit()
    conn.close()


def _register(client, org_name, name, email, password="a-strong-password-1"):
    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client), "invite_code": "test-invite",
    }, follow_redirects=True)
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    if m:
        client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    return client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    c = TestClient(app)
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


def _db():
    from amlkit.db import connect
    return connect(os.environ["AMLKIT_DB"])


def test_login_success_records_ip(client):
    """Successful login should record client IP in auth_log."""
    # Logout first
    client.post("/logout", data={"csrf_token": _csrf(client)})

    # Login again
    r = client.post("/login", data={
        "email": "alice@testfirm.ae",
        "password": "a-strong-password-1",
        "csrf_token": _csrf(client),
    }, follow_redirects=False)
    assert r.status_code == 303

    # Check auth_log has IP for login_success
    conn = _db()
    log_entry = conn.execute(
        "SELECT ip, event FROM auth_log WHERE event='login_success' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert log_entry is not None
    assert log_entry["event"] == "login_success"
    assert log_entry["ip"] is not None, "IP should be recorded for successful login"
    # TestClient uses 127.0.0.1 or testclient
    assert log_entry["ip"] in ("127.0.0.1", "testclient")


def test_login_failure_records_ip(client):
    """Failed login should record client IP in auth_log."""
    r = client.post("/login", data={
        "email": "alice@testfirm.ae",
        "password": "wrong-password",
        "csrf_token": _csrf(client),
    }, follow_redirects=False)
    assert r.status_code == 200  # Returns login page with error

    # Check auth_log has IP for login_failure
    conn = _db()
    log_entry = conn.execute(
        "SELECT ip, event, detail FROM auth_log WHERE event='login_failure' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert log_entry is not None
    assert log_entry["event"] == "login_failure"
    assert log_entry["ip"] is not None, "IP should be recorded for failed login"
    assert log_entry["ip"] in ("127.0.0.1", "testclient")
    # Detail should have reason
    assert "bad_password" in log_entry["detail"]


def test_login_failure_unknown_email_records_ip(client):
    """Failed login with unknown email should record IP."""
    r = client.post("/login", data={
        "email": "nonexistent@example.com",
        "password": "any-password",
        "csrf_token": _csrf(client),
    }, follow_redirects=False)
    assert r.status_code == 200

    conn = _db()
    log_entry = conn.execute(
        "SELECT ip, event, email_attempted, detail FROM auth_log WHERE email_attempted='nonexistent@example.com' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert log_entry is not None
    assert log_entry["event"] == "login_failure"
    assert log_entry["ip"] is not None
    assert log_entry["ip"] in ("127.0.0.1", "testclient")
    assert "unknown_email" in log_entry["detail"]


def test_logout_records_ip(client):
    """Logout should record client IP in auth_log."""
    r = client.post("/logout")
    # Logout doesn't require CSRF in current implementation, just redirects
    assert r.status_code in (200, 303)  # May be 200 if no session or 303 redirect

    conn = _db()
    log_entry = conn.execute(
        "SELECT ip, event FROM auth_log WHERE event='logout' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert log_entry is not None
    assert log_entry["event"] == "logout"
    assert log_entry["ip"] is not None, "IP should be recorded for logout"
    assert log_entry["ip"] in ("127.0.0.1", "testclient")

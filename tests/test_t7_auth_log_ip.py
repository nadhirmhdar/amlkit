"""Test t7: Verify auth_log.ip populated on login success and failure.

Confirms that p11's auth_log.ip implementation correctly records client IP
for both successful and failed login attempts.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


def test_login_success_populates_ip(conn, org_id):
    """Successful login should populate IP in auth_log."""
    from amlkit.auth import login, set_password
    from amlkit.db import utcnow

    # Create operator
    now = utcnow()
    conn.execute(
        "INSERT INTO operators (name, email, org_id, role, is_active, email_verified_at, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        ("Test User", "test@example.com", org_id, "officer", 1, now, now)
    )
    conn.commit()
    op_id = conn.execute("SELECT id FROM operators WHERE email=?", ("test@example.com",)).fetchone()["id"]

    # Set password
    set_password(conn, op_id, "ValidPass123!")

    # Login with IP
    raw_token, session_info = login(conn, "test@example.com", "ValidPass123!", ip="192.168.1.100")

    # Verify auth_log entry has IP
    log_entry = conn.execute(
        "SELECT ip, event FROM auth_log WHERE event='login_success' AND email_attempted=? ORDER BY id DESC LIMIT 1",
        ("test@example.com",)
    ).fetchone()

    assert log_entry is not None
    assert log_entry["event"] == "login_success"
    assert log_entry["ip"] == "192.168.1.100", "IP should be populated in auth_log for successful login"


def test_login_failure_populates_ip(conn, org_id):
    """Failed login should populate IP in auth_log."""
    from amlkit.auth import AuthError, login, set_password
    from amlkit.db import utcnow

    # Create operator
    now = utcnow()
    conn.execute(
        "INSERT INTO operators (name, email, org_id, role, is_active, email_verified_at, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        ("Test User", "test2@example.com", org_id, "officer", 1, now, now)
    )
    conn.commit()
    op_id = conn.execute("SELECT id FROM operators WHERE email=?", ("test2@example.com",)).fetchone()["id"]

    # Set password
    set_password(conn, op_id, "ValidPass123!")

    # Attempt login with wrong password
    with pytest.raises(AuthError):
        login(conn, "test2@example.com", "WrongPassword!", ip="10.0.0.50")

    # Verify auth_log entry has IP
    log_entry = conn.execute(
        "SELECT ip, event FROM auth_log WHERE event='login_failure' AND email_attempted=? ORDER BY id DESC LIMIT 1",
        ("test2@example.com",)
    ).fetchone()

    assert log_entry is not None
    assert log_entry["event"] == "login_failure"
    assert log_entry["ip"] == "10.0.0.50", "IP should be populated in auth_log for failed login"

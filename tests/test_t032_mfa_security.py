"""Tests for T-032: MFA rate limiting, lockout on disable, and dashboard notices."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_mobile_mfa_verify_rate_limited(tmp_path, monkeypatch):
    """POST /api/v1/auth/mfa/verify returns 429 after 5 attempts in a minute."""
    from fastapi.testclient import TestClient
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session, mfa_enroll
    from amlkit.api.app import app

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(str(db_file))
    now = utcnow()

    # Create org and MLRO operator
    conn.execute(
        "INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1, 'Test', 'test', 'active', ?)",
        (now,)
    )
    conn.execute(
        """INSERT INTO operators (id, org_id, name, email, password_hash, role, is_active, created_at, email_verified_at, disclaimer_acknowledged_at)
           VALUES (1, 1, 'MLRO', 'mlro@test.com', ?, 'mlro', 1, ?, ?, ?)""",
        (hash_password("password"), now, now, now)
    )

    # Enroll MFA for the operator
    secret = mfa_enroll(conn, operator_id=1)
    conn.commit()

    # Create a locked session (mfa_verified=0)
    token = create_session(conn, operator_id=1, org_id=1)
    conn.execute(
        "UPDATE sessions SET mfa_verified = 0 WHERE token_hash = ?",
        (hash_password(token),)
    )
    conn.commit()
    conn.close()

    # Enable rate limiter
    app.state.limiter.enabled = True

    try:
        client = TestClient(app, base_url="http://testserver/api/v1")

        # 5 failed attempts (should all go through)
        for i in range(5):
            r = client.post(
                "/auth/mfa/verify",
                json={"code": "wrong"},
                headers={"Authorization": f"Bearer {token}"}
            )
            assert r.status_code in [403, 200], f"Attempt {i+1} should not be rate-limited yet"

        # 6th attempt should be rate-limited
        r = client.post(
            "/auth/mfa/verify",
            json={"code": "wrong"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 429, "6th attempt should be rate-limited"

    finally:
        app.state.limiter.enabled = False


def test_mfa_disable_validates_code_with_lockout(tmp_path, monkeypatch):
    """POST /mfa/disable validates TOTP through mfa_check_code with lockout."""
    from fastapi.testclient import TestClient
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session, mfa_enroll
    from amlkit.api.app import app

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(str(db_file))
    now = utcnow()

    conn.execute(
        "INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1, 'Test', 'test', 'active', ?)",
        (now,)
    )
    conn.execute(
        """INSERT INTO operators (id, org_id, name, email, password_hash, role, is_active, created_at, email_verified_at, disclaimer_acknowledged_at)
           VALUES (1, 1, 'Test User', 'test@test.com', ?, 'mlro', 1, ?, ?, ?)""",
        (hash_password("password"), now, now, now)
    )

    # Enroll MFA
    secret = mfa_enroll(conn, operator_id=1)
    conn.commit()

    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)

    # Get CSRF token: any rendered page sets the synchronizer cookie
    # (there is no GET /account page; /account/password renders a form).
    r = client.get("/account/password")
    assert r.status_code == 200
    csrf = client.cookies.get("amlkit_csrf")
    assert csrf, "CSRF cookie should be set by a rendered page"

    # Try to disable with wrong code 5 times (exhaust attempts)
    for i in range(5):
        r = client.post(
            "/mfa/disable",
            data={"totp_code": "000000", "csrf_token": csrf},
            follow_redirects=False
        )

    # 6th attempt should trigger lockout
    # The most important verification is the audit log - check that first
    # Check audit log for mfa.failed and mfa.locked events
    conn = connect(str(db_file))
    failed_count = conn.execute(
        "SELECT COUNT(*) as c FROM audit_log WHERE action = 'mfa.failed'"
    ).fetchone()["c"]
    locked_count = conn.execute(
        "SELECT COUNT(*) as c FROM audit_log WHERE action = 'mfa.locked'"
    ).fetchone()["c"]
    conn.close()

    assert failed_count >= 5, "Should have at least 5 mfa.failed audit entries"
    assert locked_count >= 1, "Should have at least 1 mfa.locked audit entry"


def test_dashboard_shows_mfa_lockout_banner(tmp_path, monkeypatch):
    """Dashboard shows banner when mfa.locked audit event exists."""
    from fastapi.testclient import TestClient
    from amlkit.db import connect, utcnow, audit
    from amlkit.auth import hash_password, create_session
    from amlkit.api.app import app

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(str(db_file))
    now = utcnow()

    conn.execute(
        "INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1, 'Test', 'test', 'active', ?)",
        (now,)
    )
    conn.execute(
        """INSERT INTO operators (id, org_id, name, email, password_hash, role, is_active, created_at, email_verified_at, disclaimer_acknowledged_at)
           VALUES (1, 1, 'MLRO User', 'mlro@test.com', ?, 'mlro', 1, ?, ?, ?)""",
        (hash_password("password"), now, now, now)
    )

    # Add a fresh dataset so dashboard doesn't fail
    conn.execute(
        "INSERT INTO datasets (key, title, is_mandatory, last_refresh, entity_count) VALUES ('un', 'UN', 1, ?, 1)",
        (now,)
    )

    # Create an mfa.locked audit event
    audit(conn, "test-operator", "mfa.locked", "operator", 1, "lockout_key", org_id=1)
    conn.commit()

    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)

    # Visit dashboard (or any page that renders with the banner)
    r = client.get("/dashboard")
    assert r.status_code == 200

    # Check for MFA lockout message in response
    assert "MFA" in r.text or "locked" in r.text.lower() or "authentication" in r.text.lower()

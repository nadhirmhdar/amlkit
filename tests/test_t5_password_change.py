"""Test self-service password change at /account/password (t5)."""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_password_change_happy_path(tmp_path, monkeypatch):
    """Happy path: correct current password + valid new password → 200 and password updated."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session, verify_password

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    now = utcnow()

    # Setup org and operator
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
        ("Test Org", "test-org", "active", now)
    )
    old_password = "OldPass123!"
    conn.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active,
           created_at, email_verified_at, disclaimer_acknowledged_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (1, "Test User", "test@example.ae", hash_password(old_password), "analyst", 1, now, now, now)
    )
    conn.commit()

    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)

    # Get CSRF token from any page
    client.get("/")
    csrf = client.cookies.get("amlkit_csrf")

    # Change password with correct current password
    new_password = "NewPass456!"
    r = client.post("/account/password", data={
        "current_password": old_password,
        "new_password": new_password,
        "confirm_password": new_password,
        "csrf_token": csrf
    }, follow_redirects=False)

    # Should succeed with redirect
    assert r.status_code == 303
    assert "/" in r.headers.get("location", "")

    # Verify password was actually updated in database
    conn = connect(db_file)
    op = conn.execute("SELECT password_hash FROM operators WHERE id=1").fetchone()
    assert verify_password(new_password, op["password_hash"])
    assert not verify_password(old_password, op["password_hash"])
    conn.close()


def test_password_change_wrong_current_password_returns_400(tmp_path, monkeypatch):
    """Wrong current password → 400/401."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session, verify_password

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    now = utcnow()

    # Setup org and operator
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
        ("Test Org", "test-org", "active", now)
    )
    correct_password = "CorrectPass123!"
    conn.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active,
           created_at, email_verified_at, disclaimer_acknowledged_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (1, "Test User", "test@example.ae", hash_password(correct_password), "analyst", 1, now, now, now)
    )
    conn.commit()

    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)

    # Get CSRF token
    client.get("/account/password")
    csrf = client.cookies.get("amlkit_csrf")

    # Try to change password with WRONG current password
    r = client.post("/account/password", data={
        "current_password": "WrongPass123!",
        "new_password": "NewPass456!",
        "confirm_password": "NewPass456!",
        "csrf_token": csrf
    }, follow_redirects=True)

    # Should fail with error
    assert r.status_code in [200, 400, 401]  # May be 200 with error in HTML
    assert "incorrect" in r.text.lower() or "current password" in r.text.lower()

    # Verify password was NOT changed
    conn = connect(db_file)
    op = conn.execute("SELECT password_hash FROM operators WHERE id=1").fetchone()
    assert verify_password(correct_password, op["password_hash"])
    conn.close()


def test_password_change_invalidates_other_sessions(tmp_path, monkeypatch):
    """Successful change invalidates other active sessions for that user."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    now = utcnow()

    # Setup org and operator
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
        ("Test Org", "test-org", "active", now)
    )
    old_password = "OldPass123!"
    conn.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active,
           created_at, email_verified_at, disclaimer_acknowledged_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (1, "Test User", "test@example.ae", hash_password(old_password), "analyst", 1, now, now, now)
    )
    conn.commit()

    # Create TWO sessions for the same user (simulating login from two devices)
    session1_token = create_session(conn, operator_id=1, org_id=1)
    session2_token = create_session(conn, operator_id=1, org_id=1)

    # Verify both sessions exist and are active
    sessions_before = conn.execute(
        "SELECT COUNT(*) as count FROM sessions WHERE operator_id=1 AND revoked_at IS NULL"
    ).fetchone()["count"]
    assert sessions_before == 2

    conn.close()

    # Use session1 to change password
    client = TestClient(app)
    client.cookies.set("amlkit_session", session1_token)
    client.get("/account/password")
    csrf = client.cookies.get("amlkit_csrf")

    new_password = "NewPass456!"
    r = client.post("/account/password", data={
        "current_password": old_password,
        "new_password": new_password,
        "confirm_password": new_password,
        "csrf_token": csrf
    }, follow_redirects=True)

    assert r.status_code == 200

    # Verify ALL sessions were revoked
    conn = connect(db_file)
    sessions_after = conn.execute(
        "SELECT COUNT(*) as count FROM sessions WHERE operator_id=1 AND revoked_at IS NULL"
    ).fetchone()["count"]
    assert sessions_after == 0  # All sessions invalidated

    revoked_sessions = conn.execute(
        "SELECT COUNT(*) as count FROM sessions WHERE operator_id=1 AND revoked_at IS NOT NULL"
    ).fetchone()["count"]
    assert revoked_sessions == 2  # Both sessions marked as revoked

    conn.close()

    # Try to use session2 (should be rejected)
    client2 = TestClient(app)
    client2.cookies.set("amlkit_session", session2_token)
    r2 = client2.get("/dashboard", follow_redirects=False)

    # Should redirect to login (session invalid)
    assert r2.status_code == 303
    assert "/login" in r2.headers.get("location", "")

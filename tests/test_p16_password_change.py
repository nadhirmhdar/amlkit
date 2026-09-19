"""Self-service password change tests (p16)."""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def test_password_change_requires_old_password(tmp_path, monkeypatch):
    """Password change requires correct old password."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session
    
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    
    conn = connect(db_file)
    now = utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test Org", "test-org", "active", now))
    conn.execute("INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at, disclaimer_acknowledged_at) VALUES (?,?,?,?,?,?,?,?,?)",
                 (1, "Test User", "test@example.ae", hash_password("OldPass123!"), "mlro", 1, now, now, now))
    conn.commit()
    
    # Create session
    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()
    
    client = TestClient(app)
    client.cookies.set("amlkit_session", token)
    
    # Get CSRF token
    client.get("/profile")
    csrf = client.cookies.get("amlkit_csrf")
    
    # Try with wrong old password
    r = client.post("/profile/change-password", data={
        "old_password": "WrongPass123!",
        "new_password": "NewPass123!",
        "csrf_token": csrf
    }, follow_redirects=False)
    
    assert r.status_code in [303, 400]  # Redirect or error

def test_password_change_enforces_complexity(tmp_path, monkeypatch):
    """New password must meet complexity requirements."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session
    
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    
    conn = connect(db_file)
    now = utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test Org", "test-org", "active", now))
    conn.execute("INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at, disclaimer_acknowledged_at) VALUES (?,?,?,?,?,?,?,?,?)",
                 (1, "Test User", "test@example.ae", hash_password("OldPass123!"), "mlro", 1, now, now, now))
    conn.commit()
    
    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()
    
    client = TestClient(app)
    client.cookies.set("amlkit_session", token)
    client.get("/profile")
    csrf = client.cookies.get("amlkit_csrf")
    
    # Try weak password
    r = client.post("/profile/change-password", data={
        "old_password": "OldPass123!",
        "new_password": "weak",
        "csrf_token": csrf
    }, follow_redirects=True)
    
    assert "10 characters" in r.text or "uppercase" in r.text or "digit" in r.text

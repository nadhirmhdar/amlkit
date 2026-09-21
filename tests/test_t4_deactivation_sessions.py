"""Test operator deactivation invalidates all sessions (t4)."""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def test_operator_deactivation_invalidates_all_sessions(tmp_path, monkeypatch):
    """Deactivating operator invalidates all their active sessions."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import create_session, resolve_session
    
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    
    conn = connect(db_file)
    now = utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test Org", "test-org", "active", now))
    # Create MLRO (will deactivate the operator)
    conn.execute("INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at, disclaimer_acknowledged_at) VALUES (?,?,?,?,?,?,?,?,?)",
                 (1, "MLRO User", "mlro@test.ae", "hash", "mlro", 1, now, now, now))
    # Create target operator to deactivate
    conn.execute("INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
                 (1, "Target User", "target@test.ae", "hash", "officer", 1, now, now))
    conn.commit()
    
    # Create 2 sessions for target operator
    token1 = create_session(conn, operator_id=2, org_id=1)
    token2 = create_session(conn, operator_id=2, org_id=1)
    
    # Verify both sessions work
    assert resolve_session(conn, token1) is not None
    assert resolve_session(conn, token2) is not None
    
    conn.close()
    
    # Login as MLRO and deactivate operator #2
    client = TestClient(app)
    conn2 = connect(db_file)
    mlro_token = create_session(conn2, operator_id=1, org_id=1)
    conn2.close()
    
    client.cookies.set("amlkit_session", mlro_token)
    client.get("/admin")  # Get CSRF token
    csrf = client.cookies.get("amlkit_csrf")
    
    # Deactivate operator #2
    r = client.post("/admin/operators/2/deactivate", data={"csrf_token": csrf})
    assert r.status_code == 200
    
    # Verify both sessions are now invalid
    conn3 = connect(db_file)
    assert resolve_session(conn3, token1) is None, "First session should be invalid"
    assert resolve_session(conn3, token2) is None, "Second session should be invalid"
    conn3.close()

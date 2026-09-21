"""Test MLRO-only audit route access (t3)."""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def test_audit_route_requires_mlro_role(tmp_path, monkeypatch):
    """GET /audit requires MLRO role - operators get 403."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    
    conn = connect(db_file)
    now = utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test Org", "test-org", "active", now))
    # Create MLRO
    conn.execute("INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
                 (1, "MLRO User", "mlro@test.ae", "hash", "mlro", 1, now, now))
    # Create officer
    conn.execute("INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
                 (1, "Officer User", "officer@test.ae", "hash", "officer", 1, now, now))
    conn.commit()
    conn.close()
    
    client = TestClient(app)
    
    # Login as MLRO - should work
    from amlkit.auth import create_session
    from amlkit.db import connect as db_connect
    c = db_connect(db_file)
    mlro_token = create_session(c, operator_id=1, org_id=1)
    c.close()
    
    client.cookies.set("amlkit_session", mlro_token)
    r_mlro = client.get("/audit")
    assert r_mlro.status_code == 200
    
    # Login as officer - should get 403 or redirect
    c2 = db_connect(db_file)
    officer_token = create_session(c2, operator_id=2, org_id=1)
    c2.close()
    
    client.cookies.set("amlkit_session", officer_token)
    r_officer = client.get("/audit", follow_redirects=False)
    assert r_officer.status_code in [303, 403]  # Redirect or forbidden

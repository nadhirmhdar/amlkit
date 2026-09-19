"""Report submission validation tests (p17)."""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def test_report_submit_requires_required_fields(tmp_path, monkeypatch):
    """Report submission fails if required fields are missing."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session
    
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    
    conn = connect(db_file)
    now = utcnow()
    # Seed database
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test Org", "test-org", "active", now))
    conn.execute("INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at, disclaimer_acknowledged_at) VALUES (?,?,?,?,?,?,?,?,?)",
                 (1, "MLRO", "mlro@test.ae", hash_password("Pass123!"), "mlro", 1, now, now, now))
    # Create incomplete report (missing required fields)
    conn.execute(
        "INSERT INTO reports (org_id, report_type, reference, status, created_at) VALUES (?,?,?,?,?)",
        (1, "STR", "REP-001", "draft", now)
    )
    conn.commit()
    
    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()
    
    client = TestClient(app)
    client.cookies.set("amlkit_session", token)
    client.get("/reports/1")
    csrf = client.cookies.get("amlkit_csrf")
    
    # Try to submit incomplete report
    r = client.post("/reports/1/submit", data={"csrf_token": csrf}, follow_redirects=True)
    
    # Should fail with validation error
    assert r.status_code == 200
    assert "required" in r.text.lower() or "missing" in r.text.lower() or "cannot submit" in r.text.lower()

def test_report_submit_succeeds_with_complete_data(tmp_path, monkeypatch):
    """Report submission succeeds with all required fields."""
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
                 (1, "MLRO", "mlro@test.ae", hash_password("Pass123!"), "mlro", 1, now, now, now))
    # Create complete report with all required fields
    conn.execute(
        """INSERT INTO reports (org_id, report_type, reference, status, created_at, 
           reporting_entity_name, reporting_entity_address, fiu_ref_number, reason, location) 
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (1, "STR", "REP-001", "draft", now, "Test Entity", "Dubai, UAE", "FIU-123", "Suspicious transaction", "Dubai")
    )
    conn.commit()
    
    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()
    
    client = TestClient(app)
    client.cookies.set("amlkit_session", token)
    client.get("/reports/1")
    csrf = client.cookies.get("amlkit_csrf")
    
    # Submit complete report
    r = client.post("/reports/1/submit", data={"csrf_token": csrf}, follow_redirects=True)
    
    # Should succeed
    assert r.status_code == 200
    assert "submitted" in r.text.lower() or "success" in r.text.lower()

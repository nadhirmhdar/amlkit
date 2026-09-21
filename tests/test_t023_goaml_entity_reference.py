"""Test goAML entity_reference injection (follow-up to #231/#142)."""
import pytest
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_inject_reporting_entity_raises_when_entity_reference_missing(tmp_path, monkeypatch):
    """inject_reporting_entity() raises GoAMLValidationError when goaml_entity_reference is NULL."""
    from amlkit.db import connect, utcnow
    from amlkit.reporting.goaml import inject_reporting_entity, GoAMLValidationError

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    now = utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at, org_address) VALUES (?,?,?,?,?)",
                 ("Test Org", "test-org", "active", now, "Dubai"))
    conn.commit()

    payload = {"report_type": "STR"}

    with pytest.raises(GoAMLValidationError, match="goAML entity reference not configured"):
        inject_reporting_entity(payload, conn, 1)

    conn.close()


def test_inject_reporting_entity_fills_payload(tmp_path, monkeypatch):
    """inject_reporting_entity() fills reporting_entity_name, _branch, and entity_reference."""
    from amlkit.db import connect, utcnow
    from amlkit.reporting.goaml import inject_reporting_entity

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    now = utcnow()
    conn.execute("""INSERT INTO organizations 
                    (name, slug, status, created_at, org_address, goaml_entity_reference) 
                    VALUES (?,?,?,?,?,?)""",
                 ("Test Org", "test-org", "active", now, "Dubai HQ", "AML-TEST-001"))
    conn.commit()

    payload = {"report_type": "STR"}
    inject_reporting_entity(payload, conn, 1)

    assert payload["reporting_entity_name"] == "Test Org"
    assert payload["reporting_entity_branch"] == "Dubai HQ"
    assert payload["entity_reference"] == "AML-TEST-001"

    conn.close()


def test_mobile_export_contains_org_name_not_aml_ref(tmp_path, monkeypatch):
    """Mobile API export XML contains org name and not hardcoded AML-REF."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    now = utcnow()
    conn.execute("""INSERT INTO organizations 
                    (name, slug, status, created_at, goaml_entity_reference) 
                    VALUES (?,?,?,?,?)""",
                 ("Mobile Test Org", "mobile-test", "active", now, "MOBILE-001"))
    conn.execute("""INSERT INTO operators 
                    (org_id, name, email, password_hash, role, is_active, created_at, 
                     email_verified_at, disclaimer_acknowledged_at) 
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (1, "Test User", "test@example.ae", hash_password("TestPass123!"), 
                  "mlro", 1, now, now, now))

    # Create a minimal report
    payload = {
        "report_type": "STR",
        "reporter_name": "Test Reporter",
        "reporter_email": "reporter@example.ae",
        "first_name": "John",
        "last_name": "Doe"
    }
    conn.execute("""INSERT INTO customers 
                    (org_id, reference, customer_type, full_name, canonical_key, 
                     status, onboarded_at, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (1, "C-001", "natural", "John Doe", "john|doe", "active", now, now, now))
    conn.execute("""INSERT INTO reports 
                    (org_id, customer_id, report_type, status, payload, created_at)
                    VALUES (?,?,?,?,?,?)""",
                 (1, 1, "STR", "draft", json.dumps(payload), now))
    conn.commit()

    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)

    # Export via mobile API
    from amlkit.api.mobile import router
    app.include_router(router)
    
    r = client.get("/api/v1/reports/1/export")
    r = client.get("/api/v1/reports/1/export", headers={"Authorization": f"Bearer {token}"})
    assert r.headers["content-type"] == "application/xml"
    
    xml = r.text
    assert "Mobile Test Org" in xml
    assert "MOBILE-001" in xml
    assert "AML-REF" not in xml or "MOBILE-001" in xml  # entity_reference should be MOBILE-001, not AML-REF

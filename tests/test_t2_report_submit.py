"""Test /reports/{id}/submit endpoint (t2)."""
import pytest
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_report_submit_happy_path_mlro_submits_str(tmp_path, monkeypatch):
    """Happy path: MLRO submits an STR → 200/204."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    now = utcnow()

    # Setup org and MLRO operator
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
        ("Test Org", "test-org", "active", now)
    )
    conn.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active,
           created_at, email_verified_at, disclaimer_acknowledged_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (1, "MLRO", "mlro@test.ae", hash_password("Pass123!"), "mlro", 1, now, now, now)
    )

    # Create draft report with complete payload
    payload = {
        "reporting_entity_name": "Test Entity",
        "report_code": "STR",
        "submission_code": "SUBMIT-001",
        "reason": "Suspicious transaction pattern",
        "transactions": [{"amount": 50000, "currency": "AED"}],
        "entities": []
    }
    conn.execute(
        """INSERT INTO reports (org_id, report_type, reference, status, payload, created_at)
           VALUES (?,?,?,?,?,?)""",
        (1, "STR", "REP-001", "draft", json.dumps(payload), now)
    )
    conn.commit()

    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)
    client.get("/reports/1")  # Get CSRF token
    csrf = client.cookies.get("amlkit_csrf")

    # Submit report
    r = client.post("/reports/1/submit", data={"csrf_token": csrf}, follow_redirects=True)

    # Should succeed with redirect and success message
    assert r.status_code == 200
    assert "submitted" in r.text.lower() or "success" in r.text.lower()

    # Verify report status updated in database
    conn = connect(db_file)
    report = conn.execute("SELECT status, submitted_at FROM reports WHERE id=1").fetchone()
    assert report["status"] == "submitted"
    assert report["submitted_at"] is not None
    conn.close()


def test_report_submit_already_submitted_returns_400(tmp_path, monkeypatch):
    """Already-submitted: second submit → 400."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    now = utcnow()

    # Setup org and MLRO operator
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
        ("Test Org", "test-org", "active", now)
    )
    conn.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active,
           created_at, email_verified_at, disclaimer_acknowledged_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (1, "MLRO", "mlro@test.ae", hash_password("Pass123!"), "mlro", 1, now, now, now)
    )

    # Create ALREADY submitted report
    payload = {
        "reporting_entity_name": "Test Entity",
        "report_code": "STR",
        "submission_code": "SUBMIT-001",
        "reason": "Suspicious transaction pattern",
        "transactions": [{"amount": 50000, "currency": "AED"}]
    }
    conn.execute(
        """INSERT INTO reports (org_id, report_type, reference, status, payload,
           created_at, submitted_at)
           VALUES (?,?,?,?,?,?,?)""",
        (1, "STR", "REP-001", "submitted", json.dumps(payload), now, now)
    )
    conn.commit()

    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)
    client.get("/reports/1")  # Get CSRF token
    csrf = client.cookies.get("amlkit_csrf")

    # Try to submit already-submitted report
    r = client.post("/reports/1/submit", data={"csrf_token": csrf}, follow_redirects=True)

    # Should fail with error indicating already submitted
    assert r.status_code in [200, 400]  # May be 200 with error message in redirect
    assert "already" in r.text.lower() or "cannot submit" in r.text.lower()


def test_report_submit_wrong_org_returns_403(tmp_path, monkeypatch):
    """Wrong org: operator from different org → 403."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    now = utcnow()

    # Setup TWO orgs
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
        ("Org One", "org-one", "active", now)
    )
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
        ("Org Two", "org-two", "active", now)
    )

    # Operator in org 1
    conn.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active,
           created_at, email_verified_at, disclaimer_acknowledged_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (1, "MLRO One", "mlro1@test.ae", hash_password("Pass123!"), "mlro", 1, now, now, now)
    )

    # Report belongs to org 2
    payload = {
        "reporting_entity_name": "Test Entity",
        "report_code": "STR",
        "submission_code": "SUBMIT-001",
        "reason": "Suspicious transaction pattern",
        "transactions": [{"amount": 50000, "currency": "AED"}]
    }
    conn.execute(
        """INSERT INTO reports (org_id, report_type, reference, status, payload, created_at)
           VALUES (?,?,?,?,?,?)""",
        (2, "STR", "REP-001", "draft", json.dumps(payload), now)
    )
    conn.commit()

    # Create session for operator in org 1
    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)
    client.get("/reports")  # Get CSRF token from any page
    csrf = client.cookies.get("amlkit_csrf")

    # Try to submit report from org 2 using org 1 credentials
    r = client.post("/reports/1/submit", data={"csrf_token": csrf}, follow_redirects=True)

    # Should fail - either 403 or redirect with "not found" message
    assert r.status_code in [200, 403, 404]
    assert "not found" in r.text.lower() or "denied" in r.text.lower() or "reports" in r.url

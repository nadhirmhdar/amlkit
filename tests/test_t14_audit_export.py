"""Test t14: Audit log CSV export."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    from amlkit.db import connect
    connect(db_file).close()

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    return TestClient(app)


def test_audit_export_mlro_returns_csv(tmp_path, monkeypatch):
    """MLRO role → returns 200 with CSV content-type."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test", "test", "active", utcnow()))
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
        (1, "MLRO User", "mlro@example.ae", auth.hash_password("password"), "mlro", 1, utcnow(), utcnow()))
    conn.commit()

    token = auth.create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)

    resp = client.get("/audit/export")
    assert resp.status_code == 200, "MLRO should be able to export audit log"
    assert "text/csv" in resp.headers.get("content-type", ""), "Should return CSV"


def test_audit_export_officer_forbidden(tmp_path, monkeypatch):
    """Officer role → 403."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test", "test", "active", utcnow()))
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
        (1, "Officer", "officer@example.ae", auth.hash_password("password"), "officer", 1, utcnow(), utcnow()))
    conn.commit()

    token = auth.create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)

    resp = client.get("/audit/export")
    assert resp.status_code == 403, "Officer should not be able to export audit log"


def test_audit_export_csv_has_headers(tmp_path, monkeypatch):
    """CSV has headers: timestamp, action, user, ip."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test", "test", "active", utcnow()))
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
        (1, "MLRO", "mlro@example.ae", auth.hash_password("password"), "mlro", 1, utcnow(), utcnow()))
    conn.commit()

    token = auth.create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)

    resp = client.get("/audit/export")
    content = resp.text
    header_line = content.split("\n")[0].lower()
    assert "timestamp" in header_line or "ts" in header_line, "CSV should have timestamp column"
    assert "action" in header_line or "event" in header_line, "CSV should have action column"

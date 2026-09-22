"""Test H4: CSV exports must escape formula injection characters.

Both web and mobile audit CSV exports write operator_name (free text) unescaped.
A formula-injection payload as a name lands unescaped in regulator-facing exports.
"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_web_audit_csv_escapes_formula_chars(tmp_path, monkeypatch):
    """Web /audit/export must escape cells starting with =+-@."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    conn = connect(db_file)
    now = utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test Org", "test-org", "active", now))
    # Create MLRO with formula-injection payload in name
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (1, "=1+1 Evil Formula", "mlro@test.ae", auth.hash_password("Password1!"), "mlro", 1, now, now))
    conn.commit()

    # Create an audit entry with this operator as actor
    from amlkit.db import audit
    audit(conn, "=1+1 Evil Formula", "test_action", "operator", 1, "test detail", org_id=1)
    conn.commit()
    conn.close()

    client = TestClient(app)

    # Login as MLRO
    from amlkit.auth import create_session
    conn2 = connect(db_file)
    token = create_session(conn2, operator_id=1, org_id=1)
    conn2.close()

    client.cookies.set("amlkit_session", token)
    r = client.get("/audit/export")
    assert r.status_code == 200

    csv_content = r.text
    # Formula chars must be escaped with leading single quote
    assert "'=1+1 Evil Formula" in csv_content, (
        "CSV export must escape formula-injection chars with leading single quote. "
        f"Got: {csv_content[:500]}"
    )
    assert "\n=1+1" not in csv_content, "Unescaped formula found in CSV"


def test_mobile_audit_csv_escapes_formula_chars(tmp_path, monkeypatch):
    """Mobile /api/v1/admin/audit/export must escape cells starting with =+-@."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    conn = connect(db_file)
    now = utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test Org", "test-org", "active", now))
    # Create MLRO with formula-injection payload in name
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (1, "+cmd|'/c calc'!A1", "mlro@test.ae", auth.hash_password("Password1!"), "mlro", 1, now, now))
    conn.commit()

    # Create an audit entry
    from amlkit.db import audit
    audit(conn, "+cmd|'/c calc'!A1", "test_action", "operator", 1, "test detail", org_id=1)
    conn.commit()
    conn.close()

    client = TestClient(app)

    # Login as MLRO via mobile API
    mlro_login = client.post("/api/v1/auth/login", json={
        "email": "mlro@test.ae", "password": "Password1!",
    })
    assert mlro_login.status_code == 200
    token = mlro_login.json()["token"]

    # Unlock MFA
    from conftest import unlock_mobile_mfa
    unlock_mobile_mfa(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/v1/audit/export", headers=headers)
    assert r.status_code == 200

    csv_content = r.text
    # Formula chars must be escaped with leading single quote
    assert "'+cmd|'/c calc'!A1" in csv_content, (
        "Mobile CSV export must escape formula-injection chars with leading single quote. "
        f"Got: {csv_content[:500]}"
    )
    assert "\n+cmd|" not in csv_content, "Unescaped formula found in mobile CSV"

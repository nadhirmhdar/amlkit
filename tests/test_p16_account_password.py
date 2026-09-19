"""Test p16: /account/password route."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    from amlkit.db import connect
    connect(db_file).close()

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    return TestClient(app)


def test_account_password_requires_auth(client):
    """GET /account/password requires authentication."""
    resp = client.get("/account/password", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_account_password_form_loads(tmp_path, monkeypatch):
    """Authenticated users can view /account/password form."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password, create_session

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    now = utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test", "test", "active", now))
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at, disclaimer_acknowledged_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (1, "Test", "test@example.ae", hash_password("password"), "mlro", 1, now, now, now))
    conn.commit()

    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)

    resp = client.get("/account/password")
    assert resp.status_code == 200
    assert b"password" in resp.content.lower()

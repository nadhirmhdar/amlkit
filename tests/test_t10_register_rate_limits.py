"""Test t10: Rate limiting on /register-organization and /resend-verification."""

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

    app.state.limiter._storage.reset()
    app.state.limiter.enabled = True
    yield TestClient(app)
    app.state.limiter.enabled = False


def test_register_organization_rate_limit(client):
    """Sending 11 requests to /register-organization → 11th returns 429."""

    # Get CSRF token
    client.get("/register-organization")
    csrf = client.cookies.get("amlkit_csrf")

    # First 10 should succeed or return validation errors (not rate limited)
    for i in range(10):
        resp = client.post("/register-organization", data={
            "org_name": f"Test Org {i}",
            "name": f"User {i}",
            "email": f"test{i}@example.ae",
            "password": f"Password{i}123!",
            "csrf_token": csrf,
        })
        assert resp.status_code != 429, f"Request {i+1} was rate limited (should not be)"

    # 11th request should be rate limited
    resp = client.post("/register-organization", data={
        "org_name": "Test Org 11",
        "name": "User 11",
        "email": "test11@example.ae",
        "password": "Password11123!",
        "csrf_token": csrf,
    })
    assert resp.status_code == 429, "11th request should be rate limited"


def test_resend_verification_rate_limit(client, tmp_path, monkeypatch):
    """Sending 11 requests to /resend-verification → 11th returns 429."""
    from amlkit.db import connect, utcnow
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    # Create unverified operator
    conn = connect(db_file)
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test", "test", "pending", utcnow()))
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at) VALUES (?,?,?,?,?,?,?)",
        (1, "Test User", "unverified@example.ae", auth.hash_password("password"), "mlro", 1, utcnow()))
    conn.commit()
    conn.close()

    # Get CSRF token
    client.get("/login")
    csrf = client.cookies.get("amlkit_csrf")

    # First 10 should not be rate limited
    for i in range(10):
        resp = client.post("/resend-verification", data={
            "email": "unverified@example.ae",
            "csrf_token": csrf,
        })
        assert resp.status_code != 429, f"Request {i+1} was rate limited (should not be)"

    # 11th should be rate limited
    resp = client.post("/resend-verification", data={
        "email": "unverified@example.ae",
        "csrf_token": csrf,
    })
    assert resp.status_code == 429, "11th request should be rate limited"

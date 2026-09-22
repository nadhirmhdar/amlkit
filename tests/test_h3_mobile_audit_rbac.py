"""Test H3: Mobile API /api/v1/audit requires MLRO role."""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_mobile_audit_requires_mlro_role(tmp_path, monkeypatch):
    """GET /api/v1/audit requires MLRO role - officers should get 403."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit.auth import hash_password

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    conn = connect(db_file)
    now = utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test Org", "test-org", "active", now))
    # Create MLRO
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (1, "MLRO User", "mlro@test.ae", hash_password("Password1!"), "mlro", 1, now, now))
    # Create officer (should NOT have access to audit)
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (1, "Officer User", "officer@test.ae", hash_password("Password1!"), "officer", 1, now, now))
    conn.commit()
    conn.close()

    client = TestClient(app)

    # Login as MLRO to get bearer token
    mlro_login = client.post("/api/v1/auth/login", json={
        "email": "mlro@test.ae", "password": "Password1!",
    })
    assert mlro_login.status_code == 200, f"MLRO login failed: {mlro_login.text}"
    mlro_token = mlro_login.json()["token"]

    # Unlock MFA for MLRO
    from conftest import unlock_mobile_mfa
    unlock_mobile_mfa(client, mlro_token)
    mlro_headers = {"Authorization": f"Bearer {mlro_token}"}

    # MLRO should have access to audit
    r_mlro = client.get("/api/v1/audit", headers=mlro_headers)
    assert r_mlro.status_code == 200, "MLRO should have access to /api/v1/audit"

    # Login as officer to get bearer token
    officer_login = client.post("/api/v1/auth/login", json={
        "email": "officer@test.ae", "password": "Password1!",
    })
    assert officer_login.status_code == 200, f"Officer login failed: {officer_login.text}"
    officer_token = officer_login.json()["token"]
    officer_headers = {"Authorization": f"Bearer {officer_token}"}

    # Officer should NOT have access to audit
    r_officer = client.get("/api/v1/audit", headers=officer_headers)
    assert r_officer.status_code == 403, (
        "Officer should not have access to /api/v1/audit (MLRO-only endpoint). "
        f"Got {r_officer.status_code}"
    )

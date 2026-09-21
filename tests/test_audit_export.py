"""Tests for audit log CSV export endpoint.

Issue #71 p20: Add CSV export endpoint for audit logs with date filtering.
MLRO/admin only, org-isolated.
"""
import csv
import io

import pytest
from fastapi.testclient import TestClient

from amlkit import auth
from amlkit.api.app import app
from amlkit.db import audit, connect, utcnow


@pytest.fixture
def db_with_audit_logs(tmp_path, monkeypatch):
    """Database with audit logs for multiple orgs."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    conn = connect(str(db_file))
    now = utcnow()

    conn.execute(
        "INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1, 'Org1', 'org1', 'active', ?)",
        (now,),
    )
    conn.execute(
        "INSERT INTO organizations (id, name, slug, status, created_at) VALUES (2, 'Org2', 'org2', 'active', ?)",
        (now,),
    )

    pw_hash = auth.hash_password("TestPass123!")

    conn.execute(
        """INSERT INTO operators (id, name, email, org_id, role, password_hash, is_active,
           email_verified_at, created_at)
           VALUES (1, 'MLRO1', 'mlro1@test.com', 1, 'mlro', ?, 1, ?, ?)""",
        (pw_hash, now, now),
    )
    conn.execute(
        """INSERT INTO operators (id, name, email, org_id, role, password_hash, is_active,
           email_verified_at, created_at)
           VALUES (2, 'Officer1', 'officer1@test.com', 1, 'officer', ?, 1, ?, ?)""",
        (pw_hash, now, now),
    )
    conn.execute(
        """INSERT INTO operators (id, name, email, org_id, role, password_hash, is_active,
           email_verified_at, created_at)
           VALUES (3, 'MLRO2', 'mlro2@test.com', 2, 'mlro', ?, 1, ?, ?)""",
        (pw_hash, now, now),
    )

    for i in range(5):
        audit(conn, "MLRO1", f"action.{i}", "type1", i, {"detail": f"d{i}"}, org_id=1)

    for i in range(3):
        audit(conn, "MLRO2", f"action.org2.{i}", "type2", i, {"detail": f"d{i}"}, org_id=2)

    conn.commit()
    conn.close()
    return str(db_file)


def _login(client, email):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "TestPass123!"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_mlro_can_export_audit_csv(db_with_audit_logs):
    """MLRO role can export audit logs as CSV."""
    client = TestClient(app)
    token = _login(client, "mlro1@test.com")

    resp = client.get(
        "/api/v1/audit/export",
        params={"from": "2024-01-01", "to": "2026-12-31"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]

    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) >= 5
    assert "ts" in rows[0]
    assert "actor" in rows[0]
    assert "action" in rows[0]


def test_officer_cannot_export_audit_csv(db_with_audit_logs):
    """Officer role is denied access to audit export."""
    client = TestClient(app)
    token = _login(client, "officer1@test.com")

    resp = client.get(
        "/api/v1/audit/export",
        params={"from": "2024-01-01", "to": "2026-12-31"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 403


def test_audit_export_is_org_isolated(db_with_audit_logs):
    """Audit export only returns logs for the user's org."""
    client = TestClient(app)
    token = _login(client, "mlro2@test.com")

    resp = client.get(
        "/api/v1/audit/export",
        params={"from": "2024-01-01", "to": "2026-12-31"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) >= 3
    # No org1-seeded actions should appear (action.0 through action.4 are org1)
    for row in rows:
        assert not row["action"].startswith("action.") or "org2" in row["action"]


def test_unauthenticated_returns_401(db_with_audit_logs):
    """Unauthenticated request returns 401."""
    client = TestClient(app)

    resp = client.get(
        "/api/v1/audit/export",
        params={"from": "2024-01-01", "to": "2026-12-31"},
    )

    assert resp.status_code == 401

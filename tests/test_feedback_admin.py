"""Tests for the /admin/feedback viewer and /admin/feedback/export (MLRO-only,
org-scoped viewer over the feedback table that feedback_submit() writes to)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_org_and_operators(conn, org_id: int, slug: str):
    from amlkit.db import utcnow
    from amlkit import auth

    now = utcnow()
    conn.execute(
        "INSERT INTO organizations (id, name, slug, status, created_at) VALUES (?,?,?,?,?)",
        (org_id, f"Org {org_id}", slug, "active", now),
    )
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active,"
        " created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
        (org_id, "MLRO User", f"mlro-{org_id}@test.ae", auth.hash_password("password"),
         "mlro", 1, now, now),
    )
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active,"
        " created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
        (org_id, "Officer User", f"officer-{org_id}@test.ae", auth.hash_password("password"),
         "officer", 1, now, now),
    )
    conn.commit()


def test_feedback_route_requires_mlro_role(tmp_path, monkeypatch):
    """GET /admin/feedback requires MLRO role -- other roles are rejected."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    _make_org_and_operators(conn, 1, "org-1")
    mlro_id = conn.execute("SELECT id FROM operators WHERE role='mlro'").fetchone()["id"]
    officer_id = conn.execute("SELECT id FROM operators WHERE role='officer'").fetchone()["id"]

    mlro_token = auth.create_session(conn, operator_id=mlro_id, org_id=1)
    officer_token = auth.create_session(conn, operator_id=officer_id, org_id=1)
    conn.close()

    client = TestClient(app)

    client.cookies.set("amlkit_session", mlro_token)
    r_mlro = client.get("/admin/feedback")
    assert r_mlro.status_code == 200

    client.cookies.set("amlkit_session", officer_token)
    r_officer = client.get("/admin/feedback", follow_redirects=False)
    assert r_officer.status_code in (303, 403)


def test_feedback_viewer_is_org_scoped(tmp_path, monkeypatch):
    """An MLRO only sees their own org's feedback, never another firm's."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    _make_org_and_operators(conn, 1, "org-1")
    _make_org_and_operators(conn, 2, "org-2")
    now = utcnow()
    conn.execute(
        "INSERT INTO feedback (org_id, operator_id, page, message, created_at)"
        " VALUES (?,?,?,?,?)",
        (1, 1, "/dashboard", "ORG-ONE-MARKER this is confusing", now),
    )
    conn.execute(
        "INSERT INTO feedback (org_id, operator_id, page, message, created_at)"
        " VALUES (?,?,?,?,?)",
        (2, 3, "/screen", "ORG-TWO-MARKER please add a dark mode", now),
    )
    conn.commit()
    org1_mlro_id = conn.execute(
        "SELECT id FROM operators WHERE org_id=1 AND role='mlro'"
    ).fetchone()["id"]
    token = auth.create_session(conn, operator_id=org1_mlro_id, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)
    resp = client.get("/admin/feedback")
    assert resp.status_code == 200
    assert "ORG-ONE-MARKER" in resp.text
    assert "ORG-TWO-MARKER" not in resp.text


def test_feedback_export_returns_csv_with_redacted_message(tmp_path, monkeypatch):
    """MLRO export returns CSV; PII in the free-text message is redacted,
    same as /audit/export does for its own free-text detail field."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, utcnow
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    _make_org_and_operators(conn, 1, "org-1")
    now = utcnow()
    conn.execute(
        "INSERT INTO feedback (org_id, operator_id, page, message, created_at)"
        " VALUES (?,?,?,?,?)",
        (1, 1, "/customers", "contact me at leak@example.com about this bug", now),
    )
    conn.commit()
    mlro_id = conn.execute("SELECT id FROM operators WHERE role='mlro'").fetchone()["id"]
    token = auth.create_session(conn, operator_id=mlro_id, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)
    resp = client.get("/admin/feedback/export")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    assert "leak@example.com" not in resp.text


def test_feedback_export_requires_mlro_role(tmp_path, monkeypatch):
    """GET /admin/feedback/export requires MLRO role -- officers get 403."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    _make_org_and_operators(conn, 1, "org-1")
    officer_id = conn.execute("SELECT id FROM operators WHERE role='officer'").fetchone()["id"]
    token = auth.create_session(conn, operator_id=officer_id, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)
    resp = client.get("/admin/feedback/export", follow_redirects=False)
    assert resp.status_code in (303, 403)

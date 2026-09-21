"""Tests for audit activity feed widget on dashboard (p56)."""

from __future__ import annotations

import json
import os
import re
import sqlite3

import pytest


def _seed_sanctions_data(db_file):
    from amlkit.db import connect, upsert_dataset, utcnow
    from amlkit.names.arabic import blocking_keys, canonical_key

    conn = connect(db_file)
    ds = upsert_dataset(conn, "test_list", "Test List", is_mandatory=True)
    now = utcnow()
    cur = conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           countries, birth_date, gender, topics, programs, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "T-1", "Person", "John Doe", '["ae"]', "1980-01-01", "male",
         '["sanction"]', '["TEST"]', "{}", now, now),
    )
    eid = cur.lastrowid
    conn.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
        " VALUES (?,?,?,?,?)",
        (eid, "John Doe", "primary", canonical_key("John Doe"), "latin"),
    )
    for tok in blocking_keys("John Doe"):
        conn.execute(
            "INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)",
            (tok, eid),
        )
    conn.execute(
        "UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?",
        (now, ds),
    )
    conn.commit()
    conn.close()


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name, name, email, password="a-strong-password-1"):
    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, "no dev verification link"
    client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    return client


def _db():
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


def _seed_audit_rows(org_id, count=8, actor="test_actor"):
    from amlkit.db import utcnow
    conn = _db()
    for i in range(count):
        conn.execute(
            "INSERT INTO audit_log (org_id, ts, actor, action, detail) VALUES (?,?,?,?,?)",
            (org_id, utcnow(), actor, f"test.action_{i}", json.dumps({"index": i})),
        )
    conn.commit()
    conn.close()


def _seed_other_org_audit(count=3, actor="zz_other_actor", action_prefix="zzother.leak", ts="2001-02-03T04:05:06+00:00"):
    from amlkit.db import utcnow as _utcnow
    conn = _db()
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?, ?, 'active', ?)",
        ("Other Firm", "other-firm", _utcnow()),
    )
    other_org_id = conn.execute("SELECT id FROM organizations WHERE name='Other Firm'").fetchone()["id"]
    from amlkit.db import utcnow
    for i in range(count):
        conn.execute(
            "INSERT INTO audit_log (org_id, ts, actor, action, detail) VALUES (?,?,?,?,?)",
            (other_org_id, ts, actor, f"{action_prefix}_{i}", json.dumps({"index": i})),
        )
    conn.commit()
    conn.close()


@pytest.fixture()
def mlro_client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Audit Firm", "audit_mlro", "mlro@audit.ae")
    return c


@pytest.fixture()
def officer_client(mlro_client):
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    created = mlro_client.post("/admin/operators", data={
        "name": "audit_officer", "email": "officer@audit.ae",
        "password": "a-strong-password-2", "role": "officer",
        "csrf_token": _csrf(mlro_client),
    }, follow_redirects=False)
    assert created.status_code in (200, 302, 303), created.status_code
    conn = _db()
    row = conn.execute("SELECT role FROM operators WHERE email=?", ("officer@audit.ae",)).fetchone()
    conn.close()
    assert row is not None and row["role"] == "officer"

    officer = TestClient(app)
    officer.get("/login")
    officer.post("/login", data={
        "email": "officer@audit.ae", "password": "a-strong-password-2",
        "csrf_token": officer.cookies.get("amlkit_csrf"),
    }, follow_redirects=True)
    # Prove the officer session is real, not a /login redirect
    r = officer.get("/dashboard", follow_redirects=False)
    assert r.status_code == 200, r.status_code
    return officer


class TestAuditFeedWidget:
    def test_mlro_sees_audit_feed(self, mlro_client):
        conn = _db()
        org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
        conn.close()

        _seed_audit_rows(org_id, count=8)
        _seed_other_org_audit(count=3)

        r = mlro_client.get("/dashboard")
        assert r.status_code == 200
        assert "Recent activity" in r.text

        for i in range(2, 8):
            assert f"test action {i}" in r.text
        assert "test action 0" not in r.text
        assert "test action 1" not in r.text
        # distinctive other-org values must not leak in any form
        for leaked in ("zz_other_actor", "zzother", "2001-02-03", "Other Firm"):
            assert leaked not in r.text

    def test_officer_does_not_see_widget(self, mlro_client, officer_client):
        conn = _db()
        org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
        conn.close()
        _seed_audit_rows(org_id, count=4)

        r = officer_client.get("/dashboard")
        assert r.status_code == 200
        assert "Recent activity" not in r.text
        assert "test action" not in r.text

    def test_null_object_type_renders(self, mlro_client):
        conn = _db()
        org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
        conn.close()
        _seed_audit_rows(org_id, count=1, actor="nullobj_actor")
        r = mlro_client.get("/dashboard")
        assert r.status_code == 200
        assert "nullobj_actor" in r.text
        assert "nullobj_actor &middot;" not in r.text

    def test_recent_audit_empty_state(self, tmp_path):
        from amlkit.db import connect
        from amlkit import queries
        conn = connect(tmp_path / "e.db")
        assert queries.recent_audit(conn, 999) == []
        conn.close()

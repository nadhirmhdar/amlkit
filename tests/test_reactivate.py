"""Tests for POST /customers/{id}/reactivate — MLRO-only reactivation of closed customers."""

from __future__ import annotations

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
        "csrf_token": _csrf(client), "invite_code": "test-invite",
    }, follow_redirects=True)
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, "no dev verification link"
    client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    return client


def _db():
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


def _onboard_customer(client, name="Test Customer"):
    client.get("/customers/new")
    client.post("/customers", data={
        "reference": f"REF-{name[:5]}",
        "full_name": name,
        "customer_type": "natural",
        "nationality": "AE",
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    conn = _db()
    row = conn.execute(
        "SELECT id FROM customers WHERE full_name=? ORDER BY id DESC LIMIT 1",
        (name,),
    ).fetchone()
    conn.close()
    return row["id"]


def _close_customer(client, customer_id):
    client.post(f"/customers/{customer_id}/close", data={
        "csrf_token": _csrf(client),
    }, follow_redirects=True)


@pytest.fixture()
def mlro_client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Reactivate Firm", "mlro_user", "mlro@react.ae")
    return c


@pytest.fixture()
def officer_client(mlro_client):
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    mlro_client.post("/admin/operators", data={
        "name": "officer_user", "email": "officer@react.ae",
        "password": "a-strong-password-2", "role": "officer",
        "csrf_token": _csrf(mlro_client),
    })

    officer = TestClient(app)
    officer.get("/login")
    officer.post("/login", data={
        "email": "officer@react.ae", "password": "a-strong-password-2",
        "csrf_token": officer.cookies.get("amlkit_csrf"),
    }, follow_redirects=True)
    return officer


class TestReactivate:
    def test_mlro_can_reactivate_closed_customer(self, mlro_client):
        cid = _onboard_customer(mlro_client)
        _close_customer(mlro_client, cid)

        conn = _db()
        assert conn.execute("SELECT status FROM customers WHERE id=?", (cid,)).fetchone()["status"] == "closed"
        conn.close()

        r = mlro_client.post(f"/customers/{cid}/reactivate", data={
            "reason": "Relationship resumed per board decision",
            "csrf_token": _csrf(mlro_client),
        }, follow_redirects=True)
        assert r.status_code == 200

        conn = _db()
        row = conn.execute("SELECT status, retention_until FROM customers WHERE id=?", (cid,)).fetchone()
        assert row["status"] == "active"
        assert row["retention_until"] is not None
        conn.close()

    def test_officer_gets_403(self, mlro_client, officer_client):
        cid = _onboard_customer(mlro_client)
        _close_customer(mlro_client, cid)

        r = officer_client.post(f"/customers/{cid}/reactivate", data={
            "reason": "Trying to reactivate",
            "csrf_token": _csrf(officer_client),
        }, follow_redirects=True)
        assert "mlro" in r.text.lower() or r.status_code == 403

        conn = _db()
        assert conn.execute("SELECT status FROM customers WHERE id=?", (cid,)).fetchone()["status"] == "closed"
        conn.close()

    def test_reactivate_active_customer_returns_error(self, mlro_client):
        cid = _onboard_customer(mlro_client, name="Active Customer")

        r = mlro_client.post(f"/customers/{cid}/reactivate", data={
            "reason": "This should fail",
            "csrf_token": _csrf(mlro_client),
        }, follow_redirects=True)
        assert r.status_code == 200
        assert "already active" in r.text.lower() or "not closed" in r.text.lower() or "only closed" in r.text.lower()

    def test_retention_until_reset_on_reactivation(self, mlro_client):
        from datetime import date
        cid = _onboard_customer(mlro_client, name="Retention Test")
        _close_customer(mlro_client, cid)

        conn = _db()
        closed_retention = conn.execute(
            "SELECT retention_until FROM customers WHERE id=?", (cid,)
        ).fetchone()["retention_until"]
        assert closed_retention is not None
        conn.close()

        mlro_client.post(f"/customers/{cid}/reactivate", data={
            "reason": "Resetting retention",
            "csrf_token": _csrf(mlro_client),
        }, follow_redirects=True)

        conn = _db()
        row = conn.execute(
            "SELECT status, retention_until FROM customers WHERE id=?", (cid,)
        ).fetchone()
        assert row["status"] == "active"
        assert row["retention_until"] is not None
        retention_date = date.fromisoformat(row["retention_until"])
        assert retention_date.year >= date.today().year + 9
        conn.close()

    def test_audit_row_created(self, mlro_client):
        cid = _onboard_customer(mlro_client, name="Audit Test")
        _close_customer(mlro_client, cid)

        mlro_client.post(f"/customers/{cid}/reactivate", data={
            "reason": "Board approved",
            "csrf_token": _csrf(mlro_client),
        }, follow_redirects=True)

        conn = _db()
        row = conn.execute(
            "SELECT * FROM audit_log WHERE action='customer.reactivated' AND object_id=?",
            (str(cid),),
        ).fetchone()
        assert row is not None
        assert "Board approved" in row["detail"]
        conn.close()

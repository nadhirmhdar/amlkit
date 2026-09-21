"""Tests for GET /alerts/{id}/panel — inline alert detail fragment."""

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


def _insert_alert(org_id: int, customer_id=None, query_name="Adhoc Query") -> int:
    """Insert a screening + open alert directly for the given org."""
    from amlkit.db import utcnow

    conn = _db()
    ent = conn.execute("SELECT id FROM entities LIMIT 1").fetchone()["id"]
    now = utcnow()
    cur = conn.execute(
        "INSERT INTO screenings (org_id, customer_id, query_name, trigger, algorithm,"
        " threshold, run_at) VALUES (?,?,?,?,?,?,?)",
        (org_id, customer_id, query_name, "adhoc", "test", 0.8, now),
    )
    cur2 = conn.execute(
        "INSERT INTO alerts (org_id, screening_id, entity_id, score, score_detail,"
        " matched_name, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (org_id, cur.lastrowid, ent, 0.91, "{}", "John Doe", "open", now),
    )
    conn.commit()
    conn.close()
    return cur2.lastrowid


def _org_ids() -> list[int]:
    conn = _db()
    ids = [r["id"] for r in conn.execute("SELECT id FROM organizations ORDER BY id")]
    conn.close()
    return ids


def _first_alert_id() -> int:
    conn = _db()
    row = conn.execute("SELECT id FROM alerts ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if row:
        return row["id"]
    # Screening did not fire in setup; create an alert for the customer's org.
    org_id = _org_ids()[0]
    conn = _db()
    cust = conn.execute("SELECT id FROM customers WHERE org_id=?", (org_id,)).fetchone()
    conn.close()
    return _insert_alert(org_id, cust["id"] if cust else None)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Panel Firm", "panel_user", "panel@test.ae")

    c.get("/customers/new")
    c.post("/customers", data={
        "reference": "PANEL-001",
        "full_name": "John Doe",
        "customer_type": "natural",
        "nationality": "AE",
        "csrf_token": _csrf(c),
    }, follow_redirects=True)
    return c


class TestAlertPanel:
    def test_panel_returns_fragment_with_customer_name(self, client):
        aid = _first_alert_id()
        r = client.get(f"/alerts/{aid}/panel")
        assert r.status_code == 200
        assert "John Doe" in r.text
        assert "<html" not in r.text.lower()
        # Panel root must not carry data-alert-id (would hijack delegated clicks).
        assert "data-alert-id" not in r.text

    def test_panel_404_cross_org(self, client):
        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        other = TestClient(app)
        _register(other, "Other Firm", "other_user", "other@test.ae")
        org_ids = _org_ids()
        assert len(org_ids) == 2
        foreign_alert = _insert_alert(org_ids[1], None, "Other Org Query")
        # Original client (org 1) must not see org 2's real alert.
        r = client.get(f"/alerts/{foreign_alert}/panel")
        assert r.status_code == 404
        assert "<html" not in r.text.lower()
        # Sanity: the owning org can see it.
        assert other.get(f"/alerts/{foreign_alert}/panel").status_code == 200

    def test_panel_404_missing(self, client):
        assert client.get("/alerts/999999/panel").status_code == 404

    def test_assign_form_has_real_csrf_token(self, client):
        aid = _first_alert_id()
        r = client.get(f"/alerts/{aid}/panel")
        m = re.search(r'name="csrf_token" value="([^"]*)"', r.text)
        assert m and m.group(1)
        assert m.group(1) == _csrf(client)

    def test_unauthenticated_returns_401(self, client):
        aid = _first_alert_id()
        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        anon = TestClient(app)
        r = anon.get(f"/alerts/{aid}/panel", follow_redirects=False)
        assert r.status_code == 401

    def test_null_customer_alert_renders(self, client):
        aid = _insert_alert(_org_ids()[0], None, "Walk-in Query")
        r = client.get(f"/alerts/{aid}/panel")
        assert r.status_code == 200
        assert "/customers/None" not in r.text
        assert "Walk-in Query" in r.text

    def test_js_file_served(self, client):
        r = client.get("/static/js/alert-panel.js")
        assert r.status_code == 200
        assert "javascript" in r.headers.get("content-type", "")

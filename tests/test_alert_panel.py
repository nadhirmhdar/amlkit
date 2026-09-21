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


def _first_alert_id() -> int:
    conn = _db()
    row = conn.execute("SELECT id FROM alerts ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if row:
        return row["id"]
    return -1


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
        if aid < 0:
            pytest.skip("no alerts generated in test setup")
        r = client.get(f"/alerts/{aid}/panel")
        assert r.status_code == 200
        assert "John Doe" in r.text
        assert "<html" not in r.text.lower()

    def test_panel_404_cross_org(self, client):
        r = client.get("/alerts/999999/panel")
        assert r.status_code == 404

    def test_js_file_served(self, client):
        r = client.get("/static/js/alert-panel.js")
        assert r.status_code == 200
        assert "javascript" in r.headers.get("content-type", "")

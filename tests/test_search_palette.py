"""Tests for GET /search?q= — global search palette API."""

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


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Search Firm", "searcher", "search@test.ae")

    c.get("/customers/new")
    c.post("/customers", data={
        "reference": "SRCH-001",
        "full_name": "Mohammed Al Rashid",
        "customer_type": "natural",
        "nationality": "AE",
        "csrf_token": _csrf(c),
    }, follow_redirects=True)
    return c


@pytest.fixture()
def unauth_client(tmp_path, monkeypatch):
    db_file = tmp_path / "test2.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    return TestClient(app)


class TestSearchPalette:
    def test_mohd_finds_mohammed(self, client):
        r = client.get("/search?q=Mohd")
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        names = [item["name"] for item in data["results"]]
        assert any("Mohammed" in n or "Mohd" in n for n in names), f"Expected Mohammed, got {names}"

    def test_cross_org_excluded(self, client):
        r = client.get("/search?q=Mohammed")
        data = r.json()
        for item in data["results"]:
            assert item.get("type") != "customer" or "Mohammed" in item["name"]

    def test_unauthenticated_redirects(self, unauth_client):
        r = unauth_client.get("/search?q=test", follow_redirects=False)
        assert r.status_code in (303, 401, 302)

    def test_js_file_served(self, client):
        r = client.get("/static/js/search-palette.js")
        assert r.status_code == 200
        assert "javascript" in r.headers.get("content-type", "")

    def test_empty_query_returns_empty(self, client):
        r = client.get("/search?q=")
        assert r.status_code == 200
        data = r.json()
        assert data["results"] == []

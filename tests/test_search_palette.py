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
    c.db_file = db_file
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


def _add_customer(c, ref, name):
    c.get("/customers/new")
    c.post("/customers", data={
        "reference": ref, "full_name": name, "customer_type": "natural",
        "nationality": "AE", "csrf_token": _csrf(c),
    }, follow_redirects=True)


def _add_alert(db_file, customer_ref, query_name):
    """Insert an open alert; customer_ref=None makes an ad-hoc (no customer) one."""
    from amlkit.db import connect, utcnow
    conn = connect(db_file)
    now = utcnow()
    org_id = conn.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()[0]
    cid = None
    if customer_ref:
        cid = conn.execute("SELECT id FROM customers WHERE reference=?",
                           (customer_ref,)).fetchone()[0]
    eid = conn.execute("SELECT id FROM entities LIMIT 1").fetchone()[0]
    cur = conn.execute(
        """INSERT INTO screenings (org_id, customer_id, query_name, trigger,
           algorithm, threshold, run_at) VALUES (?,?,?,?,?,?,?)""",
        (org_id, cid, query_name, "adhoc", "jw", 0.8, now))
    sid = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO alerts (org_id, screening_id, entity_id, score,
           score_detail, matched_name, status, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (org_id, sid, eid, 95.0, "{}", "John Doe", "open", now))
    conn.commit()
    aid = cur.lastrowid
    conn.close()
    return aid, cid


class TestSearchPalette:
    def test_mohd_finds_mohammed(self, client):
        r = client.get("/search?q=Mohd")
        assert r.status_code == 200
        data = r.json()
        customers = [i for i in data["results"] if i["type"] == "customer"]
        assert len(customers) == 1
        assert customers[0]["name"] == "Mohammed Al Rashid"
        assert customers[0]["detail"] == "SRCH-001"

    def test_cross_org_excluded(self, client):
        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        other = TestClient(app)
        _register(other, "Other Firm", "other", "other@test.ae")
        _add_customer(other, "OTHER-001", "Mohammed Al Rashid")
        r = client.get("/search?q=Mohammed")
        refs = [i["detail"] for i in r.json()["results"]]
        assert refs == ["SRCH-001"]
        r2 = other.get("/search?q=Mohammed")
        assert [i["detail"] for i in r2.json()["results"]] == ["OTHER-001"]

    def test_alert_branch_links_customer_and_dedupes(self, client):
        a1, cid = _add_alert(client.db_file, "SRCH-001", "Mohammed Al Rashid")
        _add_alert(client.db_file, "SRCH-001", "Mohammed Al Rashid")
        # Query that only matches the alert path (query_name variant), not the customer row
        r = client.get(f"/search?q={a1}")
        alerts = [i for i in r.json()["results"] if i["type"] == "alert"]
        assert len(alerts) == 1
        assert alerts[0]["url"] == f"/customers/{cid}"
        # several alerts for one customer collapse to one alert row
        r = client.get("/search?q=Mohd")
        alerts = [i for i in r.json()["results"] if i["type"] == "alert"]
        assert len(alerts) == 1

    def test_alert_id_is_exact_not_substring(self, client):
        aid, _ = _add_alert(client.db_file, "SRCH-001", "Zed Person")
        assert aid == 1
        for _ in range(10):
            _add_alert(client.db_file, "SRCH-001", "Zed Person")
        # "1" must not match alert #10 or #11 by substring; only alert #1 (same customer -> 1 row)
        r = client.get("/search?q=1")
        alerts = [i for i in r.json()["results"] if i["type"] == "alert"]
        assert all("Alert #1 " in i["detail"] for i in alerts)

    def test_adhoc_alert_has_no_dead_customer_link(self, client):
        _add_alert(client.db_file, None, "Zaid Unknownson")
        r = client.get("/search?q=Zaid")
        alerts = [i for i in r.json()["results"] if i["type"] == "alert"]
        assert len(alerts) == 1
        assert "None" not in alerts[0]["url"]
        assert alerts[0]["url"] == "/alerts"

    def test_alert_matches_query_name_canonically(self, client):
        _add_alert(client.db_file, None, "Mohd Al Rashid")
        r = client.get("/search?q=Mohammed Rashid")
        assert any(i["type"] == "alert" for i in r.json()["results"])

    def test_results_capped_at_ten(self, client):
        for i in range(15):
            _add_customer(client, f"CAP-{i:03d}", f"Capped Person {i}")
        r = client.get("/search?q=Capped")
        assert len(r.json()["results"]) == 10

    def test_percent_and_underscore_are_literal(self, client):
        _add_customer(client, "LIT-1", "Plain Name")
        _add_customer(client, "LIT-2", "Rate 50% Holdings")
        _add_customer(client, "LIT-3", "Under_score Trading")
        assert client.get("/search?q=%25").json()["results"][0]["name"] == "Rate 50% Holdings"
        assert len(client.get("/search?q=%25").json()["results"]) == 1
        r = client.get("/search?q=_").json()["results"]
        assert [i["name"] for i in r] == ["Under_score Trading"]

    def test_unauthenticated_json_caller_gets_redirect_not_data(self, unauth_client):
        r = unauth_client.get("/search?q=test", follow_redirects=False,
                              headers={"accept": "application/json"})
        assert r.status_code == 303
        assert r.headers["location"] == "/login"

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
        assert r.json()["results"] == []

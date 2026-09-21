"""Issue #100: Alerts page renders N duplicate select[name=status] elements.

When multiple alerts exist, disposition_form() renders one form per alert,
each with <select name="status">. HTML allows this (separate forms), but
JavaScript querySelectorAll and accessibility tools expect unique IDs.

The fix: add id="status_{{ alert.id }}" to each select.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from amlkit.api.app import app


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name: str, name: str, email: str, password: str = "Password123"):
    import re as regex
    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client), "invite_code": "test-invite",
    }, follow_redirects=True)
    assert "Check your email" in r.text, f"registration failed: {r.text[:300]}"
    m = regex.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, f"no dev verification link: {r.text[:500]}"
    r2 = client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    from conftest import settle_mfa  # p15: MLRO sessions start locked
    settle_mfa(client)
    assert any(s in r2.text for s in ("Dashboard", "24-hour", "Two-Factor"))
    return client


def _seed_sanctions_data(db_file) -> None:
    """Seed DB with one sanctioned entity to generate alerts."""
    from amlkit.db import connect, upsert_dataset, utcnow
    from amlkit.names.arabic import blocking_keys, canonical_key

    conn = connect(db_file)
    ds = upsert_dataset(conn, "test_list", "Test Sanctions List", is_mandatory=True)
    now = utcnow()

    listed = "AHMED TEST SUBJECT"
    cur = conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption, countries,
           birth_date, gender, topics, programs, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "T-1", "Person", listed, '["ly"]', "1975-03-12", "male",
         '["sanction"]', '["AE-UNSC1373"]', "{}", now, now),
    )
    eid = cur.lastrowid
    conn.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
        " VALUES (?,?,?,?,?)",
        (eid, listed, "primary", canonical_key(listed), "latin"))
    for tok in blocking_keys(listed):
        conn.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)", (tok, eid))

    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    conn.commit()
    conn.close()


@pytest.fixture
def client_with_alerts(tmp_path, monkeypatch):
    """Client with org, operator, and 3 open alerts."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    # Mock UBO diagram generation to avoid Graphviz dependency
    def mock_diagram(*args, **kwargs):
        return "<svg>Mock diagram</svg>"
    monkeypatch.setattr("amlkit.cases.diagram.generate_ubo_diagram", mock_diagram)

    _seed_sanctions_data(db_file)

    client = TestClient(app)
    _register(client, "Test Firm", "Alice", "alice@test.com")

    # Create 3 customers that match the sanctioned entity (creating 3 alerts)
    for i in range(3):
        client.post("/customers", data={
            "reference": f"C-{i}",
            "full_name": f"Test Company {i}",
            "customer_type": "legal",
            "ubo_names": ["Ahmed Test Subject"],
            "ubo_pcts": ["60"],
            "ubo_controls": ["ownership"],
            "csrf_token": _csrf(client),
        }, follow_redirects=True)

    return client


def test_alerts_page_status_selects_have_unique_ids(client_with_alerts):
    """Each status select must have a unique ID for JS and accessibility."""
    client = client_with_alerts

    resp = client.get("/alerts?status=open")
    assert resp.status_code == 200
    html = resp.text

    # Count how many <select name="status"> exist
    status_selects = re.findall(r'<select[^>]+name="status"[^>]*>', html)
    assert len(status_selects) == 3, f"Expected 3 status selects, got {len(status_selects)}"

    # Each must have a unique ID
    ids = re.findall(r'<select[^>]+name="status"[^>]+id="([^"]+)"', html)
    assert len(ids) == 3, f"Expected 3 IDs on status selects, found {len(ids)}"
    assert len(set(ids)) == 3, f"IDs not unique: {ids}"

    # Verify format is status_<alert_id>
    # Get alert IDs from DB to verify
    from amlkit import db
    conn = db.connect(os.environ["AMLKIT_DB"])
    alert_ids = [row[0] for row in conn.execute("SELECT id FROM alerts ORDER BY id").fetchall()]
    conn.close()

    for alert_id in alert_ids:
        expected_id = f"status_{alert_id}"
        assert expected_id in ids, f"Missing expected ID {expected_id} in {ids}"

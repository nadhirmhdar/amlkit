"""t8: Full E2E integration test — org onboarding through STR export.

Exercises the complete happy path a regulated entity follows:
  register org → onboard customer (sanctions hit) → alert generated →
  disposition (true positive) → save STR report → submit → export goAML XML

Each step is an HTTP request through the real FastAPI app, the same way
a browser session would. No mocks, no direct DB writes for business logic.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LISTED = "AHMED ABD AL-JALEEL AL-HASNAWI"


def _seed_sanctions_data(db_file) -> None:
    from amlkit.db import connect, upsert_dataset, utcnow
    from amlkit.names.arabic import blocking_keys, canonical_key

    conn = connect(db_file)
    ds = upsert_dataset(conn, "test_list", "Test Sanctions List", is_mandatory=True)
    now = utcnow()
    cur = conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption, countries,
           birth_date, gender, topics, programs, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "T-1", "Person", LISTED, '["ly"]', "1975-03-12", "male",
         '["sanction"]', '["AE-UNSC1373"]', "{}", now, now),
    )
    eid = cur.lastrowid
    for nm in [LISTED]:
        conn.execute(
            "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
            " VALUES (?,?,?,?,?)",
            (eid, nm, "primary", canonical_key(nm), "latin"))
        for tok in blocking_keys(nm):
            conn.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)",
                         (tok, eid))
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    conn.commit()
    conn.close()


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name, name, email, password="TestPass2026!"):
    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client), "invite_code": "test-invite",
    }, follow_redirects=True)
    assert "Check your email" in r.text, f"registration failed: {r.text[:300]}"
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, f"no dev verification link: {r.text[:500]}"
    r2 = client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    from conftest import settle_mfa  # p15: MLRO sessions start locked
    settle_mfa(client)
    assert any(s in r2.text for s in ("Dashboard", "24-hour", "Two-Factor")), f"verify failed: {r2.text[:300]}"
    return client


def _db():
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "E2E Happy Path Ltd", "mlro_alice", "alice@e2e.ae")
    return c


class TestE2EHappyPath:
    """Full lifecycle: register → onboard → screen → alert → disposition → STR → export."""

    def test_full_onboard_to_str_export(self, client):
        # ── Step 1: Onboard a customer whose name matches a sanctioned entity ──
        r = client.post("/customers", data={
            "reference": "E2E-001",
            "full_name": LISTED,
            "customer_type": "natural",
            "nationality": "ly",
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        assert r.status_code == 200

        conn = _db()
        cust = conn.execute("SELECT id FROM customers WHERE reference='E2E-001'").fetchone()
        assert cust is not None, "customer not onboarded"
        customer_id = cust["id"]

        # ── Step 2: Verify an alert was auto-generated from the sanctions match ──
        alert = conn.execute(
            """SELECT a.id, a.status FROM alerts a
               JOIN screenings s ON a.screening_id = s.id
               WHERE s.customer_id=? ORDER BY a.id DESC LIMIT 1""",
            (customer_id,)
        ).fetchone()
        conn.close()
        assert alert is not None, "no alert generated for sanctioned name"
        assert alert["status"] == "open"
        alert_id = alert["id"]

        # ── Step 3: Disposition the alert as true positive (no four-eyes needed) ──
        r = client.post(f"/alerts/{alert_id}/disposition", data={
            "status": "true_positive",
            "reason_code": "confirmed_match",
            "narrative": "Name, nationality, and DOB match the UNSC designation.",
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        assert r.status_code == 200

        conn = _db()
        alert_after = conn.execute("SELECT status FROM alerts WHERE id=?", (alert_id,)).fetchone()
        conn.close()
        assert alert_after["status"] == "true_positive"

        # ── Step 4: Save an STR report for this customer ──
        r = client.post("/reports", data={
            "customer_id": customer_id,
            "report_type": "STR",
            "reporting_entity_name": "E2E Happy Path Ltd",
            "entity_reference": "LIC-E2E",
            "reporter_name": "mlro_alice",
            "reporter_email": "alice@e2e.ae",
            "first_name": "AHMED ABD AL-JALEEL",
            "last_name": "AL-HASNAWI",
            "nationality": "LY",
            "amount": "100000",
            "transaction_type": "Wire Transfer",
            "source_account": "AE070331234567890123456",
            "destination_account": "AE070339876543210987654",
            "reason_description": "Customer matched UNSC-designated individual. "
                                  "Large wire transfer inconsistent with profile.",
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        assert r.status_code == 200

        conn = _db()
        report = conn.execute(
            "SELECT id, status, report_type FROM reports WHERE customer_id=? ORDER BY id DESC LIMIT 1",
            (customer_id,)
        ).fetchone()
        conn.close()
        assert report is not None, "STR report not saved"
        assert report["report_type"] == "STR"
        report_id = report["id"]

        # ── Step 5: Submit the report (MLRO action) ──
        r = client.post(f"/reports/{report_id}/submit", data={
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        assert r.status_code == 200

        conn = _db()
        submitted = conn.execute("SELECT status FROM reports WHERE id=?", (report_id,)).fetchone()
        conn.close()
        assert submitted["status"] == "submitted"

        # ── Step 6: Export the goAML XML and verify structure ──
        r = client.get(f"/reports/{report_id}/export")
        assert r.status_code == 200
        xml = r.text
        assert "<report_code>STR</report_code>" in xml
        assert "AL-HASNAWI" in xml
        assert "E2E Happy Path" in xml or "LIC-E2E" in xml

"""HTTP route tests for freeze obligation routes.

Tests role-based access control (MLRO vs officer), tenant isolation,
and the happy path for execute/file-ffr/resolve operations.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Reuse test_api's client fixture and helpers
from test_api import client, _csrf, _add_operator, _login, _register  # noqa: E402,F401


def _db() -> sqlite3.Connection:
    """Short-lived connection to the test database."""
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


def test_execute_nonexistent_freeze_returns_error_not_500(client):
    """POST /freeze-obligations/99999/execute returns error, not 500."""
    r = client.post("/freeze-obligations/99999/execute",
                    data={"csrf_token": _csrf(client), "notes": "Test"},
                    follow_redirects=True)

    # Should NOT be a 500
    assert r.status_code == 200, f"Expected 200 with error, got {r.status_code}"
    # Should show error message
    assert "not found" in r.text.lower() or "err=" in str(r.url).lower()


def test_resolve_nonexistent_freeze_returns_error_not_500(client):
    """POST /freeze-obligations/99999/resolve returns error, not 500."""
    r = client.post("/freeze-obligations/99999/resolve",
                    data={"csrf_token": _csrf(client),
                          "resolution_reason": "delisted",
                          "notes": "Test"},
                    follow_redirects=True)

    # Should NOT be a 500
    assert r.status_code == 200, f"Expected 200 with error, got {r.status_code}"
    # Should show error message
    assert "not found" in r.text.lower() or "err=" in str(r.url).lower()


def test_mlro_can_execute_freeze(client):
    """MLRO can execute a freeze obligation with asset details."""
    from amlkit.db import utcnow

    # Create customer and freeze obligation
    conn = _db()
    org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
    now = utcnow()
    cur = conn.execute("""
        INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
                               status, onboarded_at, created_at, updated_at)
        VALUES (?, 'C-FREEZE-1', 'Test Customer', 'natural', 'test_customer', 'active', ?, ?, ?)
    """, (org_id, now, now, now))
    customer_id = cur.lastrowid

    cur = conn.execute("""
        INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
                                        status, identified_at, identified_by, authority_ref)
        VALUES (?, ?, 'sanctions', 'critical', 'pending_execution', ?, 'alice', 'UN-123')
    """, (org_id, customer_id, now))
    freeze_id = cur.lastrowid
    conn.commit()
    conn.close()

    # MLRO executes the freeze with asset details
    r = client.post(f"/freeze-obligations/{freeze_id}/execute",
                    data={
                        "csrf_token": _csrf(client),
                        "notes": "Accounts frozen per UNSC resolution",
                        "asset_type_1": "bank_account",
                        "asset_identifier_1": "AE12345678901234567890",
                        "asset_amount_1": "50000.00",
                    },
                    follow_redirects=True)

    assert r.status_code == 200
    assert "successfully" in r.text.lower() or str(freeze_id) in str(r.url)

    # Verify DB state changed
    conn = _db()
    row = conn.execute("SELECT status, executed_at, assets_frozen FROM freeze_obligations WHERE id=?",
                       (freeze_id,)).fetchone()
    conn.close()

    assert row["status"] == "executed_pending_report"
    assert row["executed_at"] is not None
    assert "bank_account" in row["assets_frozen"]


def test_mlro_can_file_ffr_and_resolve(client):
    """MLRO can file FFR and resolve a freeze obligation."""
    from amlkit.db import utcnow

    # Create customer and executed freeze obligation
    conn = _db()
    org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
    now = utcnow()
    cur = conn.execute("""
        INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
                               status, birth_date, gender, nationality, id_number, id_type,
                               onboarded_at, created_at, updated_at)
        VALUES (?, 'C-FREEZE-2', 'Ahmad Al-Test', 'natural', 'ahmad_al_test', 'active',
                '1980-05-15', 'male', 'SY', '123456789', 'passport', ?, ?, ?)
    """, (org_id, now, now, now))
    customer_id = cur.lastrowid

    cur = conn.execute("""
        INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
                                        status, identified_at, identified_by, executed_at,
                                        executed_by, assets_frozen, authority_ref)
        VALUES (?, ?, 'sanctions', 'critical', 'executed_pending_report', ?, 'alice', ?, 'alice',
                '[{"type":"cash","identifier":"USD","amount_aed":10000}]', 'UN-456')
    """, (org_id, customer_id, now, now))
    freeze_id = cur.lastrowid
    conn.commit()
    conn.close()

    # MLRO files FFR
    r = client.post(f"/freeze-obligations/{freeze_id}/file-ffr",
                    data={
                        "csrf_token": _csrf(client),
                        "reporter_name": "Alice MLRO",
                        "reporter_email": "alice@testfirm.ae",
                    },
                    follow_redirects=True)

    assert r.status_code == 200
    assert "/reports/" in str(r.url)

    # Verify status changed to reported
    conn = _db()
    row = conn.execute("SELECT status, reported_at, report_id FROM freeze_obligations WHERE id=?",
                       (freeze_id,)).fetchone()
    assert row["status"] == "reported"
    assert row["reported_at"] is not None
    assert row["report_id"] is not None

    # Now resolve it
    r2 = client.post(f"/freeze-obligations/{freeze_id}/resolve",
                     data={
                         "csrf_token": _csrf(client),
                         "resolution_reason": "delisted",
                         "authority_ref": "UN-DELIST-789",
                         "notes": "Entity removed from UNSC list",
                     },
                     follow_redirects=True)

    assert r2.status_code == 200

    # Verify resolved
    row2 = conn.execute("SELECT status, resolved_at FROM freeze_obligations WHERE id=?",
                        (freeze_id,)).fetchone()
    conn.close()

    assert row2["status"] == "resolved"
    assert row2["resolved_at"] is not None


def test_officer_cannot_execute_freeze(client):
    """Officer role is rejected when trying to execute freeze."""
    from amlkit.db import utcnow

    # Create freeze obligation
    conn = _db()
    org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
    now = utcnow()
    cur = conn.execute("""
        INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
                               status, onboarded_at, created_at, updated_at)
        VALUES (?, 'C-FREEZE-3', 'Test Customer', 'natural', 'test_customer_3', 'active', ?, ?, ?)
    """, (org_id, now, now, now))
    customer_id = cur.lastrowid

    cur = conn.execute("""
        INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
                                        status, identified_at, identified_by, authority_ref)
        VALUES (?, ?, 'sanctions', 'critical', 'pending_execution', ?, 'alice', 'UN-999')
    """, (org_id, customer_id, now))
    freeze_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Add an officer and log in as them
    _add_operator(client, "charlie", "charlie@testfirm.ae", role="officer")

    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    officer_client = TestClient(app)
    officer_client.get("/login")
    _login(officer_client, "charlie@testfirm.ae", "a-strong-password-2")

    # Officer attempts to execute
    r = officer_client.post(f"/freeze-obligations/{freeze_id}/execute",
                            data={
                                "csrf_token": _csrf(officer_client),
                                "notes": "Attempting execution as officer",
                            },
                            follow_redirects=True)

    assert r.status_code == 200
    assert "mlro" in r.text.lower() or "err=" in str(r.url).lower()

    # Verify DB unchanged
    conn = _db()
    row = conn.execute("SELECT status, executed_at FROM freeze_obligations WHERE id=?",
                       (freeze_id,)).fetchone()
    conn.close()

    assert row["status"] == "pending_execution"
    assert row["executed_at"] is None


def test_cross_org_freeze_isolation(client):
    """Org A MLRO cannot execute Org B's freeze obligation."""
    from amlkit.db import utcnow

    # Create freeze in alice's org (the client fixture)
    conn = _db()
    org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
    now = utcnow()
    cur = conn.execute("""
        INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
                               status, onboarded_at, created_at, updated_at)
        VALUES (?, 'C-FREEZE-4', 'Alice Org Customer', 'natural', 'alice_org_customer', 'active', ?, ?, ?)
    """, (org_id, now, now, now))
    customer_id = cur.lastrowid

    cur = conn.execute("""
        INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
                                        status, identified_at, identified_by, authority_ref)
        VALUES (?, ?, 'pf', 'critical', 'pending_execution', ?, 'alice', 'PF-111')
    """, (org_id, customer_id, now))
    alice_freeze_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Register second org
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    bob_client = TestClient(app)
    _register(bob_client, "Other Firm", "bob", "bob@otherfirm.ae", "strong-pass-123")

    # Bob (different org MLRO) tries to execute Alice's freeze
    r = bob_client.post(f"/freeze-obligations/{alice_freeze_id}/execute",
                        data={
                            "csrf_token": _csrf(bob_client),
                            "notes": "Cross-org execution attempt",
                        },
                        follow_redirects=True)

    assert r.status_code == 200
    assert "not found" in r.text.lower() or "err=" in str(r.url).lower()

    # Verify alice's freeze unchanged
    conn = _db()
    row = conn.execute("SELECT status, executed_at FROM freeze_obligations WHERE id=?",
                       (alice_freeze_id,)).fetchone()
    conn.close()

    assert row["status"] == "pending_execution"
    assert row["executed_at"] is None


def test_freeze_list_view_renders(client):
    """GET /freeze-obligations list view renders successfully."""
    r = client.get("/freeze-obligations")
    assert r.status_code == 200
    assert "Freeze Obligations" in r.text

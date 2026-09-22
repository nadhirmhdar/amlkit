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
    # Set goaml_entity_reference (required for FFR filing)
    conn.execute("UPDATE organizations SET goaml_entity_reference = ? WHERE id = ?", ("TEST-ORG-FFR", org_id))
    conn.commit()
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
    """GET /freeze-obligations list view renders successfully.

    Asserts on body content (not just the <title> tag, which is set by a
    separate block and would still read "Freeze Obligations" even if the
    page body itself were blank).
    """
    r = client.get("/freeze-obligations")
    assert r.status_code == 200
    assert "TFS Freeze Obligations" in r.text
    assert "Cabinet Resolution 134/2025" in r.text


def test_freeze_detail_view_renders(client):
    """GET /freeze-obligations/{id} detail view renders the obligation body."""
    from amlkit.db import utcnow

    conn = _db()
    org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
    now = utcnow()
    cur = conn.execute("""
        INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
                               status, onboarded_at, created_at, updated_at)
        VALUES (?, 'C-FREEZE-DETAIL', 'Detail Test Customer', 'natural', 'detail_test_customer',
                'active', ?, ?, ?)
    """, (org_id, now, now, now))
    customer_id = cur.lastrowid

    cur = conn.execute("""
        INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
                                        status, identified_at, identified_by, authority_ref)
        VALUES (?, ?, 'sanctions', 'critical', 'pending_execution', ?, 'alice', 'UN-456')
    """, (org_id, customer_id, now))
    freeze_id = cur.lastrowid
    conn.commit()
    conn.close()

    r = client.get(f"/freeze-obligations/{freeze_id}")
    assert r.status_code == 200
    assert f"Freeze Obligation #{freeze_id}" in r.text
    assert "Detail Test Customer" in r.text
    assert "by alice" in r.text


def test_tenant_isolation_cannot_view_other_org_freeze_list(client):
    """Org A operator cannot see Org B's freeze obligations in list view.

    SECURITY TEST: This test verifies tenant isolation. If this test fails,
    there is a cross-org data leakage vulnerability.
    """
    from amlkit.db import utcnow

    # Create org A (the default test org from _register())
    conn = _db()
    org_a_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]

    # Create org B
    cur = conn.execute("""
        INSERT INTO organizations (name, slug, status, created_at)
        VALUES ('Organization B', 'org-b-test', 'active', ?)
    """, (utcnow(),))
    org_b_id = cur.lastrowid

    # Create customer and freeze obligation in Org B
    now = utcnow()
    cur = conn.execute("""
        INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
                               status, onboarded_at, created_at, updated_at)
        VALUES (?, 'C-ORG-B-001', 'Org B Customer', 'natural', 'org_b_customer',
                'active', ?, ?, ?)
    """, (org_b_id, now, now, now))
    customer_b_id = cur.lastrowid

    cur = conn.execute("""
        INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
                                        status, identified_at, identified_by, authority_ref)
        VALUES (?, ?, 'sanctions', 'critical', 'pending_execution', ?, 'bob', 'UN-789')
    """, (org_b_id, customer_b_id, now))
    freeze_b_id = cur.lastrowid

    # Also create a freeze obligation in Org A for comparison
    cur = conn.execute("""
        INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
                               status, onboarded_at, created_at, updated_at)
        VALUES (?, 'C-ORG-A-001', 'Org A Customer', 'natural', 'org_a_customer',
                'active', ?, ?, ?)
    """, (org_a_id, now, now, now))
    customer_a_id = cur.lastrowid

    conn.execute("""
        INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
                                        status, identified_at, identified_by, authority_ref)
        VALUES (?, ?, 'sanctions', 'critical', 'pending_execution', ?, 'alice', 'UN-999')
    """, (org_a_id, customer_a_id, now))
    freeze_a_id = cur.lastrowid

    conn.commit()
    conn.close()

    # Logged in as Org A operator (default from client fixture)
    r = client.get("/freeze-obligations")
    assert r.status_code == 200

    # Should see Org A's freeze obligation
    assert "C-ORG-A-001" in r.text or "Org A Customer" in r.text

    # CRITICAL: Should NOT see Org B's freeze obligation
    assert "C-ORG-B-001" not in r.text
    assert "Org B Customer" not in r.text


def test_tenant_isolation_cannot_view_other_org_freeze_detail(client):
    """Org A operator cannot access Org B's freeze obligation detail view.

    SECURITY TEST: This test verifies tenant isolation at the detail level.
    Attempting to access another org's freeze obligation should either redirect
    or show "not found" error.
    """
    from amlkit.db import utcnow

    # Get org A (the default test org)
    conn = _db()
    org_a_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]

    # Create org B
    cur = conn.execute("""
        INSERT INTO organizations (name, slug, status, created_at)
        VALUES ('Organization B Detail', 'org-b-detail-test', 'active', ?)
    """, (utcnow(),))
    org_b_id = cur.lastrowid

    # Create freeze obligation in Org B only
    now = utcnow()
    cur = conn.execute("""
        INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
                               status, onboarded_at, created_at, updated_at)
        VALUES (?, 'C-DETAIL-B-001', 'Org B Detail Customer', 'natural', 'org_b_detail_customer',
                'active', ?, ?, ?)
    """, (org_b_id, now, now, now))
    customer_b_id = cur.lastrowid

    cur = conn.execute("""
        INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
                                        status, identified_at, identified_by, authority_ref)
        VALUES (?, ?, 'sanctions', 'critical', 'pending_execution', ?, 'bob', 'UN-DETAIL-999')
    """, (org_b_id, customer_b_id, now))
    freeze_b_id = cur.lastrowid

    conn.commit()
    conn.close()

    # Org A operator tries to access Org B's freeze obligation
    r = client.get(f"/freeze-obligations/{freeze_b_id}", follow_redirects=True)

    # Should get redirected back or see error (not 500)
    assert r.status_code == 200
    # Should show error message about not found
    assert ("not found" in r.text.lower() or "err=" in str(r.url).lower())
    # CRITICAL: Should NOT show Org B's customer details
    assert "Org B Detail Customer" not in r.text
    assert "C-DETAIL-B-001" not in r.text


def test_tenant_isolation_cannot_execute_other_org_freeze(client):
    """Org A MLRO cannot execute Org B's freeze obligation.

    SECURITY TEST: This test verifies tenant isolation for state-changing
    operations. Attempting to execute another org's freeze should fail with
    proper error, not update the record.
    """
    from amlkit.db import utcnow

    # Get org A
    conn = _db()
    org_a_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]

    # Create org B
    cur = conn.execute("""
        INSERT INTO organizations (name, slug, status, created_at)
        VALUES ('Organization B Execute', 'org-b-exec-test', 'active', ?)
    """, (utcnow(),))
    org_b_id = cur.lastrowid

    # Create freeze obligation in Org B
    now = utcnow()
    cur = conn.execute("""
        INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
                               status, onboarded_at, created_at, updated_at)
        VALUES (?, 'C-EXEC-B-001', 'Org B Exec Customer', 'natural', 'org_b_exec_customer',
                'active', ?, ?, ?)
    """, (org_b_id, now, now, now))
    customer_b_id = cur.lastrowid

    cur = conn.execute("""
        INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
                                        status, identified_at, identified_by, authority_ref)
        VALUES (?, ?, 'sanctions', 'critical', 'pending_execution', ?, 'bob', 'UN-EXEC-123')
    """, (org_b_id, customer_b_id, now))
    freeze_b_id = cur.lastrowid

    conn.commit()
    conn.close()

    # Org A MLRO tries to execute Org B's freeze obligation
    r = client.post(f"/freeze-obligations/{freeze_b_id}/execute",
                    data={
                        "csrf_token": _csrf(client),
                        "notes": "Malicious cross-org execution attempt",
                        "asset_type_1": "bank_account",
                        "asset_identifier_1": "HACKED",
                        "asset_amount_1": "999999.00",
                    },
                    follow_redirects=True)

    # Should get error response (not 500)
    assert r.status_code == 200
    assert ("not found" in r.text.lower() or "err=" in str(r.url).lower())

    # CRITICAL: Verify the freeze obligation was NOT modified
    conn = _db()
    row = conn.execute("""
        SELECT status, executed_at, executed_by, assets_frozen
        FROM freeze_obligations WHERE id=?
    """, (freeze_b_id,)).fetchone()
    conn.close()

    assert row["status"] == "pending_execution"  # Status unchanged
    assert row["executed_at"] is None  # Not executed
    assert row["executed_by"] is None  # No executor recorded
    assert row["assets_frozen"] is None or "HACKED" not in (row["assets_frozen"] or "")


def test_tenant_isolation_cannot_resolve_other_org_freeze(client):
    """Org A MLRO cannot resolve Org B's freeze obligation.

    SECURITY TEST: Verifies tenant isolation for resolve operation.
    """
    from amlkit.db import utcnow

    # Get org A
    conn = _db()
    org_a_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]

    # Create org B
    cur = conn.execute("""
        INSERT INTO organizations (name, slug, status, created_at)
        VALUES ('Organization B Resolve', 'org-b-resolve-test', 'active', ?)
    """, (utcnow(),))
    org_b_id = cur.lastrowid

    # Create executed freeze obligation in Org B
    now = utcnow()
    cur = conn.execute("""
        INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
                               status, onboarded_at, created_at, updated_at)
        VALUES (?, 'C-RESOLVE-B-001', 'Org B Resolve Customer', 'natural', 'org_b_resolve_customer',
                'active', ?, ?, ?)
    """, (org_b_id, now, now, now))
    customer_b_id = cur.lastrowid

    cur = conn.execute("""
        INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
                                        status, identified_at, identified_by, executed_at, executed_by,
                                        assets_frozen, authority_ref)
        VALUES (?, ?, 'sanctions', 'critical', 'executed_pending_report', ?, 'bob', ?, 'bob',
                '[{"type":"cash","identifier":"USD","amount_aed":5000}]', 'UN-RESOLVE-456')
    """, (org_b_id, customer_b_id, now, now))
    freeze_b_id = cur.lastrowid

    conn.commit()
    conn.close()

    # Org A MLRO tries to resolve Org B's freeze obligation
    r = client.post(f"/freeze-obligations/{freeze_b_id}/resolve",
                    data={
                        "csrf_token": _csrf(client),
                        "resolution_reason": "delisted",
                        "notes": "Malicious cross-org resolution",
                    },
                    follow_redirects=True)

    # Should get error response
    assert r.status_code == 200
    assert ("not found" in r.text.lower() or "err=" in str(r.url).lower())

    # CRITICAL: Verify the freeze obligation was NOT resolved
    conn = _db()
    row = conn.execute("""
        SELECT status, resolved_at, resolved_by
        FROM freeze_obligations WHERE id=?
    """, (freeze_b_id,)).fetchone()
    conn.close()

    assert row["status"] == "executed_pending_report"  # Status unchanged
    assert row["resolved_at"] is None  # Not resolved
    assert row["resolved_by"] is None  # No resolver recorded


def _seed_freeze(reference: str, authority_ref: str) -> int:
    from amlkit.db import utcnow

    conn = _db()
    org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
    now = utcnow()
    cur = conn.execute("""
        INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
                               status, onboarded_at, created_at, updated_at)
        VALUES (?, ?, 'Blank Page Check', 'natural', ?, 'active', ?, ?, ?)
    """, (org_id, reference, reference.lower(), now, now, now))
    cur = conn.execute("""
        INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
                                        status, identified_at, identified_by, authority_ref)
        VALUES (?, ?, 'sanctions', 'critical', 'pending_execution', ?, 'alice', ?)
    """, (org_id, cur.lastrowid, now, authority_ref))
    freeze_id = cur.lastrowid
    conn.commit()
    conn.close()
    return freeze_id


def test_freeze_button_on_dashboard_for_mlro_only(client):
    _seed_freeze("C-FREEZE-BTN", "UN-BTN-1")

    dash = client.get("/dashboard").text
    head = dash.split('class="page-head page-head--with-actions"', 1)[1].split('<div class="dashboard-hero">', 1)[0]
    assert 'href="/freeze-obligations" class="btn-outline"' in head
    assert '<span class="visually-hidden">, 1 pending execution</span>' in head

    # Gone from the sidebar.
    nav = dash.split('<nav aria-label="Main navigation">', 1)[1].split("</nav>", 1)[0]
    assert "/freeze-obligations" not in nav

    _add_operator(client, "dora", "dora@testfirm.ae", role="officer")
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    officer = TestClient(app)
    officer.get("/login")
    _login(officer, "dora@testfirm.ae", "a-strong-password-2")
    officer_dash = officer.get("/dashboard").text
    assert 'class="btn-outline"' not in officer_dash


def _page_form(html: str, action: str) -> dict:
    """The hidden and default fields of the form posting to `action`."""
    import re
    m = re.search(r'<form method="post" action="' + re.escape(action) + r'"[^>]*>(.*?)</form>', html, re.S)
    assert m, f"no POST form for {action}"
    return dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', m.group(1)))


def _status(freeze_id: int) -> str:
    conn = _db()
    try:
        return conn.execute("SELECT status FROM freeze_obligations WHERE id = ?", (freeze_id,)).fetchone()["status"]
    finally:
        conn.close()


def test_freeze_detail_actions_are_post_forms_that_work(client):
    """The detail page's actions were <a href> links to POST-only routes (405).
    Walk the lifecycle using the forms the page actually renders."""
    freeze_id = _seed_freeze("C-FREEZE-FLOW", "UN-FLOW-1")
    base = f"/freeze-obligations/{freeze_id}"

    page = client.get(base).text
    assert f'href="{base}/execute"' not in page
    fields = _page_form(page, f"{base}/execute")
    assert fields.get("csrf_token"), "execute form must carry the CSRF token"
    r = client.post(f"{base}/execute", data={
        **fields, "asset_type_1": "bank_account", "asset_identifier_1": "AE07 0331 2345 6789",
        "asset_amount_1": "50000", "notes": "frozen",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert _status(freeze_id) == "executed_pending_report"

    page = client.get(base).text
    assert f'action="{base}/execute"' not in page
    assert _page_form(page, f"{base}/file-ffr").get("csrf_token")
    fields = _page_form(page, f"{base}/resolve")
    r = client.post(f"{base}/resolve", data={
        **fields, "resolution_reason": "authority_clearance", "authority_ref": "EOCN-1",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert _status(freeze_id) == "resolved"


def test_freeze_detail_hides_action_forms_from_officers(client):
    freeze_id = _seed_freeze("C-FREEZE-OFF", "UN-OFF-1")
    _add_operator(client, "erin", "erin@testfirm.ae", role="officer")
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    officer = TestClient(app)
    officer.get("/login")
    _login(officer, "erin@testfirm.ae", "a-strong-password-2")
    page = officer.get(f"/freeze-obligations/{freeze_id}").text
    assert f"<h1>Freeze Obligation #{freeze_id}</h1>" in page
    assert 'class="freeze-action"' not in page

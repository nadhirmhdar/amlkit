"""Tests for TFS freeze obligation tracking.

Cabinet Resolution 134 of 2025 places personal liability on senior management
for TFS compliance failures. These tests verify freeze-and-report workflows are
correctly tracked with full audit trail.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from amlkit import db


def test_freeze_obligations_table_exists():
    """Verify freeze_obligations table created by schema."""
    conn = db.connect(":memory:")

    # Check table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='freeze_obligations'"
    )
    assert cursor.fetchone() is not None

    # Check required columns exist
    cursor = conn.execute("PRAGMA table_info(freeze_obligations)")
    columns = {row[1] for row in cursor.fetchall()}

    required_columns = {
        "id", "org_id", "customer_id", "alert_id",
        "obligation_type", "risk_category",
        "identified_at", "identified_by",
        "executed_at", "executed_by",
        "reported_at", "report_id",
        "resolved_at", "resolved_by", "resolution_reason",
        "assets_frozen", "authority_ref", "notes", "status"
    }

    assert required_columns.issubset(columns), f"Missing columns: {required_columns - columns}"

    conn.close()


def test_freeze_obligations_indexes():
    """Verify indexes exist for query performance."""
    conn = db.connect(":memory:")

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='freeze_obligations'"
    )
    indexes = {row[0] for row in cursor.fetchall()}

    # Check expected indexes
    expected = {"ix_freeze_org", "ix_freeze_customer", "ix_freeze_status"}
    assert expected.issubset(indexes), f"Missing indexes: {expected - indexes}"

    conn.close()


def test_freeze_obligations_foreign_keys():
    """Verify FK constraints are properly defined."""
    conn = db.connect(":memory:")

    # Insert test org and customer
    conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES (?, ?, ?)",
        ("Test Org", "test", db.utcnow())
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    now = db.utcnow()
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type,
           canonical_key, onboarded_at, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, "C-2026-001", "Test Customer", "natural", "test_customer", now, "active", now, now)
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Insert freeze obligation
    conn.execute(
        """INSERT INTO freeze_obligations
           (org_id, customer_id, obligation_type, risk_category,
            identified_at, identified_by, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (org_id, customer_id, "sanctions", "high", db.utcnow(), "test_mlro", "pending_execution")
    )

    # Verify it was inserted
    cursor = conn.execute("SELECT COUNT(*) FROM freeze_obligations")
    assert cursor.fetchone()[0] == 1

    # Verify ON DELETE CASCADE for org_id
    conn.execute("DELETE FROM organizations WHERE id = ?", (org_id,))
    cursor = conn.execute("SELECT COUNT(*) FROM freeze_obligations")
    assert cursor.fetchone()[0] == 0, "freeze_obligation should cascade delete with org"

    conn.close()


def test_freeze_obligations_alert_id_null_on_delete():
    """Verify alert_id becomes NULL when source alert is deleted."""
    conn = db.connect(":memory:")

    # Setup org and customer
    conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES (?, ?, ?)",
        ("Test Org", "test", db.utcnow())
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    now = db.utcnow()
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type,
           canonical_key, onboarded_at, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, "C-2026-001", "Test Customer", "natural", "test_customer", now, "active", now, now)
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create a minimal entity for the alert
    conn.execute(
        "INSERT INTO datasets (key, title, is_mandatory, entity_count) VALUES (?, ?, ?, ?)",
        ("test_dataset", "Test Dataset", 1, 1)
    )
    dataset_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)""",
        (dataset_id, "test-1", "Person", "Test Entity", now, now)
    )
    entity_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create screening
    conn.execute(
        """INSERT INTO screenings (org_id, customer_id, query_name, trigger,
           algorithm, threshold, run_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (org_id, customer_id, "Test Customer", "onboarding", "jaro_winkler", 0.8, now)
    )
    screening_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create alert
    conn.execute(
        """INSERT INTO alerts (org_id, screening_id, entity_id, score,
           score_detail, matched_name, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, screening_id, entity_id, 95.0, "{}", "Sanctioned Entity", "open", now)
    )
    alert_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Insert freeze obligation linked to alert
    conn.execute(
        """INSERT INTO freeze_obligations
           (org_id, customer_id, alert_id, obligation_type, risk_category,
            identified_at, identified_by, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, customer_id, alert_id, "proliferation", "critical", now, "test_mlro", "pending_execution")
    )

    # Delete alert
    conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))

    # Verify alert_id is now NULL but freeze obligation remains
    cursor = conn.execute("SELECT alert_id FROM freeze_obligations")
    row = cursor.fetchone()
    assert row is not None, "freeze_obligation should still exist"
    assert row[0] is None, "alert_id should be NULL after alert deletion"

    conn.close()


def test_create_freeze_obligation_success():
    """Create freeze obligation with all required fields."""
    from amlkit.cases import manager

    conn = db.connect(":memory:")

    # Setup org and customer
    conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES (?, ?, ?)",
        ("Test Org", "test", db.utcnow())
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    now = db.utcnow()
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type,
           canonical_key, onboarded_at, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, "C-2026-001", "Test Customer", "natural", "test_customer", now, "active", now, now)
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create freeze obligation
    freeze_id = manager.create_freeze_obligation(
        conn,
        org_id,
        customer_id,
        obligation_type="sanctions",
        risk_category="high",
        identified_by="test_mlro",
        notes="Test freeze obligation"
    )

    assert freeze_id > 0

    # Verify it was created
    cursor = conn.execute(
        "SELECT * FROM freeze_obligations WHERE id = ?",
        (freeze_id,)
    )
    row = dict(cursor.fetchone())

    assert row["org_id"] == org_id
    assert row["customer_id"] == customer_id
    assert row["obligation_type"] == "sanctions"
    assert row["risk_category"] == "high"
    assert row["identified_by"] == "test_mlro"
    assert row["notes"] == "Test freeze obligation"
    assert row["status"] == "pending_execution"
    assert row["identified_at"] is not None
    assert row["executed_at"] is None
    assert row["reported_at"] is None
    assert row["resolved_at"] is None

    # Verify audit entry
    cursor = conn.execute(
        "SELECT * FROM audit_log WHERE action = ? AND org_id = ?",
        ("freeze.identified", org_id)
    )
    audit_row = cursor.fetchone()
    assert audit_row is not None

    conn.close()


def test_create_freeze_obligation_invalid_type():
    """Reject invalid obligation_type."""
    from amlkit.cases import manager

    conn = db.connect(":memory:")

    conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES (?, ?, ?)",
        ("Test Org", "test", db.utcnow())
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    now = db.utcnow()
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type,
           canonical_key, onboarded_at, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, "C-2026-001", "Test Customer", "natural", "test_customer", now, "active", now, now)
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    with pytest.raises(ValueError, match="obligation_type"):
        manager.create_freeze_obligation(
            conn,
            org_id,
            customer_id,
            obligation_type="invalid",
            risk_category="high",
            identified_by="test_mlro"
        )

    conn.close()


def test_execute_freeze_success():
    """Execute freeze obligation and update status."""
    from amlkit.cases import manager

    conn = db.connect(":memory:")

    # Setup
    conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES (?, ?, ?)",
        ("Test Org", "test", db.utcnow())
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    now = db.utcnow()
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type,
           canonical_key, onboarded_at, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, "C-2026-001", "Test Customer", "natural", "test_customer", now, "active", now, now)
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create freeze obligation
    freeze_id = manager.create_freeze_obligation(
        conn,
        org_id,
        customer_id,
        obligation_type="proliferation",
        risk_category="critical",
        identified_by="test_mlro"
    )

    # Execute freeze
    assets = [
        {"type": "bank_account", "identifier": "AE070331234567890123456", "amount_aed": 150000.50},
        {"type": "investment_account", "identifier": "INV-12345", "amount_aed": 500000.00}
    ]

    manager.execute_freeze(
        conn,
        freeze_id,
        org_id=org_id,
        executed_by="test_mlro",
        assets_frozen=assets,
        notes="Freeze executed per UNSCR 1718"
    )

    # Verify status updated
    cursor = conn.execute(
        "SELECT status, executed_at, executed_by, assets_frozen, notes FROM freeze_obligations WHERE id = ?",
        (freeze_id,)
    )
    row = dict(cursor.fetchone())

    assert row["status"] == "executed_pending_report"
    assert row["executed_at"] is not None
    assert row["executed_by"] == "test_mlro"
    assert row["notes"] == "Freeze executed per UNSCR 1718"

    # Verify assets stored as JSON
    stored_assets = json.loads(row["assets_frozen"])
    assert len(stored_assets) == 2
    assert stored_assets[0]["type"] == "bank_account"
    assert stored_assets[0]["amount_aed"] == 150000.50

    # Verify audit entry
    cursor = conn.execute(
        "SELECT * FROM audit_log WHERE action = ? AND org_id = ?",
        ("freeze.executed", org_id)
    )
    audit_row = cursor.fetchone()
    assert audit_row is not None

    conn.close()


def test_execute_freeze_already_executed():
    """Reject executing an already-executed freeze."""
    from amlkit.cases import manager

    conn = db.connect(":memory:")

    # Setup
    conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES (?, ?, ?)",
        ("Test Org", "test", db.utcnow())
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    now = db.utcnow()
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type,
           canonical_key, onboarded_at, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, "C-2026-001", "Test Customer", "natural", "test_customer", now, "active", now, now)
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    freeze_id = manager.create_freeze_obligation(
        conn, org_id, customer_id,
        obligation_type="sanctions",
        risk_category="high",
        identified_by="test_mlro"
    )

    # Execute once
    manager.execute_freeze(
        conn, freeze_id,
        org_id=org_id,
        executed_by="test_mlro",
        assets_frozen=[]
    )

    # Try to execute again - should fail
    with pytest.raises(ValueError, match="already executed"):
        manager.execute_freeze(
            conn, freeze_id,
        org_id=org_id,
            executed_by="test_mlro",
            assets_frozen=[]
        )

    conn.close()


def test_resolve_freeze_obligation_success():
    """Resolve freeze obligation with reason."""
    from amlkit.cases import manager

    conn = db.connect(":memory:")

    # Setup
    conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES (?, ?, ?)",
        ("Test Org", "test", db.utcnow())
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    now = db.utcnow()
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type,
           canonical_key, onboarded_at, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, "C-2026-001", "Test Customer", "natural", "test_customer", now, "active", now, now)
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    freeze_id = manager.create_freeze_obligation(
        conn, org_id, customer_id,
        obligation_type="sanctions",
        risk_category="high",
        identified_by="test_mlro"
    )

    manager.execute_freeze(
        conn, freeze_id,
        org_id=org_id,
        executed_by="test_mlro",
        assets_frozen=[]
    )

    # Resolve
    manager.resolve_freeze_obligation(
        conn,
        freeze_id,
        org_id=org_id,
        resolved_by="test_mlro",
        resolution_reason="delisted",
        authority_ref="FIU-2026-001",
        notes="Entity removed from OFAC list"
    )

    # Verify status
    cursor = conn.execute(
        "SELECT status, resolved_at, resolved_by, resolution_reason, authority_ref, notes FROM freeze_obligations WHERE id = ?",
        (freeze_id,)
    )
    row = dict(cursor.fetchone())

    assert row["status"] == "resolved"
    assert row["resolved_at"] is not None
    assert row["resolved_by"] == "test_mlro"
    assert row["resolution_reason"] == "delisted"
    assert row["authority_ref"] == "FIU-2026-001"
    assert row["notes"] == "Entity removed from OFAC list"

    # Verify audit entry
    cursor = conn.execute(
        "SELECT * FROM audit_log WHERE action = ? AND org_id = ?",
        ("freeze.resolved", org_id)
    )
    audit_row = cursor.fetchone()
    assert audit_row is not None

    conn.close()


def test_resolve_false_positive_before_execution():
    """Allow resolving as false_positive without execution."""
    from amlkit.cases import manager

    conn = db.connect(":memory:")

    # Setup
    conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES (?, ?, ?)",
        ("Test Org", "test", db.utcnow())
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    now = db.utcnow()
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type,
           canonical_key, onboarded_at, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, "C-2026-001", "Test Customer", "natural", "test_customer", now, "active", now, now)
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    freeze_id = manager.create_freeze_obligation(
        conn, org_id, customer_id,
        obligation_type="sanctions",
        risk_category="high",
        identified_by="test_mlro"
    )

    # Resolve as false positive WITHOUT executing
    manager.resolve_freeze_obligation(
        conn,
        freeze_id,
        org_id=org_id,
        resolved_by="test_mlro",
        resolution_reason="false_positive",
        notes="Name match error - different person"
    )

    # Verify it was resolved
    cursor = conn.execute(
        "SELECT status, executed_at FROM freeze_obligations WHERE id = ?",
        (freeze_id,)
    )
    row = dict(cursor.fetchone())

    assert row["status"] == "resolved"
    assert row["executed_at"] is None  # Never executed

    conn.close()


def test_send_freeze_obligation_alert():
    """Verify freeze obligation alert email can be sent."""
    from amlkit import mail

    # Test with no SMTP configured (should print to console)
    result = mail.send_freeze_obligation_alert(
        to_email="mlro@test.com",
        freeze_obligation_id=1,
        customer_reference="C-2026-001",
        obligation_type="proliferation",
        risk_category="critical"
    )

    # Should return NOT_CONFIGURED since SMTP is not set up in test
    assert result == mail.NOT_CONFIGURED


def test_check_unexecuted_freeze_obligations_finds_overdue():
    """Find freeze obligations pending execution for > 24 hours."""
    from amlkit.cases import manager
    from datetime import timedelta

    conn = db.connect(":memory:")

    # Setup org and customer
    conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES (?, ?, ?)",
        ("Test Org", "test", db.utcnow())
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    now = db.utcnow()
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type,
           canonical_key, onboarded_at, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, "C-2026-001", "Test Customer", "natural", "test_customer", now, "active", now, now)
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create a freeze obligation from 36 hours ago (overdue)
    from datetime import datetime, timezone
    overdue_time = (datetime.now(timezone.utc) - timedelta(hours=36)).isoformat()

    conn.execute(
        """INSERT INTO freeze_obligations
           (org_id, customer_id, obligation_type, risk_category,
            identified_at, identified_by, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (org_id, customer_id, "proliferation", "critical",
         overdue_time, "test_mlro", "pending_execution")
    )

    # Create a recent one (not overdue - 1 hour old)
    recent_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn.execute(
        """INSERT INTO freeze_obligations
           (org_id, customer_id, obligation_type, risk_category,
            identified_at, identified_by, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (org_id, customer_id, "sanctions", "high",
         recent_time, "test_mlro", "pending_execution")
    )

    # Create an executed one (should not be included)
    conn.execute(
        """INSERT INTO freeze_obligations
           (org_id, customer_id, obligation_type, risk_category,
            identified_at, identified_by, status, executed_at, executed_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, customer_id, "sanctions", "high",
         overdue_time, "test_mlro", "executed_pending_report", now, "test_mlro")
    )

    conn.commit()

    # Check for overdue obligations
    overdue = manager.check_unexecuted_freeze_obligations(conn, org_id)

    # Should find only the 36-hour-old pending obligation
    assert len(overdue) == 1
    assert overdue[0]["customer_reference"] == "C-2026-001"
    assert overdue[0]["obligation_type"] == "proliferation"
    assert overdue[0]["hours_pending"] > 24

    conn.close()


def test_check_unexecuted_freeze_obligations_empty():
    """Return empty list when no overdue obligations."""
    from amlkit.cases import manager

    conn = db.connect(":memory:")

    conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES (?, ?, ?)",
        ("Test Org", "test", db.utcnow())
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # No freeze obligations at all
    overdue = manager.check_unexecuted_freeze_obligations(conn, org_id)
    assert overdue == []

    conn.close()


def test_auto_create_freeze_on_pf_alert_confirmed():
    """Auto-create freeze obligation when PF alert confirmed."""
    from amlkit.cases import review
    from amlkit.screening.pf import PF_PROGRAM_PREFIXES

    conn = db.connect(":memory:")

    # Setup org and customer
    conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES (?, ?, ?)",
        ("Test Org", "test", db.utcnow())
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    now = db.utcnow()
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type,
           canonical_key, onboarded_at, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, "C-2026-001", "Test Customer", "natural", "test_customer", now, "active", now, now)
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create entity with PF program
    conn.execute(
        "INSERT INTO datasets (key, title, is_mandatory, entity_count) VALUES (?, ?, ?, ?)",
        ("test_dataset", "Test Dataset", 1, 1)
    )
    dataset_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           programs, topics, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (dataset_id, "test-1", "Person", "Test PF Entity",
         json.dumps([PF_PROGRAM_PREFIXES[0]]),  # UNSCR 1718 (DPRK)
         json.dumps(["sanction"]), now, now)
    )
    entity_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create screening and alert
    conn.execute(
        """INSERT INTO screenings (org_id, customer_id, query_name, trigger,
           algorithm, threshold, run_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (org_id, customer_id, "Test Customer", "onboarding", "jaro_winkler", 0.8, now)
    )
    screening_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        """INSERT INTO alerts (org_id, screening_id, entity_id, score,
           score_detail, matched_name, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, screening_id, entity_id, 95.0, "{}", "Test PF Entity", "open", now)
    )
    alert_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()

    # Disposition as true_positive
    review.propose_disposition(
        conn,
        alert_id,
        org_id=org_id,
        status="true_positive",
        reason_code="confirmed_match",
        operator="test_mlro",
        narrative="Confirmed DPRK proliferation entity"
    )

    # Verify freeze obligation was created
    cursor = conn.execute(
        """SELECT * FROM freeze_obligations
           WHERE org_id = ? AND customer_id = ? AND alert_id = ?""",
        (org_id, customer_id, alert_id)
    )
    freeze = cursor.fetchone()

    assert freeze is not None, "Freeze obligation should be auto-created for confirmed PF alert"
    assert freeze["obligation_type"] == "proliferation"
    assert freeze["status"] == "pending_execution"
    assert freeze["identified_by"] == "test_mlro"

    conn.close()


def test_auto_create_freeze_on_sanctions_alert_confirmed():
    """Auto-create freeze obligation when sanctions alert confirmed."""
    from amlkit.cases import review

    conn = db.connect(":memory:")

    # Setup org and customer
    conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES (?, ?, ?)",
        ("Test Org", "test", db.utcnow())
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    now = db.utcnow()
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type,
           canonical_key, onboarded_at, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, "C-2026-001", "Test Customer", "natural", "test_customer", now, "active", now, now)
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create entity with sanctions topic (but no PF program)
    conn.execute(
        "INSERT INTO datasets (key, title, is_mandatory, entity_count) VALUES (?, ?, ?, ?)",
        ("test_dataset", "Test Dataset", 1, 1)
    )
    dataset_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           programs, topics, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (dataset_id, "test-1", "Person", "Test Sanctions Entity",
         json.dumps([]),  # No PF programs
         json.dumps(["sanction"]), now, now)
    )
    entity_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create screening and alert
    conn.execute(
        """INSERT INTO screenings (org_id, customer_id, query_name, trigger,
           algorithm, threshold, run_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (org_id, customer_id, "Test Customer", "onboarding", "jaro_winkler", 0.8, now)
    )
    screening_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        """INSERT INTO alerts (org_id, screening_id, entity_id, score,
           score_detail, matched_name, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, screening_id, entity_id, 95.0, "{}", "Test Sanctions Entity", "open", now)
    )
    alert_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()

    # Disposition as true_positive
    review.propose_disposition(
        conn,
        alert_id,
        org_id=org_id,
        status="true_positive",
        reason_code="confirmed_match",
        operator="test_mlro",
        narrative="Confirmed sanctions match"
    )

    # Verify freeze obligation was created
    cursor = conn.execute(
        """SELECT * FROM freeze_obligations
           WHERE org_id = ? AND customer_id = ? AND alert_id = ?""",
        (org_id, customer_id, alert_id)
    )
    freeze = cursor.fetchone()

    assert freeze is not None, "Freeze obligation should be auto-created for confirmed sanctions alert"
    assert freeze["obligation_type"] == "sanctions"
    assert freeze["status"] == "pending_execution"

    conn.close()


def test_no_freeze_on_false_positive():
    """Do NOT create freeze obligation when alert is false positive."""
    from amlkit.cases import review

    conn = db.connect(":memory:")

    # Setup org and customer
    conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES (?, ?, ?)",
        ("Test Org", "test", db.utcnow())
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    now = db.utcnow()
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type,
           canonical_key, onboarded_at, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, "C-2026-001", "Test Customer", "natural", "test_customer", now, "active", now, now)
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create entity with sanctions
    conn.execute(
        "INSERT INTO datasets (key, title, is_mandatory, entity_count) VALUES (?, ?, ?, ?)",
        ("test_dataset", "Test Dataset", 1, 1)
    )
    dataset_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           programs, topics, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (dataset_id, "test-1", "Person", "Test Entity",
         json.dumps([]), json.dumps(["sanction"]), now, now)
    )
    entity_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create screening and alert
    conn.execute(
        """INSERT INTO screenings (org_id, customer_id, query_name, trigger,
           algorithm, threshold, run_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (org_id, customer_id, "Test Customer", "onboarding", "jaro_winkler", 0.8, now)
    )
    screening_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        """INSERT INTO alerts (org_id, screening_id, entity_id, score,
           score_detail, matched_name, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, screening_id, entity_id, 95.0, "{}", "Test Entity", "open", now)
    )
    alert_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()

    # Set single operator mode to avoid four-eyes review
    import os
    os.environ["AMLKIT_SINGLE_OPERATOR_MODE"] = "1"

    try:
        # Disposition as false_positive
        review.propose_disposition(
            conn,
            alert_id,
            org_id=org_id,
            status="false_positive",
            reason_code="name_coincidence",
            operator="test_mlro",
            narrative="Name similarity only - different person"
        )

        # Verify NO freeze obligation was created
        cursor = conn.execute(
            "SELECT COUNT(*) FROM freeze_obligations WHERE org_id = ? AND customer_id = ?",
            (org_id, customer_id)
        )
        count = cursor.fetchone()[0]
        assert count == 0, "No freeze obligation should be created for false positive"

    finally:
        del os.environ["AMLKIT_SINGLE_OPERATOR_MODE"]

    conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_cross_org_execute_freeze_blocked():
    """Org A cannot execute org B's freeze obligation (tenant isolation)."""
    from amlkit.cases import manager

    conn = db.connect(":memory:")

    # Create org A and B
    now = db.utcnow()
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?, ?, ?, ?)",
        ("Org A", "org-a", "active", now)
    )
    org_a = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?, ?, ?, ?)",
        ("Org B", "org-b", "active", now)
    )
    org_b = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create customer in org B
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
           onboarded_at, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_b, "C-B-001", "Org B Customer", "natural", "test", now, "active", now, now)
    )
    customer_b = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create freeze obligation in org B
    freeze_id = manager.create_freeze_obligation(
        conn, org_b, customer_b,
        obligation_type="sanctions",
        risk_category="high",
        identified_by="mlro_b"
    )

    # Org A operator tries to execute org B's freeze
    with pytest.raises(ValueError, match="not found in org"):
        manager.execute_freeze(
            conn, freeze_id,
            org_id=org_a,
            executed_by="mlro_a",
            assets_frozen=[]
        )

    # Verify org B's freeze unchanged
    row = conn.execute(
        "SELECT status, executed_at FROM freeze_obligations WHERE id = ?",
        (freeze_id,)
    ).fetchone()
    assert row["status"] == "pending_execution"
    assert row["executed_at"] is None

    # Verify no audit entry from org A
    audit = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE org_id = ? AND action = 'freeze.executed'",
        (org_a,)
    ).fetchone()[0]
    assert audit == 0

    conn.close()


def test_cross_org_resolve_freeze_blocked():
    """Org A cannot resolve org B's freeze obligation (tenant isolation)."""
    from amlkit.cases import manager

    conn = db.connect(":memory:")

    # Create org A and B
    now = db.utcnow()
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?, ?, ?, ?)",
        ("Org A", "org-a", "active", now)
    )
    org_a = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?, ?, ?, ?)",
        ("Org B", "org-b", "active", now)
    )
    org_b = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create customer in org B
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
           onboarded_at, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_b, "C-B-001", "Org B Customer", "natural", "test", now, "active", now, now)
    )
    customer_b = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create and execute freeze in org B
    freeze_id = manager.create_freeze_obligation(
        conn, org_b, customer_b,
        obligation_type="sanctions",
        risk_category="high",
        identified_by="mlro_b"
    )
    manager.execute_freeze(
        conn, freeze_id,
        org_id=org_b,
        executed_by="mlro_b",
        assets_frozen=[]
    )

    # Org A operator tries to resolve org B's freeze
    with pytest.raises(ValueError, match="not found in org"):
        manager.resolve_freeze_obligation(
            conn, freeze_id,
            org_id=org_a,
            resolved_by="mlro_a",
            resolution_reason="delisted"
        )

    # Verify org B's freeze unchanged
    row = conn.execute(
        "SELECT status, resolved_at FROM freeze_obligations WHERE id = ?",
        (freeze_id,)
    ).fetchone()
    assert row["status"] == "executed_pending_report"
    assert row["resolved_at"] is None

    # Verify no audit entry from org A
    audit = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE org_id = ? AND action = 'freeze.resolved'",
        (org_a,)
    ).fetchone()[0]
    assert audit == 0

    conn.close()


def test_check_unexecuted_freeze_obligations_sends_email():
    """check_unexecuted_freeze_obligations calls mailer for overdue obligations."""
    from amlkit.cases import manager
    from datetime import timedelta, datetime, timezone
    from unittest.mock import patch

    conn = db.connect(":memory:")

    # Setup org and MLRO
    now = db.utcnow()
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?, ?, ?, ?)",
        ("Test Org", "test", "active", now)
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active, failed_login_count, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, "MLRO", "mlro@test.com", "hash", "mlro", 1, 0, now)
    )

    # Create customer
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
           onboarded_at, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, "C-001", "Test Customer", "natural", "test", now, "active", now, now)
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Create overdue freeze obligation (36 hours old)
    overdue_time = (datetime.now(timezone.utc) - timedelta(hours=36)).isoformat()
    conn.execute(
        """INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
           identified_at, identified_by, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (org_id, customer_id, "proliferation", "critical", overdue_time, "mlro", "pending_execution")
    )
    freeze_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()

    # Mock the mailer
    with patch('amlkit.mail.send_freeze_obligation_alert') as mock_mailer:
        mock_mailer.return_value = "SENT"

        overdue = manager.check_unexecuted_freeze_obligations(conn, org_id)

        # Verify mailer was called
        assert mock_mailer.called, "Mailer should be called for overdue obligations"
        mock_mailer.assert_called_once_with(
            to_email="mlro@test.com",
            freeze_obligation_id=freeze_id,
            customer_reference="C-001",
            obligation_type="proliferation",
            risk_category="critical"
        )

    assert len(overdue) == 1
    conn.close()

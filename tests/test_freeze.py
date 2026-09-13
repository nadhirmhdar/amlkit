"""Tests for TFS freeze obligation tracking.

Cabinet Resolution 134 of 2025 places personal liability on senior management
for TFS compliance failures. These tests verify freeze-and-report workflows are
correctly tracked with full audit trail.
"""

from __future__ import annotations

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

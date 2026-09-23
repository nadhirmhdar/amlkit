"""P0: Test AMLKIT_PURGE_ENABLED gate for retention purge.

Gate purge_expired behind env flag. When unset: no-op, log warning, audit entry.
When set to 'true': purge runs normally.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit import db
from amlkit.cases import manager
from amlkit.names.arabic import canonical_key


def _create_customer(conn, org_id: int, cust_id: int, reference: str, retention_until: str):
    """Helper to create a customer with required fields."""
    full_name = "Test Customer"
    conn.execute(
        "INSERT INTO customers (id, org_id, reference, full_name, canonical_key, "
        "customer_type, status, retention_until, onboarded_at, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'natural', 'closed', ?, '2020-01-01', '2020-01-01', '2020-01-01')",
        (cust_id, org_id, reference, full_name, canonical_key(full_name), retention_until)
    )


def test_purge_disabled_when_flag_unset(monkeypatch, tmp_path):
    """P0: purge_expired is no-op when AMLKIT_PURGE_ENABLED is unset."""
    # Ensure flag is NOT set
    monkeypatch.delenv("AMLKIT_PURGE_ENABLED", raising=False)

    conn = db.connect(tmp_path / "test.db")
    try:
        # Create org and expired customer
        conn.execute(
            "INSERT INTO organizations (id, name, slug, status, created_at) "
            "VALUES (1, 'Test Org', 'test', 'active', '2024-01-01')"
        )
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _create_customer(conn, org_id=1, cust_id=1, reference="C-001", retention_until=yesterday)
        conn.commit()

        # Purge should be no-op
        result = manager.purge_expired(conn, org_id=1, actor="test")

        assert result["purged"] == 0, "Should not purge when flag unset"
        assert result.get("disabled") is True, "Should indicate purge is disabled"
        assert result["details"] == [], "Should return empty details"

        # Customer should still exist
        customer = conn.execute(
            "SELECT * FROM customers WHERE id=1 AND org_id=1"
        ).fetchone()
        assert customer is not None, "Customer should NOT be deleted when flag unset"

        # Audit entry should exist
        audit_entry = conn.execute(
            "SELECT * FROM audit_log WHERE action='retention.purge_disabled' AND org_id=1"
        ).fetchone()
        assert audit_entry is not None, "Audit entry should record purge was disabled"
        assert "AMLKIT_PURGE_ENABLED not set" in audit_entry["detail"]

    finally:
        conn.close()


def test_purge_enabled_when_flag_set_true(monkeypatch, tmp_path):
    """P0: purge_expired runs normally when AMLKIT_PURGE_ENABLED='true'."""
    # Set flag to 'true'
    monkeypatch.setenv("AMLKIT_PURGE_ENABLED", "true")

    conn = db.connect(tmp_path / "test.db")
    try:
        # Create org and expired customer
        conn.execute(
            "INSERT INTO organizations (id, name, slug, status, created_at) "
            "VALUES (1, 'Test Org', 'test', 'active', '2024-01-01')"
        )
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _create_customer(conn, org_id=1, cust_id=1, reference="C-001", retention_until=yesterday)
        conn.commit()

        # Purge should run
        result = manager.purge_expired(conn, org_id=1, actor="test")

        assert result["purged"] == 1, "Should purge when flag set to 'true'"
        assert result.get("disabled") is not True, "Should NOT be disabled"
        assert len(result["details"]) == 1, "Should return purged customer details"

        # Customer should be deleted
        customer = conn.execute(
            "SELECT * FROM customers WHERE id=1 AND org_id=1"
        ).fetchone()
        assert customer is None, "Customer SHOULD be deleted when flag='true'"

        # Normal purge audit entry should exist
        audit_entry = conn.execute(
            "SELECT * FROM audit_log WHERE action='customer.purge' AND org_id=1"
        ).fetchone()
        assert audit_entry is not None, "Normal purge audit entry should exist"

        # NO disabled audit entry
        disabled_entry = conn.execute(
            "SELECT * FROM audit_log WHERE action='retention.purge_disabled'"
        ).fetchone()
        assert disabled_entry is None, "Should NOT have disabled audit entry when enabled"

    finally:
        conn.close()


def test_purge_disabled_when_flag_set_to_other_values(monkeypatch, tmp_path):
    """P0: purge_expired is no-op when AMLKIT_PURGE_ENABLED is set but not 'true'."""
    # Set flag to something other than 'true'
    for value in ["false", "True", "1", "yes", ""]:
        monkeypatch.setenv("AMLKIT_PURGE_ENABLED", value)

        conn = db.connect(tmp_path / f"test_{value}.db")
        try:
            # Create org and expired customer
            conn.execute(
                "INSERT INTO organizations (id, name, slug, status, created_at) "
                "VALUES (1, 'Test Org', 'test', 'active', '2024-01-01')"
            )
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            _create_customer(conn, org_id=1, cust_id=1, reference="C-001", retention_until=yesterday)
            conn.commit()

            # Purge should be no-op
            result = manager.purge_expired(conn, org_id=1, actor="test")

            assert result["purged"] == 0, \
                f"Should not purge when flag='{value}' (only 'true' enables)"
            assert result.get("disabled") is True, \
                f"Should be disabled when flag='{value}'"

            # Customer should still exist
            customer = conn.execute(
                "SELECT * FROM customers WHERE id=1 AND org_id=1"
            ).fetchone()
            assert customer is not None, \
                f"Customer should NOT be deleted when flag='{value}'"

        finally:
            conn.close()


def test_purge_dry_run_respects_flag(monkeypatch, tmp_path):
    """P0: purge_expired dry_run also respects flag."""
    # Flag unset
    monkeypatch.delenv("AMLKIT_PURGE_ENABLED", raising=False)

    conn = db.connect(tmp_path / "test.db")
    try:
        # Create org and expired customer
        conn.execute(
            "INSERT INTO organizations (id, name, slug, status, created_at) "
            "VALUES (1, 'Test Org', 'test', 'active', '2024-01-01')"
        )
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _create_customer(conn, org_id=1, cust_id=1, reference="C-001", retention_until=yesterday)
        conn.commit()

        # Dry run should also be gated
        result = manager.purge_expired(conn, org_id=1, actor="test", dry_run=True)

        assert result["purged"] == 0, "Dry run should return 0 when flag unset"
        assert result.get("disabled") is True, "Dry run should show disabled"

        # Now enable and try again
        monkeypatch.setenv("AMLKIT_PURGE_ENABLED", "true")
        result = manager.purge_expired(conn, org_id=1, actor="test", dry_run=True)

        assert result["purged"] == 1, "Dry run should show would-purge count when enabled"
        assert result.get("dry_run") is True, "Should indicate dry run mode"
        assert result.get("disabled") is not True, "Should not be disabled when flag set"

        # Customer should still exist (dry run didn't delete)
        customer = conn.execute(
            "SELECT * FROM customers WHERE id=1 AND org_id=1"
        ).fetchone()
        assert customer is not None, "Dry run should not delete"

    finally:
        conn.close()

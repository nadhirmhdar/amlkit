"""Test structuring rule applies to ALL payment methods, not just cash.

Regression test for issue #257 (board p93): structuring rule was blind to
wire and virtual-asset transfers, only aggregating cash. This test verifies
that 4 sub-threshold wire transfers within the structuring window trigger
the structuring alert.

This test must FAIL before the fix and PASS after.
"""

import pytest
from amlkit.db import connect, utcnow, upsert_dataset
from amlkit.screening.kyt import evaluate_transaction, LARGE_CASH_THRESHOLD_AED
from amlkit.cases.manager import record_transaction, onboard
from datetime import datetime, timedelta, timezone


def test_structuring_triggers_for_wire_transfers():
    """Four sub-threshold wire transfers within structuring window must trigger alert."""
    conn = connect(":memory:")

    # Create fresh mandatory dataset so onboard() passes staleness guard
    ds = upsert_dataset(conn, "test_sanctions", "Test Sanctions List", is_mandatory=True)
    now = utcnow()
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    conn.commit()

    # Register org
    org_id = conn.execute(
        """INSERT INTO organizations (name, slug, status, created_at) VALUES (?, ?, ?, ?) RETURNING id""",
        ("Test Org", "test-org", "active", utcnow())
    ).fetchone()["id"]

    # Onboard customer
    result = onboard(conn, org_id=org_id, reference="CUST-001", full_name="John Doe")
    customer_id = result.customer_id
    conn.commit()

    # Record 4 wire transfers, each 20,000 AED (sub-threshold), all within 7 days
    base_time = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
    threshold = LARGE_CASH_THRESHOLD_AED  # 55,000 AED
    per_transfer = 20_000.0  # Sub-threshold

    for i in range(4):
        occurred_at = (base_time + timedelta(days=i)).isoformat()
        transaction_id, alerts = record_transaction(
            conn,
            org_id=org_id,
            customer_id=customer_id,
            direction="outbound",
            method="wire",  # Wire transfer, not cash
            amount=per_transfer,
            currency="AED",
            counterparty_name="Beneficiary Corp",
            counterparty_country="AE",
            occurred_at=occurred_at,
            actor="test-user",
        )

        # First 3 transfers should NOT trigger structuring (under total threshold yet)
        if i < 3:
            # No structuring alert yet
            pass
        else:
            # 4th transfer: total = 80,000 AED (exceeds 55,000 threshold)
            # Structuring rule should fire
            assert len(alerts) > 0, f"Expected structuring alert on 4th wire transfer (total={4*per_transfer} AED > {threshold} AED)"

    # Verify the 4th transaction triggered structuring
    last_txn = conn.execute(
        """SELECT id FROM transactions WHERE customer_id=? ORDER BY occurred_at DESC LIMIT 1""",
        (customer_id,)
    ).fetchone()

    rules = evaluate_transaction(
        conn,
        org_id=org_id,
        customer_id=customer_id,
        transaction_id=last_txn["id"],
        method="wire",
        amount_aed=per_transfer,
        counterparty_country="AE",
        occurred_at=(base_time + timedelta(days=3)).isoformat(),
    )

    # Must have structuring alert
    structuring_alerts = [r for r in rules if r.rule_key == "structuring"]
    assert len(structuring_alerts) == 1, (
        f"Expected 1 structuring alert for wire transfers totaling "
        f"{4*per_transfer} AED (> {threshold} AED threshold), got {len(structuring_alerts)}"
    )

    alert = structuring_alerts[0]
    assert alert.severity == "high"
    assert alert.detail["transaction_count"] >= 4
    assert alert.detail["total_aed"] >= 4 * per_transfer


def test_structuring_still_works_for_cash():
    """Verify existing cash structuring behavior still works after fix."""
    conn = connect(":memory:")

    # Create fresh mandatory dataset so onboard() passes staleness guard
    ds = upsert_dataset(conn, "test_sanctions_2", "Test Sanctions List 2", is_mandatory=True)
    now = utcnow()
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    conn.commit()

    # Register org
    org_id = conn.execute(
        """INSERT INTO organizations (name, slug, status, created_at) VALUES (?, ?, ?, ?) RETURNING id""",
        ("Test Org 2", "test-org-2", "active", utcnow())
    ).fetchone()["id"]

    # Onboard customer
    result = onboard(conn, org_id=org_id, reference="CUST-002", full_name="Jane Smith")
    customer_id = result.customer_id
    conn.commit()

    # Record 3 cash transactions, each 25,000 AED (sub-threshold)
    base_time = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
    per_transfer = 25_000.0

    for i in range(3):
        occurred_at = (base_time + timedelta(days=i)).isoformat()
        transaction_id, alerts = record_transaction(
            conn,
            org_id=org_id,
            customer_id=customer_id,
            direction="inbound",
            method="cash",  # Cash transactions
            amount=per_transfer,
            currency="AED",
            counterparty_name="Walk-in Customer",
            counterparty_country="AE",
            occurred_at=occurred_at,
            actor="test-user",
        )

        if i == 2:
            # 3rd cash transaction: total = 75,000 AED (exceeds 55,000)
            assert len(alerts) > 0, "Expected structuring alert on 3rd cash transaction"

    # Verify existing cash structuring still works
    last_txn = conn.execute(
        """SELECT id FROM transactions WHERE customer_id=? ORDER BY occurred_at DESC LIMIT 1""",
        (customer_id,)
    ).fetchone()

    rules = evaluate_transaction(
        conn,
        org_id=org_id,
        customer_id=customer_id,
        transaction_id=last_txn["id"],
        method="cash",
        amount_aed=per_transfer,
        counterparty_country="AE",
        occurred_at=(base_time + timedelta(days=2)).isoformat(),
    )

    structuring_alerts = [r for r in rules if r.rule_key == "structuring"]
    assert len(structuring_alerts) == 1, "Cash structuring must still work"

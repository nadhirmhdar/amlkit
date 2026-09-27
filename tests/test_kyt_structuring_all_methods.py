"""Structuring: which channels aggregate, and one open alert per pattern.

Issue #257 asked for structuring beyond cash. Aggregating every method made
routine bank payments look like structuring: 20 daily AED 30,000 inbound
wires (rent, instalments) raised 19 high-severity alerts. Structuring now
aggregates only channels with no bank/card intermediary keeping its own record
(kyt.STRUCTURING_METHODS: cash, crypto, other), and a customer with an open
structuring alert is not re-alerted on every further transaction.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from amlkit.cases.manager import onboard, record_transaction
from amlkit.screening.kyt import STRUCTURING_METHODS

BASE = datetime(2026, 9, 1, 9, tzinfo=timezone.utc)


@pytest.fixture()
def customer_id(conn, org_id) -> int:
    return onboard(conn, org_id=org_id, reference="C-STR-1", full_name="Gulf Supplies Trading").customer_id


def _record(conn, org_id, cid, *, day, method, amount=30000.0, direction="inbound"):
    _, rules = record_transaction(
        conn, cid, org_id, direction=direction, method=method, amount=amount,
        occurred_at=(BASE + timedelta(days=day)).isoformat(), actor="tester",
    )
    return {r.rule_key for r in rules}


def _structuring_alerts(conn, cid) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM transaction_alerts WHERE customer_id=? AND rule_key='structuring'",
        (cid,),
    ).fetchone()[0]


@pytest.mark.parametrize("method", ["wire", "cheque", "card"])
def test_routine_bank_payments_never_structure(conn, org_id, customer_id, method):
    for day in range(20):
        _record(conn, org_id, customer_id, day=day, method=method)
    assert _structuring_alerts(conn, customer_id) == 0


def test_large_single_wire_still_flagged_as_large_value(conn, org_id, customer_id):
    keys = _record(conn, org_id, customer_id, day=0, method="wire", amount=60000.0)
    assert "large_value" in keys
    assert "structuring" not in keys


@pytest.mark.parametrize("method", sorted(STRUCTURING_METHODS))
def test_split_below_threshold_structures(conn, org_id, customer_id, method):
    assert "structuring" not in _record(conn, org_id, customer_id, day=0, method=method)
    assert "structuring" in _record(conn, org_id, customer_id, day=1, method=method)


def test_cash_split_with_crypto_combines(conn, org_id, customer_id):
    _record(conn, org_id, customer_id, day=0, method="cash")
    assert "structuring" in _record(conn, org_id, customer_id, day=1, method="crypto")


def test_wires_do_not_count_towards_a_cash_split(conn, org_id, customer_id):
    _record(conn, org_id, customer_id, day=0, method="wire")
    assert "structuring" not in _record(conn, org_id, customer_id, day=1, method="cash")


def test_opposite_directions_do_not_combine(conn, org_id, customer_id):
    _record(conn, org_id, customer_id, day=0, method="cash", direction="inbound")
    assert "structuring" not in _record(
        conn, org_id, customer_id, day=1, method="cash", direction="outbound"
    )


def test_one_open_alert_per_pattern(conn, org_id, customer_id):
    for day in range(6):
        _record(conn, org_id, customer_id, day=day, method="cash")
    assert _structuring_alerts(conn, customer_id) == 1


def test_new_alert_after_previous_one_is_dispositioned(conn, org_id, customer_id):
    _record(conn, org_id, customer_id, day=0, method="cash")
    _record(conn, org_id, customer_id, day=1, method="cash")
    assert _structuring_alerts(conn, customer_id) == 1
    conn.execute(
        "UPDATE transaction_alerts SET status='false_positive' WHERE customer_id=? AND rule_key='structuring'",
        (customer_id,),
    )
    conn.commit()
    assert "structuring" in _record(conn, org_id, customer_id, day=2, method="cash")
    assert _structuring_alerts(conn, customer_id) == 2

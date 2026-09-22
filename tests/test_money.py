"""Tests for amlkit/money.py — Google Money type (units + nanos)."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.money import Money


class TestMoneyConstruction:
    def test_basic_construction(self):
        m = Money("AED", 100, 0)
        assert m.currency_code == "AED"
        assert m.units == 100
        assert m.nanos == 0

    def test_with_nanos(self):
        m = Money("AED", 55000, 250_000_000)
        assert m.units == 55000
        assert m.nanos == 250_000_000

    def test_zero_amount(self):
        m = Money("AED", 0, 0)
        assert m.units == 0
        assert m.nanos == 0

    def test_negative_units_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            Money("AED", -1, 0)

    def test_negative_nanos_rejected(self):
        with pytest.raises(ValueError, match="nanos"):
            Money("AED", 0, -1)

    def test_nanos_too_large_rejected(self):
        with pytest.raises(ValueError, match="nanos"):
            Money("AED", 0, 1_000_000_000)

    def test_nanos_upper_bound_accepted(self):
        m = Money("AED", 0, 999_999_999)
        assert m.nanos == 999_999_999


class TestFromDecimal:
    def test_whole_amount(self):
        m = Money.from_decimal(Decimal("55000"), "AED")
        assert m.units == 55000
        assert m.nanos == 0
        assert m.currency_code == "AED"

    def test_fils_precision(self):
        m = Money.from_decimal(Decimal("55000.25"), "AED")
        assert m.units == 55000
        assert m.nanos == 250_000_000

    def test_sub_fils(self):
        m = Money.from_decimal(Decimal("100.123456789"), "AED")
        assert m.units == 100
        assert m.nanos == 123_456_789

    def test_zero(self):
        m = Money.from_decimal(Decimal("0"), "AED")
        assert m.units == 0
        assert m.nanos == 0

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            Money.from_decimal(Decimal("-1.50"), "AED")

    def test_large_amount(self):
        m = Money.from_decimal(Decimal("999999999.999999999"), "AED")
        assert m.units == 999_999_999
        assert m.nanos == 999_999_999

    def test_usd_currency(self):
        m = Money.from_decimal(Decimal("100.50"), "USD")
        assert m.currency_code == "USD"
        assert m.units == 100
        assert m.nanos == 500_000_000


class TestToDecimal:
    def test_whole_amount(self):
        m = Money("AED", 55000, 0)
        assert m.to_decimal() == Decimal("55000.000000000")

    def test_with_nanos(self):
        m = Money("AED", 55000, 250_000_000)
        assert m.to_decimal() == Decimal("55000.250000000")

    def test_round_trip(self):
        original = Decimal("12345.678901234")
        m = Money.from_decimal(original, "AED")
        result = m.to_decimal()
        assert result == Decimal("12345.678901234")

    def test_round_trip_fils(self):
        original = Decimal("0.25")
        m = Money.from_decimal(original, "AED")
        result = m.to_decimal()
        assert result == original

    def test_zero(self):
        m = Money("AED", 0, 0)
        assert m.to_decimal() == Decimal("0")


class TestAEDFormatting:
    def test_whole_amount(self):
        m = Money("AED", 55000, 0)
        assert m.to_aed_str() == "55,000.00"

    def test_with_fils(self):
        m = Money("AED", 55000, 250_000_000)
        assert m.to_aed_str() == "55,000.25"

    def test_zero(self):
        m = Money("AED", 0, 0)
        assert m.to_aed_str() == "0.00"

    def test_large_amount(self):
        m = Money("AED", 1_234_567, 890_000_000)
        assert m.to_aed_str() == "1,234,567.89"


class TestComparisons:
    def test_equal(self):
        a = Money("AED", 100, 500_000_000)
        b = Money("AED", 100, 500_000_000)
        assert a == b

    def test_not_equal(self):
        a = Money("AED", 100, 0)
        b = Money("AED", 100, 1)
        assert a != b

    def test_less_than_units(self):
        a = Money("AED", 99, 999_999_999)
        b = Money("AED", 100, 0)
        assert a < b

    def test_less_than_nanos(self):
        a = Money("AED", 100, 0)
        b = Money("AED", 100, 1)
        assert a < b

    def test_greater_equal(self):
        a = Money("AED", 55000, 0)
        b = Money("AED", 55000, 0)
        assert a >= b

    def test_greater_than(self):
        a = Money("AED", 55000, 1)
        b = Money("AED", 55000, 0)
        assert a > b

    def test_less_equal(self):
        a = Money("AED", 55000, 0)
        b = Money("AED", 55000, 0)
        assert a <= b


class TestAddition:
    def test_add_no_carry(self):
        a = Money("AED", 100, 250_000_000)
        b = Money("AED", 200, 500_000_000)
        result = a + b
        assert result.units == 300
        assert result.nanos == 750_000_000

    def test_add_with_carry(self):
        a = Money("AED", 100, 750_000_000)
        b = Money("AED", 200, 500_000_000)
        result = a + b
        assert result.units == 301
        assert result.nanos == 250_000_000

    def test_add_zero(self):
        a = Money("AED", 100, 0)
        b = Money("AED", 0, 0)
        result = a + b
        assert result == a

    def test_add_preserves_currency(self):
        a = Money("AED", 100, 0)
        b = Money("AED", 200, 0)
        result = a + b
        assert result.currency_code == "AED"

    def test_add_different_currencies_rejected(self):
        a = Money("AED", 100, 0)
        b = Money("USD", 200, 0)
        with pytest.raises(ValueError, match="currency"):
            a + b


class TestFromFloat:
    """Test conversion from float (for backward compat with amount_aed REAL)."""

    def test_from_float_whole(self):
        m = Money.from_float(55000.0, "AED")
        assert m.units == 55000
        assert m.nanos == 0

    def test_from_float_with_fils(self):
        m = Money.from_float(55000.25, "AED")
        assert m.units == 55000
        assert m.nanos == 250_000_000

    def test_from_float_rounding(self):
        m = Money.from_float(100.1, "AED")
        assert m.units == 100
        assert 99_000_000 <= m.nanos <= 101_000_000


class TestBackfillMigration:
    """Test that _backfill_money_columns correctly converts REAL amounts."""

    def test_backfill_whole_amount(self):
        from amlkit.db import connect
        conn = connect(":memory:")
        org_id = _create_test_org(conn)
        cust_id = _create_test_customer(conn, org_id)
        conn.execute(
            "INSERT INTO transactions (org_id, customer_id, direction, method, "
            "amount, currency, amount_aed, occurred_at, recorded_by, created_at) "
            "VALUES (?,?,'inbound','cash',55000,'AED',55000,'2026-01-01','sys','2026-01-01')",
            (org_id, cust_id),
        )
        conn.execute("UPDATE transactions SET amount_units=NULL, amount_nanos=NULL")
        conn.commit()
        from amlkit.db import _backfill_money_columns
        _backfill_money_columns(conn)
        conn.commit()
        row = conn.execute("SELECT amount_units, amount_nanos FROM transactions").fetchone()
        assert row["amount_units"] == 55000
        assert row["amount_nanos"] == 0

    def test_backfill_fils_precision(self):
        from amlkit.db import connect, _backfill_money_columns
        conn = connect(":memory:")
        org_id = _create_test_org(conn)
        cust_id = _create_test_customer(conn, org_id)
        conn.execute(
            "INSERT INTO transactions (org_id, customer_id, direction, method, "
            "amount, currency, amount_aed, occurred_at, recorded_by, created_at) "
            "VALUES (?,?,'inbound','wire',55000.25,'AED',55000.25,'2026-01-01','sys','2026-01-01')",
            (org_id, cust_id),
        )
        conn.execute("UPDATE transactions SET amount_units=NULL, amount_nanos=NULL")
        conn.commit()
        _backfill_money_columns(conn)
        conn.commit()
        row = conn.execute("SELECT amount_units, amount_nanos FROM transactions").fetchone()
        assert row["amount_units"] == 55000
        assert row["amount_nanos"] == 250_000_000

    def test_backfill_idempotent(self):
        from amlkit.db import connect, _backfill_money_columns
        conn = connect(":memory:")
        org_id = _create_test_org(conn)
        cust_id = _create_test_customer(conn, org_id)
        conn.execute(
            "INSERT INTO transactions (org_id, customer_id, direction, method, "
            "amount, currency, amount_aed, occurred_at, recorded_by, created_at) "
            "VALUES (?,?,'inbound','cash',1000,'AED',1000,'2026-01-01','sys','2026-01-01')",
            (org_id, cust_id),
        )
        conn.execute("UPDATE transactions SET amount_units=NULL, amount_nanos=NULL")
        conn.commit()
        _backfill_money_columns(conn)
        conn.commit()
        _backfill_money_columns(conn)
        conn.commit()
        row = conn.execute("SELECT amount_units, amount_nanos FROM transactions").fetchone()
        assert row["amount_units"] == 1000
        assert row["amount_nanos"] == 0

    def test_backfill_preserves_amount_aed(self):
        from amlkit.db import connect, _backfill_money_columns
        conn = connect(":memory:")
        org_id = _create_test_org(conn)
        cust_id = _create_test_customer(conn, org_id)
        conn.execute(
            "INSERT INTO transactions (org_id, customer_id, direction, method, "
            "amount, currency, amount_aed, occurred_at, recorded_by, created_at) "
            "VALUES (?,?,'inbound','cash',12345.67,'AED',12345.67,'2026-01-01','sys','2026-01-01')",
            (org_id, cust_id),
        )
        conn.execute("UPDATE transactions SET amount_units=NULL, amount_nanos=NULL")
        conn.commit()
        _backfill_money_columns(conn)
        conn.commit()
        row = conn.execute("SELECT amount_aed, amount_units, amount_nanos FROM transactions").fetchone()
        assert abs(row["amount_aed"] - 12345.67) < 0.001
        assert row["amount_units"] == 12345
        assert row["amount_nanos"] == 670_000_000


class TestKYTBoundary:
    """KYT threshold at exactly 55,000.00 behaves identically with Money."""

    def _setup_org_and_customer(self):
        from amlkit.db import connect, utcnow
        from amlkit.cases.manager import onboard
        conn = connect(":memory:")
        org_id = _create_test_org(conn)
        conn.execute(
            "INSERT INTO datasets (key, title, publisher, is_mandatory, "
            "last_refresh, entity_count, max_age_hours) "
            "VALUES ('test_list', 'Test', 'Test', 1, ?, 1, 24)",
            (utcnow(),),
        )
        conn.commit()
        result = onboard(
            conn, org_id=org_id, reference="KYT-TEST",
            full_name="Test Customer", customer_type="natural",
            actor="test",
        )
        return conn, result.customer_id, org_id

    def test_exact_threshold_triggers_large_cash(self):
        from amlkit.cases.manager import record_transaction
        conn, cust_id, org_id = self._setup_org_and_customer()
        _, triggered = record_transaction(
            conn, cust_id, org_id,
            direction="inbound", method="cash", amount=55000.0,
            actor="test",
        )
        rule_keys = [r.rule_key for r in triggered]
        assert "large_cash" in rule_keys

    def test_just_under_threshold_no_large_cash(self):
        from amlkit.cases.manager import record_transaction
        conn, cust_id, org_id = self._setup_org_and_customer()
        _, triggered = record_transaction(
            conn, cust_id, org_id,
            direction="inbound", method="cash", amount=54999.99,
            actor="test",
        )
        rule_keys = [r.rule_key for r in triggered]
        assert "large_cash" not in rule_keys

    def test_record_transaction_writes_money_columns(self):
        from amlkit.cases.manager import record_transaction
        conn, cust_id, org_id = self._setup_org_and_customer()
        txn_id, _ = record_transaction(
            conn, cust_id, org_id,
            direction="inbound", method="wire", amount=12345.67,
            actor="test",
        )
        row = conn.execute(
            "SELECT amount_units, amount_nanos FROM transactions WHERE id=?",
            (txn_id,),
        ).fetchone()
        assert row["amount_units"] == 12345
        assert row["amount_nanos"] == 670_000_000


def _create_test_org(conn):
    """Helper: create a minimal org and return its id."""
    cur = conn.execute(
        "INSERT INTO organizations (name, slug, created_at) "
        "VALUES ('Test Org', 'test-org', '2026-01-01')"
    )
    conn.commit()
    return cur.lastrowid


def _create_test_customer(conn, org_id):
    """Helper: create a minimal customer and return its id."""
    cur = conn.execute(
        "INSERT INTO customers (org_id, reference, full_name, customer_type, "
        "canonical_key, status, onboarded_at, created_at, updated_at) "
        "VALUES (?, 'REF-001', 'Test Person', 'natural', 'test person', "
        "'active', '2026-01-01', '2026-01-01', '2026-01-01')",
        (org_id,),
    )
    conn.commit()
    return cur.lastrowid

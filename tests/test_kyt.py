"""Transaction monitoring (KYT) tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import (  # noqa: E402
    disposition_transaction_alert,
    onboard,
    record_transaction,
)
from amlkit.db import connect, utcnow  # noqa: E402
from amlkit.screening.kyt import LARGE_CASH_THRESHOLD_AED  # noqa: E402


@pytest.fixture()
def conn():
    c = connect(":memory:")
    yield c
    c.close()


@pytest.fixture()
def org_id(conn) -> int:
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
        " RETURNING id",
        ("Test Firm", "test-firm", "active", utcnow()),
    ).fetchone()
    conn.commit()
    return row["id"]


@pytest.fixture()
def customer_id(conn, org_id) -> int:
    res = onboard(conn, org_id=org_id, reference="C-TXN-1", full_name="Ahmed Al Mansoori",
                  customer_type="natural", nationality="ae")
    return res.customer_id


class TestLargeCash:
    def test_large_cash_triggers(self, conn, org_id, customer_id) -> None:
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=LARGE_CASH_THRESHOLD_AED, actor="tester",
        )
        assert any(r.rule_key == "large_cash" for r in triggered)

    def test_small_cash_does_not_trigger(self, conn, org_id, customer_id) -> None:
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=1000.0, actor="tester",
        )
        assert not any(r.rule_key == "large_cash" for r in triggered)

    def test_large_wire_does_not_trigger_large_cash(self, conn, org_id, customer_id) -> None:
        """The large_cash rule is specifically about cash -- a large wire is
        not inherently the same risk signal."""
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="wire",
            amount=LARGE_CASH_THRESHOLD_AED * 2, actor="tester",
        )
        assert not any(r.rule_key == "large_cash" for r in triggered)

    def test_alert_row_is_written(self, conn, org_id, customer_id) -> None:
        record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=LARGE_CASH_THRESHOLD_AED, actor="tester",
        )
        n = conn.execute(
            "SELECT COUNT(*) c FROM transaction_alerts WHERE customer_id=? AND rule_key='large_cash'",
            (customer_id,),
        ).fetchone()["c"]
        assert n == 1


class TestStructuring:
    def test_two_near_threshold_deposits_trigger(self, conn, org_id, customer_id) -> None:
        occurred_1 = "2026-08-01T09:00:00+00:00"
        occurred_2 = "2026-08-02T09:00:00+00:00"
        record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=30000.0, occurred_at=occurred_1, actor="tester",
        )
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=30000.0, occurred_at=occurred_2, actor="tester",
        )
        assert any(r.rule_key == "structuring" for r in triggered)

    def test_single_near_threshold_deposit_does_not_trigger(self, conn, org_id, customer_id) -> None:
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=30000.0, actor="tester",
        )
        assert not any(r.rule_key == "structuring" for r in triggered)

    def test_deposits_outside_window_do_not_combine(self, conn, org_id, customer_id) -> None:
        record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=30000.0, occurred_at="2026-01-01T09:00:00+00:00", actor="tester",
        )
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=30000.0, occurred_at="2026-08-01T09:00:00+00:00", actor="tester",
        )
        assert not any(r.rule_key == "structuring" for r in triggered)


class TestHighRiskCountry:
    def test_high_risk_country_triggers(self, conn, org_id, customer_id) -> None:
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="outbound", method="wire",
            amount=5000.0, counterparty_country="kp", actor="tester",
        )
        assert any(r.rule_key == "high_risk_country" for r in triggered)

    def test_ordinary_country_does_not_trigger(self, conn, org_id, customer_id) -> None:
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="outbound", method="wire",
            amount=5000.0, counterparty_country="ae", actor="tester",
        )
        assert not any(r.rule_key == "high_risk_country" for r in triggered)


class TestVelocity:
    def test_many_transactions_in_a_day_trigger(self, conn, org_id, customer_id) -> None:
        base = "2026-08-01T0{}:00:00+00:00"
        triggered = []
        for i in range(7):
            _, triggered = record_transaction(
                conn, customer_id, org_id, direction="inbound", method="wire",
                amount=100.0, occurred_at=base.format(i), actor="tester",
            )
        assert any(r.rule_key == "velocity" for r in triggered)


class TestRecordTransaction:
    def test_rejects_zero_amount(self, conn, org_id, customer_id) -> None:
        with pytest.raises(ValueError):
            record_transaction(conn, customer_id, org_id, direction="inbound",
                               method="cash", amount=0, actor="tester")

    def test_foreign_currency_requires_amount_aed(self, conn, org_id, customer_id) -> None:
        with pytest.raises(ValueError):
            record_transaction(conn, customer_id, org_id, direction="inbound",
                               method="wire", amount=1000, currency="USD", actor="tester")

    def test_foreign_currency_with_amount_aed_succeeds(self, conn, org_id, customer_id) -> None:
        txn_id, _ = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="wire",
            amount=1000, currency="USD", amount_aed=3670.0, actor="tester",
        )
        row = conn.execute("SELECT amount_aed FROM transactions WHERE id=?", (txn_id,)).fetchone()
        assert row["amount_aed"] == 3670.0

    def test_cross_org_customer_is_rejected(self, conn, org_id, customer_id) -> None:
        """Same tenant-isolation property as add_case_note: a transaction
        cannot be attached to another org's customer."""
        other_org = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
            " RETURNING id",
            ("Other Firm", "other-firm-kyt", "active", utcnow()),
        ).fetchone()["id"]
        with pytest.raises(ValueError):
            record_transaction(conn, customer_id, other_org, direction="inbound",
                               method="cash", amount=1000, actor="tester")
        n = conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"]
        assert n == 0

    def test_transaction_is_audited(self, conn, org_id, customer_id) -> None:
        record_transaction(conn, customer_id, org_id, direction="inbound",
                           method="cash", amount=1000, actor="tester")
        n = conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE action='transaction.record'"
        ).fetchone()["c"]
        assert n == 1


class TestDisposition:
    def test_disposition_updates_status(self, conn, org_id, customer_id) -> None:
        record_transaction(conn, customer_id, org_id, direction="inbound", method="cash",
                           amount=LARGE_CASH_THRESHOLD_AED, actor="tester")
        alert_id = conn.execute(
            "SELECT id FROM transaction_alerts WHERE customer_id=?", (customer_id,)
        ).fetchone()["id"]
        disposition_transaction_alert(conn, alert_id, org_id, status="false_positive",
                                      note="Known payroll run", actor="reviewer")
        row = conn.execute(
            "SELECT status, disposition, dispositioned_by FROM transaction_alerts WHERE id=?",
            (alert_id,),
        ).fetchone()
        assert row["status"] == "false_positive"
        assert row["dispositioned_by"] == "reviewer"

    def test_rejects_invalid_status(self, conn, org_id, customer_id) -> None:
        record_transaction(conn, customer_id, org_id, direction="inbound", method="cash",
                           amount=LARGE_CASH_THRESHOLD_AED, actor="tester")
        alert_id = conn.execute(
            "SELECT id FROM transaction_alerts WHERE customer_id=?", (customer_id,)
        ).fetchone()["id"]
        with pytest.raises(ValueError):
            disposition_transaction_alert(conn, alert_id, org_id, status="open", actor="reviewer")

    def test_cross_org_alert_is_rejected(self, conn, org_id, customer_id) -> None:
        record_transaction(conn, customer_id, org_id, direction="inbound", method="cash",
                           amount=LARGE_CASH_THRESHOLD_AED, actor="tester")
        alert_id = conn.execute(
            "SELECT id FROM transaction_alerts WHERE customer_id=?", (customer_id,)
        ).fetchone()["id"]
        other_org = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
            " RETURNING id",
            ("Other Firm 2", "other-firm-kyt-2", "active", utcnow()),
        ).fetchone()["id"]
        with pytest.raises(ValueError):
            disposition_transaction_alert(conn, alert_id, other_org, status="false_positive",
                                          actor="reviewer")

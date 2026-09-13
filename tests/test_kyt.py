"""Transaction monitoring (KYT) tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import (  # noqa: E402
    disposition_transaction_alert,
    onboard,
    reassess_transaction_risk,
    record_transaction,
)
from amlkit.db import connect, upsert_dataset, utcnow  # noqa: E402
from amlkit.screening.kyt import LARGE_CASH_THRESHOLD_AED  # noqa: E402


@pytest.fixture()
def conn():
    c = connect(":memory:")
    # Create a fresh mandatory dataset so onboard() passes the staleness guard
    ds = upsert_dataset(c, "test_list", "Test List", is_mandatory=True)
    now = utcnow()
    c.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    c.commit()
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

    def test_evidence_total_excludes_already_alerted_large_cash(self, conn, org_id, customer_id) -> None:
        """total_aed in the structuring alert's evidence must reflect only the
        sub-threshold transactions that make the structuring case -- not a
        large cash deposit that already fired its own large_cash alert.
        Regression test for the 2026-08-23 continuous-improvement finding."""
        record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=LARGE_CASH_THRESHOLD_AED, occurred_at="2026-08-01T09:00:00+00:00",
            actor="tester",
        )
        record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=30000.0, occurred_at="2026-08-02T09:00:00+00:00", actor="tester",
        )
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=30000.0, occurred_at="2026-08-03T09:00:00+00:00", actor="tester",
        )
        structuring = next(r for r in triggered if r.rule_key == "structuring")
        assert structuring.detail["total_aed"] == pytest.approx(60000.0)
        assert structuring.detail["transaction_count"] == 2

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


class TestRiskFeedback:
    def test_transaction_alert_raises_cash_intensity(self, conn, org_id, customer_id) -> None:
        """Three large-cash alerts should push cash_intensity to predominantly_cash."""
        for _ in range(3):
            record_transaction(
                conn, customer_id, org_id, direction="inbound", method="cash",
                amount=LARGE_CASH_THRESHOLD_AED, actor="tester",
            )
        # After 3 open alerts, reassess_transaction_risk should have been called
        # by record_transaction and stored a higher cash_intensity rating.
        row = conn.execute(
            "SELECT factors FROM risk_assessments WHERE customer_id=? AND org_id=?"
            " ORDER BY id DESC LIMIT 1",
            (customer_id, org_id),
        ).fetchone()
        import json
        factors = json.loads(row["factors"])
        assert factors["cash_intensity"]["value"] == "predominantly_cash"

    def test_no_alert_no_reassessment(self, conn, org_id, customer_id) -> None:
        """A transaction that fires no rules must not create a new risk assessment."""
        initial_count = conn.execute(
            "SELECT COUNT(*) c FROM risk_assessments WHERE customer_id=? AND org_id=?",
            (customer_id, org_id),
        ).fetchone()["c"]
        record_transaction(
            conn, customer_id, org_id, direction="inbound", method="wire",
            amount=100.0, actor="tester",
        )
        final_count = conn.execute(
            "SELECT COUNT(*) c FROM risk_assessments WHERE customer_id=? AND org_id=?",
            (customer_id, org_id),
        ).fetchone()["c"]
        assert final_count == initial_count

    def test_reassess_transaction_risk_direct(self, conn, org_id, customer_id) -> None:
        """Direct call: 1 open alert → cash_intensity = mixed."""
        record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=LARGE_CASH_THRESHOLD_AED, actor="tester",
        )
        # Manually call to verify the mapping
        rating = reassess_transaction_risk(conn, customer_id, org_id, actor="tester")
        assert rating is not None
        row = conn.execute(
            "SELECT factors FROM risk_assessments WHERE customer_id=? AND org_id=?"
            " ORDER BY id DESC LIMIT 1",
            (customer_id, org_id),
        ).fetchone()
        import json
        factors = json.loads(row["factors"])
        assert factors["cash_intensity"]["value"] == "mixed"

    def test_reassess_transaction_risk_no_prior_returns_none(self, conn, org_id) -> None:
        """No prior assessment → returns None without writing anything."""
        # Onboard without completing risk assessment by deleting the auto-created one
        res = onboard(conn, org_id=org_id, reference="C-BARE", full_name="Bare Customer",
                      customer_type="natural", nationality="ae")
        conn.execute(
            "DELETE FROM risk_assessments WHERE customer_id=?", (res.customer_id,)
        )
        conn.commit()
        result = reassess_transaction_risk(conn, res.customer_id, org_id, actor="tester")
        assert result is None

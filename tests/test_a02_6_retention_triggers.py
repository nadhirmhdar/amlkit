"""Tests for A-02-6 (Board p96): Retention Triggers and Holds per CR 134/2025 Art. 25(2).

Cabinet Resolution No. 134 of 2025 Art. 25(2) mandates that customer due diligence
and transaction records be retained for not less than 5 years (amlkit firm policy:
RETENTION_YEARS = 10) from the MOST RECENT of six statutory triggers:
1. Termination of the business relationship
2. Account closure
3. Completion of an occasional transaction
4. Completion of inspection by the Supervisory Authority
5. Completion of an investigation
6. Issuance of a final court judgment

Additionally, an administrative retention-hold mechanism blocks purging regardless of
the computed date. All hold transitions and purge refusals must be recorded in audit_log.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any
import pytest

from amlkit.cases.manager import (
    RETENTION_YEARS,
    close_relationship,
    onboard,
    purge_expired,
)


def _years_ago(n: int) -> str:
    today = date.today()
    return today.replace(year=today.year - n).isoformat()


def _years_ahead(n: int) -> str:
    today = date.today()
    return today.replace(year=today.year + n).isoformat()


class TestRetentionTriggersAndHoldsArt25:
    """Test suite covering the 6 statutory retention triggers and holds under CR 134/2025 Art. 25(2)."""

    def test_retention_years_firm_policy_is_ten(self) -> None:
        """Firm policy maintains a 10-year retention period above the 5-year statutory floor."""
        assert RETENTION_YEARS == 10, (
            f"RETENTION_YEARS must be 10 per firm policy (#78, #313). Got {RETENTION_YEARS}."
        )

    def test_most_recent_trigger_wins_investigation_after_exit(self, conn, org_id) -> None:
        """Case 1: Customer exited 6 years ago, investigation completed 1 year ago -> NOT purged.

        Under Art. 25(2), retention runs from the most recent procedure.
        Exit 6 yrs ago + 10 yrs = 4 yrs remaining.
        Investigation completed 1 yr ago + 10 yrs = 9 yrs remaining.
        Customer must NOT be purged.
        """
        # Dynamic import of new trigger function to be implemented by lonappan
        from amlkit.cases import manager

        res = onboard(conn, org_id=org_id, reference="C-A026-1", full_name="Investigation Subject")
        cid = res.customer_id

        # Exited 6 years ago
        exit_date = _years_ago(6)
        conn.execute(
            "UPDATE customers SET status='closed', exit_date=?, updated_at=? WHERE id=?",
            (exit_date, exit_date, cid),
        )
        conn.commit()

        # Record completed investigation from 1 year ago
        investigation_date = _years_ago(1)
        assert hasattr(manager, "record_retention_trigger"), (
            "manager.py must provide record_retention_trigger() for Art. 25(2) triggers"
        )
        manager.record_retention_trigger(
            conn,
            customer_id=cid,
            org_id=org_id,
            trigger_type="investigation",
            trigger_date=investigation_date,
            actor="compliance_officer",
            reference_note="Supervisory referral #INV-2025-09",
        )

        # Check computed retention_until
        row = conn.execute("SELECT retention_until FROM customers WHERE id=?", (cid,)).fetchone()
        expected_retention_year = date.today().year + 9
        actual_retention = date.fromisoformat(row["retention_until"])
        assert abs(actual_retention.year - expected_retention_year) <= 1, (
            f"retention_until should anchor to investigation completion (expected ~{expected_retention_year}, got {actual_retention.year})"
        )

        # Attempt purge
        result = purge_expired(conn, org_id=org_id, actor="system")
        assert result["purged"] == 0, "Customer with recent investigation trigger must NOT be purged"

        # Customer still exists
        surviving = conn.execute("SELECT id FROM customers WHERE id=?", (cid,)).fetchone()
        assert surviving is not None, "Customer record must remain in database"

    def test_past_retention_purged_when_no_other_triggers(self, conn, org_id) -> None:
        """Case 2: Customer exited 11 years ago, no other triggers -> purged.

        Exit 11 yrs ago + 10 yrs retention = expired 1 year ago.
        Without holds or later procedures, customer is eligible for purge.
        """
        from amlkit.cases import manager

        res = onboard(conn, org_id=org_id, reference="C-A026-2", full_name="Expired Exit Customer")
        cid = res.customer_id

        # Exited 11 years ago
        exit_date = _years_ago(11)
        expired_retention = _years_ago(1)
        conn.execute(
            "UPDATE customers SET status='closed', exit_date=?, retention_until=?, updated_at=? WHERE id=?",
            (exit_date, expired_retention, exit_date, cid),
        )
        conn.commit()

        result = purge_expired(conn, org_id=org_id, actor="system")
        assert result["purged"] >= 1, "Expired customer with no active holds or procedures must be purged"

        purged_row = conn.execute("SELECT id FROM customers WHERE id=?", (cid,)).fetchone()
        assert purged_row is None, "Customer row must be deleted upon purge"

    def test_active_hold_blocks_purge_and_logs_audit_refusal(self, conn, org_id) -> None:
        """Case 3: Customer exited 11 years ago (past retention date), active hold set -> NOT purged.

        A retention hold blocks purge regardless of date.
        purge_expired must log a refusal in audit_log.
        """
        from amlkit.cases import manager

        res = onboard(conn, org_id=org_id, reference="C-A026-3", full_name="Held Expired Customer")
        cid = res.customer_id

        expired_date = _years_ago(11)
        expired_retention = _years_ago(1)
        conn.execute(
            "UPDATE customers SET status='closed', exit_date=?, retention_until=?, updated_at=? WHERE id=?",
            (expired_date, expired_retention, expired_date, cid),
        )
        conn.commit()

        assert hasattr(manager, "set_retention_hold"), (
            "manager.py must provide set_retention_hold() to block purge"
        )
        manager.set_retention_hold(
            conn,
            customer_id=cid,
            org_id=org_id,
            reason="Court document preservation subpoena",
            actor="legal_counsel",
        )

        # Purge attempt
        result = purge_expired(conn, org_id=org_id, actor="system")
        assert result["purged"] == 0, "Active retention hold MUST block purge"

        # Customer still exists
        row = conn.execute("SELECT id FROM customers WHERE id=?", (cid,)).fetchone()
        assert row is not None, "Held customer must not be deleted"

        # Audit refusal entry must exist
        refusal = conn.execute(
            "SELECT * FROM audit_log WHERE action='retention.purge_refused' AND object_id=? AND org_id=?",
            (str(cid), org_id),
        ).fetchone()
        assert refusal is not None, "Refusal to purge held customer must be recorded in audit_log"

    def test_hold_lifecycle_set_then_release_allows_purge(self, conn, org_id) -> None:
        """Case 4: Hold set, then explicitly released, then purge attempt -> purged.

        Both hold-set and hold-release events must be recorded in audit_log.
        Once released, an expired record is purged.
        """
        from amlkit.cases import manager

        res = onboard(conn, org_id=org_id, reference="C-A026-4", full_name="Released Hold Customer")
        cid = res.customer_id

        expired_date = _years_ago(11)
        expired_retention = _years_ago(1)
        conn.execute(
            "UPDATE customers SET status='closed', exit_date=?, retention_until=?, updated_at=? WHERE id=?",
            (expired_date, expired_retention, expired_date, cid),
        )
        conn.commit()

        assert hasattr(manager, "set_retention_hold") and hasattr(manager, "release_retention_hold"), (
            "manager.py must provide set_retention_hold() and release_retention_hold()"
        )

        # 1. Set hold
        manager.set_retention_hold(
            conn,
            customer_id=cid,
            org_id=org_id,
            reason="Temporary inspection freeze",
            actor="compliance_lead",
        )

        # 2. Release hold
        manager.release_retention_hold(
            conn,
            customer_id=cid,
            org_id=org_id,
            reason="Inspection concluded with no findings",
            actor="compliance_lead",
        )

        # Verify audit entries for both set and release
        hold_set_audit = conn.execute(
            "SELECT * FROM audit_log WHERE action='retention.hold_set' AND object_id=? AND org_id=?",
            (str(cid), org_id),
        ).fetchone()
        assert hold_set_audit is not None, "retention.hold_set must be recorded in audit_log"

        hold_released_audit = conn.execute(
            "SELECT * FROM audit_log WHERE action='retention.hold_released' AND object_id=? AND org_id=?",
            (str(cid), org_id),
        ).fetchone()
        assert hold_released_audit is not None, "retention.hold_released must be recorded in audit_log"

        # 3. Purge should now succeed
        result = purge_expired(conn, org_id=org_id, actor="system")
        assert result["purged"] >= 1, "Customer with released hold should now be purged"

        purged_row = conn.execute("SELECT id FROM customers WHERE id=?", (cid,)).fetchone()
        assert purged_row is None, "Customer row must be gone after purge"

    def test_monotonicity_never_shortens_stored_retention_date(self, conn, org_id) -> None:
        """Case 5: Recomputation of retention_until never produces an earlier date than stored.

        Extending retention is allowed; shortening is strictly prohibited under any code path.
        """
        from amlkit.cases import manager

        res = onboard(conn, org_id=org_id, reference="C-A026-5", full_name="Monotonic Customer")
        cid = res.customer_id

        # Existing stored retention is 10 years ahead
        initial_retention = _years_ahead(10)
        conn.execute(
            "UPDATE customers SET status='closed', retention_until=?, updated_at=? WHERE id=?",
            (initial_retention, date.today().isoformat(), cid),
        )
        conn.commit()

        assert hasattr(manager, "recompute_retention_until"), (
            "manager.py must provide recompute_retention_until()"
        )

        # Attempt to record an older trigger (e.g. occasional transaction 5 years ago)
        older_trigger = _years_ago(5)
        manager.record_retention_trigger(
            conn,
            customer_id=cid,
            org_id=org_id,
            trigger_type="occasional_transaction",
            trigger_date=older_trigger,
            actor="system",
        )

        # Recompute
        computed = manager.recompute_retention_until(conn, customer_id=cid, org_id=org_id)
        assert date.fromisoformat(computed) >= date.fromisoformat(initial_retention), (
            f"Monotonicity violation: recomputed retention ({computed}) is earlier than stored ({initial_retention})"
        )

        row = conn.execute("SELECT retention_until FROM customers WHERE id=?", (cid,)).fetchone()
        assert date.fromisoformat(row["retention_until"]) >= date.fromisoformat(initial_retention), (
            "Stored retention_until must not be shortened"
        )

    def test_all_six_statutory_triggers_supported(self, conn, org_id) -> None:
        """Case 6: Model explicitly supports all 6 statutory triggers from CR 134/2025 Art. 25(2)."""
        from amlkit.cases import manager

        assert hasattr(manager, "STATUTORY_RETENTION_TRIGGERS"), (
            "manager.py must export STATUTORY_RETENTION_TRIGGERS set/tuple"
        )

        expected_triggers = {
            "business_relationship_termination",
            "account_closure",
            "occasional_transaction",
            "supervisory_inspection",
            "investigation",
            "court_judgment",
        }

        supported = set(manager.STATUTORY_RETENTION_TRIGGERS)
        missing = expected_triggers - supported
        assert not missing, f"Missing statutory triggers from Art. 25(2): {missing}"

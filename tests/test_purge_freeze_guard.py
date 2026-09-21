"""Issue #140: Guard customer purge against active TFS freeze obligations.

Customers with active freeze_obligations (status != 'resolved') must NOT
be purged even if retention_until has passed. Purging a frozen customer's
records would destroy evidence required for ongoing TFS compliance.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import RETENTION_YEARS, onboard, purge_expired  # noqa: E402
from amlkit.db import connect, upsert_dataset, utcnow, audit  # noqa: E402
from amlkit.names.arabic import blocking_keys, canonical_key  # noqa: E402


@pytest.fixture()
def conn():
    c = connect(":memory:")
    ds = upsert_dataset(c, "test_list", "Synthetic Test List", is_mandatory=True)
    now = utcnow()
    c.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    cur = c.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           countries, birth_date, gender, topics, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "SYN-1", "Person", "JOHN DOE", '["us"]', "1990-01-01", "male",
         '["sanction"]', "{}", now, now),
    )
    eid = cur.lastrowid
    c.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
        " VALUES (?,?,?,?,?)", (eid, "JOHN DOE", "primary", canonical_key("JOHN DOE"), "latin"))
    for tok in blocking_keys("JOHN DOE"):
        c.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)", (tok, eid))
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


def _make_closed_expired_customer(conn, org_id, ref="CUST-FROZEN"):
    """Create a customer that is closed and past retention."""
    now = utcnow()
    conn.execute(
        """INSERT INTO customers
           (org_id, reference, customer_type, full_name, canonical_key,
            status, onboarded_at, retention_until, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (org_id, ref, "natural", "Frozen Person",
         canonical_key("Frozen Person"), "closed", now, "2020-01-01", now, now),
    )
    cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    return cid


class TestPurgeFreezeGuard:
    def test_frozen_customer_not_purged(self, conn, org_id) -> None:
        """Customer with active freeze obligation must not be purged."""
        cid = _make_closed_expired_customer(conn, org_id)
        now = utcnow()
        conn.execute(
            """INSERT INTO freeze_obligations
               (org_id, customer_id, obligation_type, risk_category,
                identified_at, identified_by, status)
               VALUES (?,?,?,?,?,?,?)""",
            (org_id, cid, "sanctions", "high", now, "test", "executed_pending_report"),
        )
        conn.commit()

        result = purge_expired(conn, org_id, actor="test")
        assert result["purged"] == 0

        row = conn.execute(
            "SELECT id FROM customers WHERE id=? AND org_id=?", (cid, org_id)
        ).fetchone()
        assert row is not None, "Frozen customer must not be purged"

    def test_resolved_freeze_allows_purge(self, conn, org_id) -> None:
        """Customer with only resolved freeze obligations CAN be purged."""
        cid = _make_closed_expired_customer(conn, org_id, ref="CUST-RESOLVED")
        now = utcnow()
        conn.execute(
            """INSERT INTO freeze_obligations
               (org_id, customer_id, obligation_type, risk_category,
                identified_at, identified_by, resolved_at, resolved_by,
                resolution_reason, status)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (org_id, cid, "sanctions", "high", now, "test",
             now, "mlro", "delisted", "resolved"),
        )
        conn.commit()

        result = purge_expired(conn, org_id, actor="test")
        assert result["purged"] == 1

        row = conn.execute(
            "SELECT id FROM customers WHERE id=? AND org_id=?", (cid, org_id)
        ).fetchone()
        assert row is None, "Resolved freeze should allow purge"

    def test_frozen_customer_audit_logged(self, conn, org_id) -> None:
        """Skipping a frozen customer must produce an audit entry."""
        cid = _make_closed_expired_customer(conn, org_id, ref="CUST-AUDIT")
        now = utcnow()
        conn.execute(
            """INSERT INTO freeze_obligations
               (org_id, customer_id, obligation_type, risk_category,
                identified_at, identified_by, status)
               VALUES (?,?,?,?,?,?,?)""",
            (org_id, cid, "proliferation", "critical", now, "test", "pending_execution"),
        )
        conn.commit()

        purge_expired(conn, org_id, actor="test")

        log = conn.execute(
            "SELECT action, detail FROM audit_log WHERE object_type='customer'"
            " AND object_id=? AND org_id=? ORDER BY ts DESC LIMIT 1",
            (cid, org_id),
        ).fetchone()
        assert log is not None, "Audit entry must be written for skipped frozen customer"
        assert "freeze" in log["action"] or "freeze" in (log["detail"] or "").lower()

    def test_unfrozen_customer_still_purged(self, conn, org_id) -> None:
        """Customer with no freeze obligations is purged normally."""
        cid = _make_closed_expired_customer(conn, org_id, ref="CUST-NORMAL")

        result = purge_expired(conn, org_id, actor="test")
        assert result["purged"] == 1

        row = conn.execute(
            "SELECT id FROM customers WHERE id=? AND org_id=?", (cid, org_id)
        ).fetchone()
        assert row is None

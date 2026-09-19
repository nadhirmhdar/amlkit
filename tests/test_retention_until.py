"""Issue #96: retention_until must never be NULL.

New customers must get retention_until = onboarded_at + RETENTION_YEARS on
creation. Existing customers with NULL retention_until must be backfilled.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import RETENTION_YEARS, onboard  # noqa: E402
from amlkit.db import connect, upsert_dataset, utcnow  # noqa: E402
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


class TestRetentionUntilOnCreation:
    def test_onboard_sets_retention_until(self, conn, org_id) -> None:
        """New customer must have retention_until = onboarded_at + RETENTION_YEARS."""
        result = onboard(
            conn,
            org_id=org_id,
            reference="CUST-001",
            full_name="Jane Smith",
            actor="test",
        )
        row = conn.execute(
            "SELECT onboarded_at, retention_until FROM customers WHERE id=?",
            (result.customer_id,),
        ).fetchone()
        assert row["retention_until"] is not None, "retention_until must not be NULL"
        onboarded = row["onboarded_at"][:10]
        expected_year = int(onboarded[:4]) + RETENTION_YEARS
        assert row["retention_until"].startswith(str(expected_year))


class TestRetentionUntilBackfill:
    def test_backfill_sets_retention_for_null_rows(self, conn, org_id) -> None:
        """Existing customers with NULL retention_until must be backfilled."""
        now = utcnow()
        conn.execute(
            """INSERT INTO customers
               (org_id, reference, customer_type, full_name, canonical_key,
                onboarded_at, retention_until, created_at, updated_at)
               VALUES (?,?,?,?,?,?,NULL,?,?)""",
            (org_id, "LEGACY-001", "natural", "Legacy Customer",
             canonical_key("Legacy Customer"), now, now, now),
        )
        conn.commit()

        row = conn.execute(
            "SELECT retention_until FROM customers WHERE reference='LEGACY-001' AND org_id=?",
            (org_id,),
        ).fetchone()
        assert row["retention_until"] is None, "Precondition: retention_until should be NULL before backfill"

        from amlkit.db import _backfill_retention_until
        _backfill_retention_until(conn)
        conn.commit()

        row = conn.execute(
            "SELECT retention_until FROM customers WHERE reference='LEGACY-001' AND org_id=?",
            (org_id,),
        ).fetchone()
        assert row["retention_until"] is not None, "retention_until must be backfilled"

    def test_backfill_does_not_overwrite_existing(self, conn, org_id) -> None:
        """Customers with an existing retention_until must not be changed."""
        now = utcnow()
        existing_date = "2035-06-15"
        conn.execute(
            """INSERT INTO customers
               (org_id, reference, customer_type, full_name, canonical_key,
                onboarded_at, retention_until, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (org_id, "EXISTING-001", "natural", "Existing Customer",
             canonical_key("Existing Customer"), now, existing_date, now, now),
        )
        conn.commit()

        from amlkit.db import _backfill_retention_until
        _backfill_retention_until(conn)
        conn.commit()

        row = conn.execute(
            "SELECT retention_until FROM customers WHERE reference='EXISTING-001' AND org_id=?",
            (org_id,),
        ).fetchone()
        assert row["retention_until"] == existing_date

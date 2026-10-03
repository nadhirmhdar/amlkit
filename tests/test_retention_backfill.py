"""Tests for scripts/backfill_retention.py (#79).

Additive retention backfill: closed customers whose retention_until was
computed under an older, shorter firm retention policy get their date
extended to the current policy. Contract pinned here:

* dry run (default) writes nothing;
* --commit extends only forward, stamps retention_backfilled_at, and is
  idempotent (a second run is a no-op);
* a record already retaining longer than the new policy is left untouched;
* active customers and null-retention rows are never touched;
* every extension is audited, scoped to the owning org;
* the backfill is tenant-isolated: it never touches another org's rows.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import onboard  # noqa: E402
from amlkit.db import connect, upsert_dataset, utcnow  # noqa: E402
from amlkit.names.arabic import blocking_keys, canonical_key  # noqa: E402
from scripts.backfill_retention import (  # noqa: E402
    _add_years,
    backfill_org,
    plan_backfill,
)

LISTED = "AHMED ABD AL-JALEEL AL-HASNAWI"


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
        (ds, "SYN-1", "Person", LISTED, '["ly"]', "1975-03-12", "male",
         '["sanction"]', "{}", now, now),
    )
    eid = cur.lastrowid
    c.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
        " VALUES (?,?,?,?,?)", (eid, LISTED, "primary", canonical_key(LISTED), "latin"))
    for tok in blocking_keys(LISTED):
        c.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)", (tok, eid))
    c.commit()
    yield c
    c.close()


def _org(conn, slug="firm-a"):
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
        " RETURNING id",
        (slug, slug, "active", utcnow()),
    ).fetchone()
    conn.commit()
    return row["id"]


def _closed_customer(conn, org_id, ref, retention_until):
    res = onboard(conn, org_id=org_id, reference=ref, full_name="Ahmed Al Mansoori")
    conn.execute(
        "UPDATE customers SET status='closed', retention_until=? WHERE id=? AND org_id=?",
        (retention_until, res.customer_id, org_id),
    )
    conn.commit()
    return res.customer_id


def test_add_years_basic():
    assert _add_years("2020-01-15", 5) == "2025-01-15"


def test_add_years_leap_day_fallback():
    assert _add_years("2020-02-29", 1) == "2021-03-01"


def test_dry_run_writes_nothing(conn):
    org = _org(conn)
    cid = _closed_customer(conn, org, "C-1", "2027-01-01")
    summary = backfill_org(conn, org, old_years=5, new_years=10, commit=False)
    assert summary["dry_run"] is True
    assert len(summary["plan"]) == 1
    row = conn.execute("SELECT retention_until, retention_backfilled_at FROM customers WHERE id=?", (cid,)).fetchone()
    assert row["retention_until"] == "2027-01-01"
    assert row["retention_backfilled_at"] is None


def test_commit_extends_forward_and_stamps(conn):
    org = _org(conn)
    cid = _closed_customer(conn, org, "C-1", "2027-01-01")
    summary = backfill_org(conn, org, old_years=5, new_years=10, commit=True)
    assert summary["extended"] == 1
    row = conn.execute("SELECT retention_until, retention_backfilled_at FROM customers WHERE id=?", (cid,)).fetchone()
    assert row["retention_until"] == "2032-01-01"
    assert row["retention_backfilled_at"] is not None


def test_idempotent_second_run_is_noop(conn):
    org = _org(conn)
    cid = _closed_customer(conn, org, "C-1", "2027-01-01")
    backfill_org(conn, org, old_years=5, new_years=10, commit=True)
    first = conn.execute("SELECT retention_until FROM customers WHERE id=?", (cid,)).fetchone()["retention_until"]
    summary2 = backfill_org(conn, org, old_years=5, new_years=10, commit=True)
    assert summary2["extended"] == 0
    second = conn.execute("SELECT retention_until FROM customers WHERE id=?", (cid,)).fetchone()["retention_until"]
    assert first == second == "2032-01-01"


def test_active_customer_never_touched(conn):
    org = _org(conn)
    res = onboard(conn, org_id=org, reference="C-ACT", full_name="Active Co")
    conn.execute("UPDATE customers SET retention_until='2027-01-01' WHERE id=?", (res.customer_id,))
    conn.commit()
    backfill_org(conn, org, old_years=5, new_years=10, commit=True)
    row = conn.execute("SELECT retention_until, retention_backfilled_at FROM customers WHERE id=?", (res.customer_id,)).fetchone()
    assert row["retention_until"] == "2027-01-01"
    assert row["retention_backfilled_at"] is None


def test_null_retention_never_touched(conn):
    org = _org(conn)
    res = onboard(conn, org_id=org, reference="C-NULL", full_name="No Date Co")
    conn.execute("UPDATE customers SET status='closed', retention_until=NULL WHERE id=?", (res.customer_id,))
    conn.commit()
    summary = backfill_org(conn, org, old_years=5, new_years=10, commit=True)
    assert summary["extended"] == 0


def test_writes_audit_scoped_to_org(conn):
    org = _org(conn)
    cid = _closed_customer(conn, org, "C-1", "2027-01-01")
    backfill_org(conn, org, old_years=5, new_years=10, commit=True)
    row = conn.execute(
        "SELECT org_id, object_id FROM audit_log WHERE action='retention.backfill' AND org_id=?",
        (org,),
    ).fetchone()
    assert row is not None
    assert row["org_id"] == org
    assert row["object_id"] == str(cid)


def test_tenant_isolation(conn):
    org_a = _org(conn, "firm-a")
    org_b = _org(conn, "firm-b")
    cid_a = _closed_customer(conn, org_a, "A-1", "2027-01-01")
    cid_b = _closed_customer(conn, org_b, "B-1", "2027-01-01")
    backfill_org(conn, org_a, old_years=5, new_years=10, commit=True)
    row_a = conn.execute("SELECT retention_until FROM customers WHERE id=?", (cid_a,)).fetchone()
    row_b = conn.execute("SELECT retention_until FROM customers WHERE id=?", (cid_b,)).fetchone()
    assert row_a["retention_until"] == "2032-01-01"
    assert row_b["retention_until"] == "2027-01-01"


def test_noop_when_new_not_longer(conn):
    org = _org(conn)
    _closed_customer(conn, org, "C-1", "2027-01-01")
    summary = backfill_org(conn, org, old_years=10, new_years=10, commit=True)
    assert summary["extended"] == 0


def test_plan_backfill_is_pure_read(conn):
    org = _org(conn)
    cid = _closed_customer(conn, org, "C-1", "2027-01-01")
    plan = plan_backfill(conn, org, extra_years=5)
    assert len(plan) == 1
    assert plan[0]["customer_id"] == cid
    assert plan[0]["new_until"] == "2032-01-01"
    row = conn.execute("SELECT retention_until FROM customers WHERE id=?", (cid,)).fetchone()
    assert row["retention_until"] == "2027-01-01"

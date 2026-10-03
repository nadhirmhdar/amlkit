"""Backfill retention dates for records stored under an older retention rule.

Why this exists
---------------
`cases/manager.close_relationship()` stamps `retention_until` when a customer
relationship ends. The stored date reflects whatever retention floor was in
force at the time of closure. When a firm's retention policy lengthens (e.g.
a 5-year floor superseded by a 10-year firm policy), customers closed under
the *old* rule keep the *shorter* date and would be eligible for purge too
early. This script walks closed customers, per org, and extends any
retention date that was computed under the old rule up to the new one.

It is deliberately *additive and standalone*:

* It never shortens a retention date -- only extends. A record already set
  to retain longer than the new policy (manual hold, legal freeze) is left
  untouched.
* It stamps `customers.retention_backfilled_at` so a second run is a no-op:
  an already-stamped row is skipped, so repeated runs can never
  double-extend a date.
* `--commit` is required to write. Without it the script previews (dry run),
  the same disabled-by-default posture the purge job takes, since moving a
  compliance retention date is not something to do by accident.
* Every extension is written to the append-only audit log, scoped to the
  owning org, before (and independently of) the row update.

The arithmetic works off the stored date, not a remembered close date: a
record closed under an N-year rule carries `retention_until = close + N`, so
extending to an M-year policy means adding (M - N) years to the stored
`retention_until`. That keeps the script correct without needing to know the
original close date.

Usage
-----
    # Preview every org (default: old 5yr -> new 10yr), writes nothing:
    python scripts/backfill_retention.py

    # Actually apply, one org:
    python scripts/backfill_retention.py --commit --org 3

    # Different policy transition:
    python scripts/backfill_retention.py --old-years 5 --new-years 10 --commit

Exit codes:
    0  completed (preview or commit); nothing to do is also 0
    2  bad arguments
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import audit, connect, utcnow  # noqa: E402


def _add_years(iso_date: str, years: int) -> str:
    """Add whole years to an ISO date string, mirroring the leap-year
    fallback close_relationship() uses (Feb 29 -> Feb 28 next year)."""
    d = date.fromisoformat(iso_date)
    try:
        return d.replace(year=d.year + years).isoformat()
    except ValueError:
        return (d + timedelta(days=365 * years + 1)).isoformat()


def plan_backfill(
    conn: sqlite3.Connection,
    org_id: int,
    *,
    extra_years: int,
) -> list[dict[str, Any]]:
    """Return the list of extensions that would be applied for one org.

    Pure read: selects closed customers that (a) have a retention date,
    (b) have not already been backfilled, and (c) would move *forward* under
    the new policy. Does not write.
    """
    rows = conn.execute(
        "SELECT id, reference, retention_until FROM customers"
        " WHERE org_id=? AND status='closed'"
        " AND retention_until IS NOT NULL"
        " AND retention_backfilled_at IS NULL",
        (org_id,),
    ).fetchall()

    plan: list[dict[str, Any]] = []
    for r in rows:
        old_until = r["retention_until"]
        new_until = _add_years(old_until, extra_years)
        if new_until <= old_until:
            # Never shorten (or no-op) an existing retention date.
            continue
        plan.append(
            {
                "customer_id": r["id"],
                "reference": r["reference"],
                "old_until": old_until,
                "new_until": new_until,
            }
        )
    return plan


def backfill_org(
    conn: sqlite3.Connection,
    org_id: int,
    *,
    old_years: int,
    new_years: int,
    commit: bool,
    actor: str = "system",
) -> dict[str, Any]:
    """Backfill one org. Returns a summary dict.

    When `commit` is False this previews only (writes nothing). When True,
    each extension writes a `retention.backfill` audit row (scoped to
    `org_id`) before the customer row is updated and stamped.
    """
    extra_years = new_years - old_years
    if extra_years <= 0:
        return {"org_id": org_id, "extended": 0, "plan": [], "noop_reason": "new policy not longer than old"}

    plan = plan_backfill(conn, org_id, extra_years=extra_years)

    if not commit:
        return {"org_id": org_id, "extended": 0, "plan": plan, "dry_run": True}

    stamp = utcnow()
    for item in plan:
        cid = item["customer_id"]
        with conn:
            audit(
                conn, actor, "retention.backfill", "customer", cid,
                {
                    "reference": item["reference"],
                    "old_until": item["old_until"],
                    "new_until": item["new_until"],
                    "old_years": old_years,
                    "new_years": new_years,
                },
                org_id=org_id,
            )
            conn.execute(
                "UPDATE customers SET retention_until=?, retention_backfilled_at=?,"
                " updated_at=? WHERE id=? AND org_id=?",
                (item["new_until"], stamp, stamp, cid, org_id),
            )
    return {"org_id": org_id, "extended": len(plan), "plan": plan}


def _org_ids(conn: sqlite3.Connection, only: int | None) -> list[int]:
    if only is not None:
        return [only]
    return [r["id"] for r in conn.execute("SELECT id FROM organizations ORDER BY id")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill retention dates under a new policy.")
    ap.add_argument("--old-years", type=int, default=5, help="retention years records were stored under (default 5)")
    ap.add_argument("--new-years", type=int, default=10, help="current firm retention policy in years (default 10)")
    ap.add_argument("--org", type=int, default=None, help="limit to one org id (default: all orgs)")
    ap.add_argument("--commit", action="store_true", help="apply changes (default: preview only)")
    args = ap.parse_args(argv)

    if args.new_years <= args.old_years:
        print(f"new-years ({args.new_years}) must exceed old-years ({args.old_years}); nothing to backfill.")
        return 0

    conn = connect()
    try:
        total = 0
        for oid in _org_ids(conn, args.org):
            summary = backfill_org(
                conn, oid,
                old_years=args.old_years, new_years=args.new_years,
                commit=args.commit,
            )
            plan = summary["plan"]
            if not plan:
                continue
            mode = "WOULD EXTEND" if not args.commit else "EXTENDED"
            print(f"org {oid}: {mode} {len(plan)} record(s) ({args.old_years}yr -> {args.new_years}yr)")
            for item in plan:
                print(f"    customer {item['customer_id']} [{item['reference']}]: {item['old_until']} -> {item['new_until']}")
            total += len(plan)
        if total == 0:
            print("Nothing to backfill.")
        elif not args.commit:
            print(f"\nPreview only. Re-run with --commit to apply {total} change(s).")
        else:
            print(f"\nApplied {total} change(s).")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

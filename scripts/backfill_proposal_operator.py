"""Backfill alert_reviews.operator_id on legacy four-eyes proposals (N8 / CR-1b).

`cases.review.confirm_disposition` no longer compares display names: a proposal
whose `operator_id` is NULL is treated as proposed-by-unknown. This script fills
the id where the audit trail identifies the proposer unambiguously, so those
proposals regain the "proposer cannot confirm" protection.

A row is filled only when ALL of these hold:
  * exactly one `alert.propose` audit row for that alert (same org) lies within
    WINDOW_SECONDS of the review row's `created_at`, and
  * exactly one operator in the same org carries that audit actor's name.
Anything else (no audit row, several audit rows or actors, name not found or
shared) is listed as ambiguous and left NULL.

    python scripts/backfill_proposal_operator.py            # dry run (default)
    python scripts/backfill_proposal_operator.py --apply    # write

Exit code is 0 on success (dry run or applied), 2 on bad arguments.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect  # noqa: E402

WINDOW_SECONDS = 120


def _ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def plan(conn) -> tuple[list[dict], list[dict]]:
    """Return (fillable, ambiguous). Each item has review_id, alert_id, org_id
    and either operator_id (fillable) or reason (ambiguous)."""
    fillable: list[dict] = []
    ambiguous: list[dict] = []
    reviews = conn.execute(
        "SELECT id, org_id, alert_id, operator, created_at FROM alert_reviews"
        " WHERE action='propose' AND operator_id IS NULL ORDER BY id"
    ).fetchall()
    for r in reviews:
        base = {"review_id": r["id"], "alert_id": r["alert_id"], "org_id": r["org_id"],
                "operator": r["operator"]}
        created = _ts(r["created_at"])
        events = []
        for a in conn.execute(
            "SELECT actor, ts FROM audit_log WHERE action='alert.propose'"
            " AND object_type='alert' AND object_id=? AND org_id=?",
            (str(r["alert_id"]), r["org_id"]),
        ):
            at = _ts(a["ts"])
            if created is not None and at is not None and \
                    abs((at - created).total_seconds()) <= WINDOW_SECONDS:
                events.append(a["actor"])
        if len(events) != 1:
            ambiguous.append(base | {"reason": f"{len(events)} matching audit events"})
            continue
        ops = conn.execute(
            "SELECT id FROM operators WHERE org_id=? AND name=?", (r["org_id"], events[0])
        ).fetchall()
        if len(ops) != 1:
            ambiguous.append(base | {"reason": f"{len(ops)} operators named {events[0]!r}"})
            continue
        fillable.append(base | {"operator_id": ops[0]["id"]})
    return fillable, ambiguous


def apply(conn, fillable: list[dict]) -> int:
    n = 0
    with conn:
        for f in fillable:
            cur = conn.execute(
                "UPDATE alert_reviews SET operator_id=? WHERE id=? AND org_id=?"
                " AND operator_id IS NULL",
                (f["operator_id"], f["review_id"], f["org_id"]),
            )
            n += cur.rowcount
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write the fills (default: dry run)")
    args = ap.parse_args(argv)
    conn = connect()
    fillable, ambiguous = plan(conn)
    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"[{mode}] proposals with NULL operator_id: {len(fillable) + len(ambiguous)}")
    for f in fillable:
        print(f"  fill   review {f['review_id']} (alert {f['alert_id']}, org {f['org_id']})"
              f" -> operator_id {f['operator_id']}")
    for a in ambiguous:
        print(f"  LEAVE  review {a['review_id']} (alert {a['alert_id']}, org {a['org_id']}):"
              f" {a['reason']}")
    if args.apply:
        print(f"updated {apply(conn, fillable)} row(s)")
    else:
        print("dry run: nothing written (use --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

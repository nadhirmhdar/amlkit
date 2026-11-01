"""Extend retention_until for closed customers to closure date + RETENTION_YEARS (#79).

Dry-run by default: lists, per organisation, each affected customer's reference
and old -> new date (no names). Pass --apply to write. Idempotent and
extend-only: a date already on or after the recomputed one is left alone, so a
second run changes nothing. Writes one `retention.extended` audit row per
change (customer id and dates only, scoped to the customer's org).

Closure date: the `customer.close` audit row, else the customer's exit_date,
else today (conservative).

Exit codes:
    0  success (including nothing to change)
    1  error
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import RETENTION_YEARS, extend_closed_retention
from amlkit.db import connect


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="Path to SQLite database (overrides AMLKIT_DB env var)")
    parser.add_argument("--apply", action="store_true", help="Write the changes (default is dry-run)")
    args = parser.parse_args(argv)

    try:
        db_path = args.db or os.environ.get("AMLKIT_DB")
        conn = connect(db_path) if db_path else connect()
    except Exception as exc:
        print(f"ERROR: cannot open database: {exc}", file=sys.stderr)
        return 1

    changes = extend_closed_retention(conn, apply=args.apply, actor="script:extend_retention")
    label = "extended" if args.apply else "would extend"
    total = 0
    for org_id, items in changes.items():
        print(f"org {org_id}: {label} {len(items)} customer(s) (RETENTION_YEARS={RETENTION_YEARS})")
        for it in items:
            print(f"  {it['reference']}: {it['from']} -> {it['to']}")
        total += len(items)
    print(f"{'' if args.apply else '[dry-run] '}Total: {total} customer(s) {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

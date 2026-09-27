"""Purge customer records whose retention period (retention_until) has expired.

Run after business hours or via Task Scheduler / cron. Only deletes
customers with status='closed' AND retention_until < today.

Exit codes:
    0  success (including zero records to purge)
    1  error
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import purge_expired
from amlkit.db import connect


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="Path to SQLite database (overrides AMLKIT_DB env var)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without deleting")
    args = parser.parse_args()

    try:
        db_path = args.db or os.environ.get("AMLKIT_DB")
        conn = connect(db_path) if db_path else connect()
    except Exception as exc:
        print(f"ERROR: cannot open database: {exc}", file=sys.stderr)
        return 1

    orgs = conn.execute("SELECT id, name FROM organizations WHERE status='active'").fetchall()
    total = 0
    disabled = False
    for org in orgs:
        result = purge_expired(conn, org["id"], dry_run=args.dry_run)
        if result.get("disabled"):
            disabled = True
            continue
        count = result["purged"]
        if count:
            label = "would purge" if args.dry_run else "purged"
            print(f"org {org['id']} ({org['name']}): {label} {count} record(s)")
        total += count

    if disabled:
        print("Purge disabled: set AMLKIT_PURGE_ENABLED=true to enable (dry run is always allowed).")
    else:
        print(f"{'[dry-run] ' if args.dry_run else ''}Total: {total} record(s) purged")
    return 0


if __name__ == "__main__":
    sys.exit(main())

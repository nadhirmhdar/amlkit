"""Purge customer records whose 8-year retention period has expired.

Run after business hours or via Task Scheduler / cron. Only deletes
customers with status='closed' AND retention_until < today.

Exit codes:
    0  success (including zero records to purge)
    1  error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import purge_expired
from amlkit.db import connect


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/aml.db", help="Path to SQLite database")
    parser.add_argument("--dry-run", action="store_true", help="Preview without deleting")
    args = parser.parse_args()

    try:
        conn = connect(args.db)
    except Exception as exc:
        print(f"ERROR: cannot open database: {exc}", file=sys.stderr)
        return 1

    orgs = conn.execute("SELECT id, name FROM organizations WHERE is_active=1").fetchall()
    total = 0
    for org in orgs:
        result = purge_expired(conn, org["id"], dry_run=args.dry_run)
        count = result["purged"]
        if count:
            label = "would purge" if args.dry_run else "purged"
            print(f"org {org['id']} ({org.get('name', '?')}): {label} {count} record(s)")
        total += count

    print(f"{'[dry-run] ' if args.dry_run else ''}Total: {total} record(s) purged")
    return 0


if __name__ == "__main__":
    sys.exit(main())

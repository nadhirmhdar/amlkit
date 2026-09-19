#!/usr/bin/env python3
"""Export amlkit compliance data to BigQuery.

Usage:
    export GCP_PROJECT_ID=my-gcp-project
    export AMLKIT_DB=/path/to/aml.db          # or leave default
    python scripts/export_to_bigquery.py --org-id 1

    # All orgs:
    python scripts/export_to_bigquery.py --all-orgs

    # Custom dataset:
    python scripts/export_to_bigquery.py --org-id 1 --dataset my_dataset
"""

from __future__ import annotations

import argparse
import os
import sys

# Ensure the repo root is on the path when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from amlkit.db import connect
from amlkit.reporting.bigquery import BQ_DATASET, GCP_PROJECT_ID, export_all


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--org-id", type=int, metavar="ID",
                       help="Export data for a single organization ID")
    group.add_argument("--all-orgs", action="store_true",
                       help="Export data for every active organization")
    ap.add_argument("--project", default=GCP_PROJECT_ID,
                    help="GCP project ID (overrides GCP_PROJECT_ID env var)")
    ap.add_argument("--dataset", default=BQ_DATASET,
                    help=f"BigQuery dataset name (default: {BQ_DATASET})")
    ap.add_argument("--db", default=None,
                    help="Path to SQLite database (overrides AMLKIT_DB)")
    args = ap.parse_args()

    if not args.project:
        print("ERROR: GCP project ID is required. "
              "Set GCP_PROJECT_ID or pass --project.", file=sys.stderr)
        return 1

    db_path = args.db or os.environ.get("AMLKIT_DB")
    conn = connect(db_path) if db_path else connect()

    if args.all_orgs:
        orgs = conn.execute(
            "SELECT id, name FROM organizations WHERE status = 'active'"
        ).fetchall()
        if not orgs:
            print("No active organizations found.")
            return 0
        org_ids = [(row[0], row[1]) for row in orgs]
    else:
        row = conn.execute(
            "SELECT id, name FROM organizations WHERE id = ?", (args.org_id,)
        ).fetchone()
        if not row:
            print(f"ERROR: Organization {args.org_id} not found.", file=sys.stderr)
            return 1
        org_ids = [(row[0], row[1])]

    total_errors = 0
    for org_id, org_name in org_ids:
        print(f"\nExporting org {org_id} ({org_name}) → "
              f"{args.project}.{args.dataset}")
        try:
            counts = export_all(conn, org_id, project=args.project,
                                dataset_id=args.dataset)
            for table, n in counts.items():
                print(f"  {table:<30} {n:>6} rows")
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            total_errors += 1

    if total_errors:
        print(f"\n{total_errors} org(s) had errors.", file=sys.stderr)
        return 1

    print("\nExport complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

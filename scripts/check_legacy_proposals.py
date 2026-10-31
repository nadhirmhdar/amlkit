"""Report pending four-eyes proposals that still rely on the name-comparison fallback (L-27).

`cases.review.confirm_disposition` compares operator ids, but falls back to
comparing display names when the staged proposal has `operator_id IS NULL`
(rows written before that column existed). Run this against the production
database copy; when it reports 0, the fallback in `cases/review.py` can be
deleted.

    python scripts/check_legacy_proposals.py

Exit codes:
    0  no pending proposal depends on the fallback
    1  one or more pending proposals have operator_id IS NULL
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect  # noqa: E402


def count_legacy_pending(conn) -> list[dict]:
    """Alerts awaiting confirmation whose latest 'propose' row has no operator_id."""
    rows = conn.execute(
        """SELECT a.id AS alert_id, a.org_id, r.operator, r.created_at
           FROM alerts a
           JOIN alert_reviews r ON r.alert_id = a.id AND r.org_id = a.org_id
           WHERE a.status = 'pending_review'
             AND r.action = 'propose'
             AND r.operator_id IS NULL
             AND r.id = (SELECT MAX(id) FROM alert_reviews
                         WHERE alert_id = a.id AND org_id = a.org_id AND action = 'propose')
           ORDER BY a.id"""
    ).fetchall()
    return [dict(r) for r in rows]


def main() -> int:
    conn = connect()
    legacy = count_legacy_pending(conn)
    print(f"Pending proposals with operator_id IS NULL: {len(legacy)}")
    for r in legacy:
        print(f"  alert {r['alert_id']} (org {r['org_id']}) proposed by {r['operator']!r} at {r['created_at']}")
    return 1 if legacy else 0


if __name__ == "__main__":
    sys.exit(main())

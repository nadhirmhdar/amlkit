"""Daily list refresh and re-screen. THIS is the 24-hour compliance control.

EOCN requires list updates to be implemented within 24 hours. That obligation
has two halves, and only one of them is downloading a file:

    1. refresh the sanctions lists
    2. re-screen the existing customer book against them

A refreshed list that nobody has been screened against provides no protection,
so both run here, in that order, as one operation.

This deliberately does NOT run in GitHub Actions. Customer data lives locally
and must not leave the machine -- CI has nothing to re-screen. The GitHub
workflow is a canary for upstream source drift, not this control.

Schedule it with Windows Task Scheduler:

    schtasks /create /tn "AML list refresh" /tr ^
      "\"C:\\path\\to\\AML\\.venv\\Scripts\\python.exe\" \"C:\\path\\to\\AML\\scripts\\refresh.py\"" ^
      /sc daily /st 06:00

Exit codes:
    0  all mandatory lists fresh, re-screen completed
    1  a source failed, or a mandatory list is stale beyond 24 hours
    2  new alerts raised - requires MLRO review
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import audit, connect  # noqa: E402
from amlkit.ingest.base import AdapterError  # noqa: E402
from amlkit.ingest.loader import load, staleness_report  # noqa: E402
from amlkit.ingest.opensanctions import (  # noqa: E402
    uae_local_terrorists,
    un_sanctions,
)
from amlkit.match.engine import rescreen_all  # noqa: E402

# Mandatory under UAE law. Failure to refresh any of these is a compliance
# breach, not a warning.
MANDATORY_SOURCES = [uae_local_terrorists, un_sanctions]


def main() -> int:
    conn = connect()
    failures: list[str] = []

    print("=" * 68)
    print("AML list refresh")
    print("=" * 68)

    for factory in MANDATORY_SOURCES:
        adapter = factory()
        try:
            result = load(conn, adapter, actor="scheduled-refresh")
            print(f"  OK    {result}")
        except AdapterError as exc:
            # Loud by design. A silently-failing feed shows green while
            # coverage has lapsed, which is the exact failure the 24-hour rule
            # exists to prevent.
            print(f"  FAIL  {adapter.key}: {exc}", file=sys.stderr)
            failures.append(adapter.key)
            audit(conn, "scheduled-refresh", "dataset.refresh_failed",
                  "dataset", adapter.key, {"error": str(exc)})
            conn.commit()

    print()
    print("Staleness against the 24-hour rule:")
    breaches = []
    for row in staleness_report(conn):
        status = "BREACH" if row["breach"] else "ok"
        mand = "mandatory" if row["mandatory"] else "optional "
        print(
            f"  [{status:6}] {row['key']:24} {mand}  "
            f"{row['entities']:>6} entities  {row['hours_since_refresh']}h old"
        )
        if row["breach"]:
            breaches.append(row["key"])

    print()
    print("Re-screening customer book against refreshed lists...")
    outcome = rescreen_all(conn, actor="scheduled-refresh")
    print(f"  screened {outcome['screened']} name(s), {outcome['alerts']} alert(s) raised")

    open_alerts = conn.execute(
        "SELECT COUNT(*) c FROM alerts WHERE status='open'"
    ).fetchone()["c"]
    print(f"  {open_alerts} alert(s) awaiting MLRO disposition")

    conn.commit()

    print()
    if failures or breaches:
        print("RESULT: FAILED - mandatory coverage is not current.", file=sys.stderr)
        if failures:
            print(f"  sources failed : {failures}", file=sys.stderr)
        if breaches:
            print(f"  stale >24h     : {breaches}", file=sys.stderr)
        return 1

    if open_alerts:
        print(f"RESULT: {open_alerts} alert(s) require review.")
        return 2

    print("RESULT: OK - all mandatory lists current, no open alerts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

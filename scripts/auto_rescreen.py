"""23-hour auto-rescreening script.

Designed to run immediately after the API's own sanctions-list refresh
completes -- either triggered by Windows Task Scheduler or called from
a post-refresh hook. Safe to call on its own: it checks whether the
lists have been refreshed recently (within REFRESH_GRACE_HOURS) and, if
not, runs a full refresh first before rescreening.

Exit codes:
    0  lists current, all customers rescreened, no new alerts
    1  a mandatory list refresh failed, or lists are stale beyond 24h
    2  rescreening raised new alerts -- MLRO review required
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import audit, connect, utcnow  # noqa: E402
from amlkit.ingest.base import AdapterError  # noqa: E402
from amlkit.ingest.loader import load, staleness_report  # noqa: E402
from amlkit.ingest.eocn import uae_local_terrorists  # noqa: E402
from amlkit.ingest.cia import cia_world_leaders  # noqa: E402
from amlkit.ingest.un import UNSanctionsAdapter  # noqa: E402
from amlkit.ingest.ofac import OFACSDNAdapter  # noqa: E402
from amlkit.ingest.eu import EUSanctionsAdapter  # noqa: E402
from amlkit.ingest.uk import UKSanctionsAdapter  # noqa: E402
from amlkit.match.engine import rescreen_all  # noqa: E402
from amlkit.cases.manager import reassess_risk  # noqa: E402

REFRESH_SOURCES = [
    uae_local_terrorists,
    UNSanctionsAdapter,
    OFACSDNAdapter,
    EUSanctionsAdapter,
    UKSanctionsAdapter,
    cia_world_leaders,
]

# If all mandatory lists were refreshed within this window, skip the refresh
# step and go straight to rescreening. Keeps the script fast when called
# immediately after an API-triggered refresh.
REFRESH_GRACE_HOURS = 1


def _lists_are_current(conn) -> bool:
    """Return True if every mandatory list was refreshed within REFRESH_GRACE_HOURS."""
    report = staleness_report(conn)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=REFRESH_GRACE_HOURS)
    for row in report:
        if not row["mandatory"]:
            continue
        last = row.get("last_refresh")
        if not last:
            return False
        try:
            refreshed_at = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if refreshed_at.tzinfo is None:
                refreshed_at = refreshed_at.replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        if refreshed_at < cutoff:
            return False
    return True


def _refresh(conn) -> list[str]:
    """Refresh all mandatory sources. Returns a list of failed source keys."""
    failures: list[str] = []
    for factory in REFRESH_SOURCES:
        adapter = factory()
        try:
            result = load(conn, adapter, actor="auto-rescreen")
            print(f"  OK    {result}")
        except AdapterError as exc:
            print(f"  FAIL  {adapter.key}: {exc}", file=sys.stderr)
            if adapter.is_mandatory:
                failures.append(adapter.key)
            audit(conn, "auto-rescreen", "dataset.refresh_failed",
                  "dataset", adapter.key, {"error": str(exc)}, org_id=None)
            conn.commit()
    return failures


def main() -> int:
    conn = connect()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print("=" * 68)
    print(f"AML 23-hour auto-rescreen  [{now_str}]")
    print("=" * 68)

    # ----------------------------------------------------------------- refresh
    failures: list[str] = []
    if _lists_are_current(conn):
        print(f"Lists refreshed within last {REFRESH_GRACE_HOURS}h -- skipping refresh step.")
    else:
        print("Lists need refresh -- running now...")
        failures = _refresh(conn)

    # ---------------------------------------------------------------- staleness
    print()
    print("Staleness check:")
    breaches: list[str] = []
    for row in staleness_report(conn):
        status = "BREACH" if row["breach"] else "ok"
        mand = "mandatory" if row["mandatory"] else "optional "
        age = row["hours_since_refresh"]
        print(f"  [{status:6}] {row['key']:28} {mand}  {row['entities']:>6} entities  {age}h old")
        if row["breach"]:
            breaches.append(row["key"])

    if failures or breaches:
        print()
        print("RESULT: FAILED -- mandatory coverage not current.", file=sys.stderr)
        if failures:
            print(f"  sources failed: {failures}", file=sys.stderr)
        if breaches:
            print(f"  stale >24h    : {breaches}", file=sys.stderr)
        return 1

    # --------------------------------------------------------------- rescreen
    print()
    print("Rescreening all organizations...")
    orgs = conn.execute(
        "SELECT id, name FROM organizations WHERE status='active'"
    ).fetchall()

    total_screened = total_new_alerts = total_reassessed = 0
    failed_orgs: list[tuple[int, str, str]] = []  # (id, name, error)

    for org in orgs:
        try:
            # Note the timestamp so we can identify alerts created by THIS run.
            run_ts = utcnow()

            outcome = rescreen_all(conn, org["id"], actor="auto-rescreen")
            new = outcome["alerts"]
            print(
                f"  {org['name']:38}  screened {outcome['screened']:>4}  "
                f"new alerts {new}"
            )
            total_screened += outcome["screened"]
            total_new_alerts += new

            # Re-assess risk for any customer that just received a new alert.
            # Without this, a customer hitting a sanctions list between two runs
            # would have an open sanctions alert but still show the old rating.
            if new:
                query_ts = (datetime.fromisoformat(run_ts) - timedelta(seconds=1)).isoformat()
                new_alert_customers = conn.execute(
                    """SELECT DISTINCT s.customer_id
                       FROM alerts a
                       JOIN screenings s ON s.id = a.screening_id
                       WHERE a.org_id = ? AND a.created_at >= ?""",
                    (org["id"], query_ts),
                ).fetchall()
                for row in new_alert_customers:
                    updated = reassess_risk(
                        conn, row["customer_id"], org["id"], actor="auto-rescreen"
                    )
                    if updated:
                        total_reassessed += 1
                conn.commit()
        except Exception as exc:
            # Issue #259: Isolate per-org exceptions so one failing org doesn't
            # prevent others from rescreening.
            error_msg = f"{type(exc).__name__}: {exc}"
            print(
                f"  {org['name']:38}  FAILED: {error_msg}",
                file=sys.stderr
            )
            failed_orgs.append((org["id"], org["name"], error_msg))
            # Log the failure and continue to next org
            audit(
                conn, "auto-rescreen", "rescreen.org_failed",
                "organization", str(org["id"]),
                {"org_name": org["name"], "error": error_msg},
                org_id=org["id"]
            )
            conn.commit()

    print(
        f"\n  total: {total_screened} screened, {total_new_alerts} new alert(s), "
        f"{total_reassessed} risk re-assessment(s) across {len(orgs)} org(s)"
    )

    if failed_orgs:
        print(f"\n  {len(failed_orgs)} org(s) failed:", file=sys.stderr)
        for org_id, org_name, error in failed_orgs:
            print(f"    - {org_name} (id={org_id}): {error}", file=sys.stderr)

    open_alerts = conn.execute(
        "SELECT COUNT(*) c FROM alerts WHERE status='open'"
    ).fetchone()["c"]
    print(f"  {open_alerts} alert(s) awaiting MLRO disposition across all organizations")

    audit(
        conn, "auto-rescreen", "rescreen.completed", None, None,
        {
            "orgs": len(orgs),
            "screened": total_screened,
            "new_alerts": total_new_alerts,
            "failed_orgs": len(failed_orgs),
        },
        org_id=None,
    )
    conn.commit()

    print()
    if failed_orgs:
        print(f"RESULT: FAILED -- {len(failed_orgs)} org(s) could not be rescreened.", file=sys.stderr)
        return 1
    if total_new_alerts or open_alerts:
        print(f"RESULT: {open_alerts} open alert(s) require MLRO review.")
        return 2

    print("RESULT: OK -- all lists current, rescreen complete, no open alerts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

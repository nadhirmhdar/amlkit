"""System-level values for the /admin/ops page and operational log lines.

Everything here is process-wide or shared reference data (dataset freshness,
replica state, build version) -- nothing tenant-owned. Tenant-scoped figures
(alerts, freeze obligations, CNMR drafts, the org's own audit times) live in
`queries.ops_org_figures`, which takes an `org_id`.

The two `log_*` helpers emit one structured line per scheduler run so
log-based metrics (scripts/monitoring/) have a stable source. Fields travel in
`extra_fields`, which `logging_config.StructuredFormatter` merges into the
JSON payload (`jsonPayload.overdue_count` etc.).
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import subprocess
from typing import Any

log = logging.getLogger("amlkit.ops")

# Message prefixes the Cloud Logging metrics in scripts/monitoring/ match on.
FREEZE_CHECK_MESSAGE = "freeze_obligation_check"
REFRESH_MESSAGE = "sanctions_refresh"


def app_version() -> str:
    """Git SHA of the deployed build (AMLKIT_GIT_SHA, set by the deploy)."""
    return os.environ.get("AMLKIT_GIT_SHA", "").strip() or "dev"


def log_freeze_check_run(result: dict[str, Any]) -> None:
    """One line per /system/check-freeze-obligations run."""
    try:
        overdue = int(result.get("overdue", 0))
        orgs = int(result.get("orgs_checked", 0))
        log.info(
            "%s overdue_count=%d org_count=%d", FREEZE_CHECK_MESSAGE, overdue, orgs,
            extra={"extra_fields": {
                "overdue_count": overdue,
                "org_count": orgs,
                "newly_notified": int(result.get("newly_notified", 0)),
                "failure_count": len(result.get("failures") or []),
            }},
        )
    except Exception:  # observability must never fail the run it describes
        log.exception("could not log freeze check run")


def dataset_entity_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """{dataset key: entity_count} -- shared reference data."""
    return {r["key"]: int(r["entity_count"] or 0)
            for r in conn.execute("SELECT key, entity_count FROM datasets ORDER BY key")}


def log_refresh_run(conn: sqlite3.Connection, result: dict[str, Any], duration_s: float) -> None:
    """One line per /system/refresh run: per-dataset counts and duration."""
    try:
        counts = dataset_entity_counts(conn)
        log.info(
            "%s duration_seconds=%.1f datasets=%d", REFRESH_MESSAGE, duration_s, len(counts),
            extra={"extra_fields": {
                "duration_seconds": round(duration_s, 1),
                "dataset_counts": counts,
                "failure_count": len(result.get("failures") or []),
                "mandatory_failure_count": len(result.get("mandatory_failures") or []),
                "new_alerts": int(result.get("new_alerts", 0)),
                "orgs_screened": int(result.get("orgs_screened", 0)),
            }},
        )
    except Exception:
        log.exception("could not log refresh run")


def _litestream_position() -> str:
    """Best-effort litestream-reported replica position; "unknown" if the
    binary, its control socket or the command is unavailable. Read-only
    (`litestream status`); never raises."""
    from . import replication

    try:
        exe = shutil.which("litestream")
        socket = os.environ.get("AMLKIT_LITESTREAM_SOCKET", "").strip() or replication.DEFAULT_SOCKET
        if exe is None or not os.path.exists(socket):
            return "unknown"
        proc = subprocess.run([exe, "status", "-socket", socket],
                              capture_output=True, text=True, timeout=5)
        out = " ".join((proc.stdout or "").split())
        return out[:300] if proc.returncode == 0 and out else "unknown"
    except Exception:
        return "unknown"


def replica_status() -> dict[str, Any]:
    from . import replication

    last = replication.last_successful_sync()
    age_hours = None
    if last:
        from datetime import datetime, timezone
        age_hours = round((datetime.now(timezone.utc) - datetime.fromisoformat(last["at"]))
                          .total_seconds() / 3600, 2)
    return {
        "configured": bool(os.environ.get("LITESTREAM_REPLICA_URL", "").strip()),
        "sync_enabled": replication.sync_enabled(),
        "last_sync_at": last["at"] if last else None,
        "last_sync_reason": last["reason"] if last else None,
        "last_sync_age_hours": age_hours,
        "position": _litestream_position(),
    }


def last_shared_refresh(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Latest successful dataset load and who ran it. Shared reference data
    (audit rows with org_id NULL); when an operator triggered the refresh the
    shared rows carry the system actor, never a tenant's operator name."""
    row = conn.execute(
        "SELECT ts, actor FROM audit_log WHERE action='dataset.refresh' AND org_id IS NULL "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return {"ts": row["ts"], "actor": row["actor"]} if row else None


def system_status(conn: sqlite3.Connection) -> dict[str, Any]:
    from .ingest.loader import staleness_report

    datasets = staleness_report(conn)
    for ds in datasets:
        h = ds["hours_since_refresh"]
        ds["stale"] = h is None or h > ds["max_age_hours"]
    return {
        "version": app_version(),
        "datasets": datasets,
        "stale_count": sum(1 for d in datasets if d["stale"]),
        "last_refresh": last_shared_refresh(conn),
        "replica": replica_status(),
    }

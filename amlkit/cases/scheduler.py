"""Scheduler operations for sanctions refresh and staleness monitoring.

Extracted from api/app.py to keep routes thin. These functions are called by:
- POST /system/refresh (Cloud Scheduler HTTP endpoint)
- POST /admin/refresh (manual MLRO trigger)
- In-process APScheduler background task (_run_scheduled_refresh)
"""

from __future__ import annotations

import logging
import sqlite3

from ..db import retry_on_lock

log = logging.getLogger("amlkit.scheduler")


@retry_on_lock(max_retries=3, base_delay=0.5)
def run_sanctions_refresh(conn: sqlite3.Connection, actor: str) -> dict:
    """Load every mandatory sanctions source and re-screen every active org.

    Single source of truth for "what a refresh actually does" -- previously
    the interactive /admin/refresh button and the automated scheduler path
    silently drifted apart: the manual button loaded six sources (including
    UK and the CIA World Leaders PEP list), the automated path only loaded
    four. An automated refresh that covers less than the button a human
    would click is exactly the kind of gap that isn't visible until an
    examiner asks why UK-sanctioned entities weren't being screened against.
    Both routes, and the scheduler, now call this one function.
    """
    from ..ingest.base import AdapterError
    from ..ingest.loader import load
    from ..ingest.eocn import uae_local_terrorists
    from ..ingest.cia import cia_world_leaders
    from ..ingest.un import UNSanctionsAdapter
    from ..ingest.ofac import OFACSDNAdapter
    from ..ingest.eu import EUSanctionsAdapter
    from ..ingest.uk import UKSanctionsAdapter
    from ..ingest.fatf import FATFAdapter, load_fatf_data
    from ..ingest.interpol import InterpolRedNoticeAdapter
    from ..match.engine import rescreen_all
    from ..match.cache import invalidate as invalidate_cache
    from ..db import audit, record_dataset_error, upsert_dataset

    loaded: list[str] = []
    failures: list[str] = []
    mandatory_failures: list[str] = []
    for factory in [uae_local_terrorists, UNSanctionsAdapter, OFACSDNAdapter,
                     EUSanctionsAdapter, UKSanctionsAdapter, cia_world_leaders,
                     FATFAdapter, InterpolRedNoticeAdapter]:
        adapter = factory()
        try:
            result = load(conn, adapter, actor=actor)
            loaded.append(f"{adapter.title}: {result.entities} entities")
        except AdapterError as exc:
            msg = f"{adapter.title}: {exc}"
            failures.append(msg)
            if adapter.is_mandatory:
                mandatory_failures.append(msg)
            # A source that has never once loaded successfully has no dataset
            # row yet (load() only upserts one on success), so record_dataset_error
            # below would silently no-op and the compliance dashboard would show
            # nothing at all for it instead of a failed/breach row. Ensure the
            # row exists first, exactly as a successful load() would have.
            upsert_dataset(conn, key=adapter.key, title=adapter.title,
                            publisher=adapter.publisher, source_url=adapter.source_url,
                            licence=adapter.licence, is_mandatory=adapter.is_mandatory)
            # Persist onto the dataset row so /admin/compliance shows which
            # source failed and why, not just a transient audit-log line.
            record_dataset_error(conn, adapter.key, str(exc))
            audit(conn, actor, "dataset.refresh_failed", "dataset", adapter.key,
                  {"error": str(exc)}, org_id=None)
    conn.commit()

    # Populate denormalized fatf_countries table from loaded entities
    try:
        load_fatf_data(conn)
        log.info("FATF country risk table populated from live data")
    except Exception as exc:
        log.exception("Failed to populate fatf_countries table: %s", exc)

    # Invalidate the name_tokens cache after loading new data
    invalidate_cache()
    log.info("Sanctions cache invalidated after refresh")

    total_alerts = 0
    screened_orgs = 0
    rescreen_failures: list[str] = []
    orgs = conn.execute("SELECT id, name FROM organizations WHERE status='active'").fetchall()
    for org in orgs:
        try:
            outcome = rescreen_all(conn, org["id"], actor=actor)
            total_alerts += outcome["alerts"]
            screened_orgs += 1
        except Exception as exc:
            log.exception("rescreen_all failed for org %s (%s): %s", org["id"], org["name"], exc)
            rescreen_failures.append(f"{org['name']}: {exc}")
    conn.commit()

    return {
        "loaded": loaded,
        "failures": failures,
        "mandatory_failures": mandatory_failures,
        "rescreen_failures": rescreen_failures,
        "orgs_screened": screened_orgs,
        "new_alerts": total_alerts,
    }


def _default_adapters():
    from ..ingest.eocn import uae_local_terrorists
    from ..ingest.cia import cia_world_leaders
    from ..ingest.un import UNSanctionsAdapter
    from ..ingest.ofac import OFACSDNAdapter
    from ..ingest.eu import EUSanctionsAdapter
    from ..ingest.uk import UKSanctionsAdapter
    from ..ingest.interpol import InterpolRedNoticeAdapter
    return [uae_local_terrorists, UNSanctionsAdapter, OFACSDNAdapter,
            EUSanctionsAdapter, UKSanctionsAdapter, cia_world_leaders,
            InterpolRedNoticeAdapter]


def refresh_with_progress(conn, actor, adapters=None):
    """Generator that yields progress dicts as each sanctions adapter completes.

    Used by the SSE endpoint to stream per-list progress to the browser.
    """
    from ..ingest.base import AdapterError
    from ..ingest.loader import load
    from ..match.engine import rescreen_all
    from ..match.cache import invalidate as invalidate_cache
    from ..db import audit, record_dataset_error, upsert_dataset

    if adapters is None:
        adapters = _default_adapters()

    total = len(adapters)
    loaded = []
    failures = []

    for i, factory in enumerate(adapters):
        adapter = factory()
        try:
            result = load(conn, adapter, actor=actor)
            loaded.append(adapter.title)
            yield {
                "type": "adapter_done",
                "index": i + 1,
                "total": total,
                "title": adapter.title,
                "entities": result.entities,
            }
        except AdapterError as exc:
            failures.append(adapter.title)
            # See run_sanctions_refresh: without this, a source that has
            # never once loaded successfully has no dataset row yet, so
            # record_dataset_error below would silently no-op.
            upsert_dataset(conn, key=adapter.key, title=adapter.title,
                            publisher=adapter.publisher, source_url=adapter.source_url,
                            licence=adapter.licence, is_mandatory=adapter.is_mandatory)
            record_dataset_error(conn, adapter.key, str(exc))
            audit(conn, actor, "dataset.refresh_failed", "dataset", adapter.key,
                  {"error": str(exc)}, org_id=None)
            yield {
                "type": "adapter_error",
                "index": i + 1,
                "total": total,
                "title": adapter.title,
                "error": str(exc),
            }
    conn.commit()
    invalidate_cache()

    yield {"type": "rescreen_start"}

    total_alerts = 0
    orgs = conn.execute("SELECT id, name FROM organizations WHERE status='active'").fetchall()
    for org in orgs:
        try:
            outcome = rescreen_all(conn, org["id"], actor=actor)
            total_alerts += outcome["alerts"]
        except Exception as exc:
            log.exception("rescreen_all failed for org %s", org["id"])
    conn.commit()

    yield {
        "type": "complete",
        "loaded": loaded,
        "failures": failures,
        "new_alerts": total_alerts,
    }


def check_and_notify_staleness(conn: sqlite3.Connection) -> dict:
    """Check for stale mandatory datasets and send email alerts if needed.

    Only notifies once per staleness breach (tracked via staleness_notified_at)
    to avoid spam. Returns a summary of what was notified.
    """
    from ..ingest.loader import staleness_report
    from .. import mail
    from ..db import utcnow

    staleness = staleness_report(conn)
    breaches = [d for d in staleness if d["breach"] and d["mandatory"]]

    if not breaches:
        # Clear staleness_notified_at for any datasets that are now fresh
        conn.execute(
            "UPDATE datasets SET staleness_notified_at=NULL WHERE staleness_notified_at IS NOT NULL"
        )
        conn.commit()
        return {"breaches": 0, "notified": 0}

    # Find datasets that breached and haven't been notified yet
    needs_notification = []
    for d in breaches:
        row = conn.execute(
            "SELECT staleness_notified_at FROM datasets WHERE key=?", (d["key"],)
        ).fetchone()
        if row and row["staleness_notified_at"] is None:
            needs_notification.append(d)

    if not needs_notification:
        return {"breaches": len(breaches), "notified": 0}

    # Send per-org alerts to avoid cross-tenant MLRO email disclosure (#138)
    orgs = conn.execute(
        "SELECT id, name FROM organizations WHERE status='active'"
    ).fetchall()

    total_recipients = 0
    outcomes = []
    for org in orgs:
        org_mlro_emails = [
            r["email"] for r in conn.execute(
                """SELECT DISTINCT email FROM operators
                   WHERE org_id=? AND role='mlro' AND is_active=1
                     AND email IS NOT NULL""",
                (org["id"],),
            ).fetchall()
        ]
        if not org_mlro_emails:
            continue
        outcome = mail.send_staleness_alert(org_mlro_emails, needs_notification)
        outcomes.append(outcome)
        total_recipients += len(org_mlro_emails)

    if not total_recipients:
        log.warning("Staleness breach detected but no MLRO emails to notify")
        return {"breaches": len(breaches), "notified": 0}

    now = utcnow()
    for d in needs_notification:
        conn.execute(
            "UPDATE datasets SET staleness_notified_at=? WHERE key=?", (now, d["key"])
        )
    conn.commit()

    log.info("Staleness notification: %d datasets, %d MLROs across %d orgs",
             len(needs_notification), total_recipients, len(orgs))

    return {
        "breaches": len(breaches),
        "notified": len(needs_notification),
        "outcome": outcomes[0] if len(outcomes) == 1 else "SENT",
        "recipients": total_recipients,
    }

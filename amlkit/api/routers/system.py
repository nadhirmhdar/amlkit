"""Token-authenticated /system/* endpoints called by Cloud Scheduler and ops tooling.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations


from fastapi import Request
from fastapi.responses import JSONResponse

from ..deps import (
    bearer_ok,
    db_path,
)

import os

from ...cases.scheduler import check_and_notify_staleness, run_sanctions_refresh

from fastapi import APIRouter

from ..helpers import (
    log,
)

router = APIRouter()


# ---------------------------------------------------------------------- system/refresh (Cloud Scheduler endpoint)
@router.post("/system/refresh")
def system_refresh(request: Request):
    """HTTP endpoint for Cloud Scheduler to call automatically, on a
    schedule set in Cloud Scheduler (see .github/workflows/source-canary.yml's
    "Wire up Cloud Scheduler sanctions refresh" step) -- not
    once every 23 hours in-process, which cannot survive Cloud Run scaling
    the container to zero between calls.

    Protected by a bearer token stored in the SCHEDULER_SECRET environment
    variable. If the variable is not set the endpoint is disabled entirely
    (returns 403) to prevent accidental exposure on a fresh deploy.

    Runs SYNCHRONOUSLY rather than spawning a background thread. A prior
    version fired the refresh in a daemon thread and returned immediately --
    which meant Cloud Run's autoscaler, which only tracks in-flight HTTP
    requests, had no signal that work was still happening, and could freeze
    or tear down the instance mid-refresh with no error and no way to tell
    whether it had actually finished. Running inline means the instance is
    guaranteed to stay up for the request's duration (see the deploy
    script's --timeout, set generously above this refresh's expected
    duration), and the caller gets a real result back instead of a fire-
    and-forget acknowledgment.
    """
    secret = os.environ.get("SCHEDULER_SECRET", "").strip()
    if not secret:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "endpoint disabled — set SCHEDULER_SECRET"}, status_code=403)

    auth_header = request.headers.get("Authorization", "")
    if not bearer_ok(auth_header, secret):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    from ...db import connect
    from fastapi.responses import JSONResponse

    conn = None
    try:
        conn = connect(db_path())
        import time as _time
        _t0 = _time.perf_counter()
        result = run_sanctions_refresh(conn, actor="cloud-scheduler")
        from ... import ops
        ops.log_refresh_run(conn, result, _time.perf_counter() - _t0)

        # Check for staleness and notify MLROs if needed
        staleness_result = check_and_notify_staleness(conn)
        result["staleness_check"] = staleness_result
        try:
            from ...cases.applications import purge_expired
            result["applications_purged"] = purge_expired(conn, actor="cloud-scheduler")
        except Exception:  # retention clean-up must never fail the list refresh
            log.exception("applications purge failed")
    finally:
        if conn is not None:
            conn.close()
        # The refresh rewrites the lists and rescreens every customer: the
        # largest write of the day, and the one most likely to be followed by
        # an idle spell in which litestream may get little CPU. Wait
        # for the replica before answering Cloud Scheduler.
        from ...replication import sync_replica
        sync_replica(timeout=30, reason="sanctions refresh")

    # 500 on mandatory-source failure so Cloud Scheduler retries (it only
    # retries on non-2xx). 207 for non-mandatory partial failures leaves a
    # record without triggering unnecessary retries.
    if result["mandatory_failures"]:
        status_code = 500
    elif result["failures"] or result["rescreen_failures"]:
        status_code = 207
    else:
        status_code = 200
    return JSONResponse({"status": "complete", **result}, status_code=status_code)

@router.post("/system/check-freeze-obligations")
def system_check_freeze_obligations(request: Request):
    """HTTP endpoint for Cloud Scheduler (hourly) to flag TFS freeze
    obligations still pending execution after 24 hours.

    UAE TFS requires the freeze to be executed within 24 hours. The check
    (cases.manager.check_unexecuted_freeze_obligations) emails each org's
    MLRO, but before this endpoint its only caller was a Windows Task
    Scheduler script, so on Cloud Run nobody was ever alerted. See
    .github/workflows/source-canary.yml's "Wire up Cloud Scheduler freeze
    obligation check" step.

    Same auth model as /system/refresh: bearer token in SCHEDULER_SECRET
    (ADMIN_API_SECRET does not unlock it); disabled (403) when unset.
    Each overdue obligation is emailed once (overdue_notified_at), so hourly
    calls do not repeat the alert.
    """
    secret = os.environ.get("SCHEDULER_SECRET", "").strip()
    if not secret:
        return JSONResponse({"error": "endpoint disabled — set SCHEDULER_SECRET"}, status_code=403)

    auth_header = request.headers.get("Authorization", "")
    if not bearer_ok(auth_header, secret):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    from ...db import connect
    from ...cases.scheduler import run_freeze_obligation_check

    conn = None
    try:
        conn = connect(db_path())
        result = run_freeze_obligation_check(conn)
        from ... import ops
        ops.log_freeze_check_run(result)
    except Exception as exc:
        log.exception("freeze obligation check failed")
        return JSONResponse({"status": "error", "error": str(exc)}, status_code=500)
    finally:
        if conn is not None:
            conn.close()

    if result["newly_notified"]:
        # The overdue_notified_at marks are the only record that an alert
        # went out; get them to the replica before answering.
        from ...replication import sync_replica
        sync_replica(timeout=30, reason="freeze obligation check")

    # 500 when any org's check failed so Cloud Scheduler retries (it only
    # retries on non-2xx); orgs already alerted are no-ops on the retry
    # thanks to overdue_notified_at.
    status_code = 500 if result["failures"] else 200
    return JSONResponse({"status": "complete", **result}, status_code=status_code)

@router.post("/system/create-operator")
async def system_create_operator(request: Request):
    """Provision an operator without a browser session."""
    secret = os.environ.get("ADMIN_API_SECRET", "").strip()
    if not secret:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "endpoint disabled — set ADMIN_API_SECRET"}, status_code=403)

    auth_header = request.headers.get("Authorization", "")
    if not bearer_ok(auth_header, secret):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    from fastapi.responses import JSONResponse
    from ...db import connect
    from ...cases.operators import provision_operator

    body = await request.json()
    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    role = body.get("role") or "officer"
    org_slug = (body.get("org_slug") or "").strip()

    conn = connect(db_path())
    try:
        result = provision_operator(conn, name, email, password, role, org_slug, actor="system")
        return JSONResponse({
            "status": "created",
            "operator_id": result["operator_id"],
            "organization": result["organization"],
            "email": result["email"],
            "role": result["role"],
        })
    except ValueError as exc:
        status = 404 if "no matching" in str(exc) else 409 if "already exists" in str(exc) else 400
        return JSONResponse({"error": str(exc)}, status_code=status)
    finally:
        conn.close()

@router.post("/system/super-admin")
async def system_super_admin(request: Request):
    """Grant or revoke super_admin on an existing operator without a browser
    session.

    Out-of-band by design, same as /system/create-operator: this is the only
    way to set the flag anywhere in the app. No authenticated in-app route
    grants super_admin to anyone, including the caller themselves.
    """
    secret = os.environ.get("ADMIN_API_SECRET", "").strip()
    if not secret:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "endpoint disabled — set ADMIN_API_SECRET"}, status_code=403)

    auth_header = request.headers.get("Authorization", "")
    if not bearer_ok(auth_header, secret):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    from fastapi.responses import JSONResponse
    from ...db import connect
    from ...cases.operators import set_super_admin

    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    grant = body.get("grant", True)

    conn = connect(db_path())
    try:
        result = set_super_admin(conn, email, bool(grant), actor="system")
        return JSONResponse({
            "status": "updated",
            "operator_id": result["operator_id"],
            "organization": result["organization"],
            "email": result["email"],
            "role": result["role"],
            "super_admin": result["super_admin"],
        })
    except ValueError as exc:
        status = 404 if "no matching" in str(exc) else 400
        return JSONResponse({"error": str(exc)}, status_code=status)
    finally:
        conn.close()

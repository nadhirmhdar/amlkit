"""Admin operations: ops status, sanctions refresh, rule configuration.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

from typing import Annotated

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import queries
from ..limits import limiter
from ..deps import (
    current_session,
    require_csrf,
    require_role,
    require_session,
)


from ...cases.scheduler import run_sanctions_refresh

from fastapi import APIRouter

from ..helpers import (
    DB,
    _fmt_amount,
    back,
    log,
    render,
)

router = APIRouter()


@router.get("/admin/ops", response_class=HTMLResponse)
def ops_status_view(request: Request, db: DB):
    """Operational status for the MLRO: data freshness, replica, queues, version."""
    try:
        session = require_session(request, db)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/", err=str(exc))
    from ... import ops
    return render(request, "admin/ops.html", {
        "session": session,
        "system": ops.system_status(db),
        "org": queries.ops_org_figures(db, session.org_id),
    })

# ---------------------------------------------------------------------- sanctions refresh
@router.post("/admin/refresh")
@limiter.limit("10/minute")
def admin_refresh_sanctions(
    request: Request, db: DB,
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    result = run_sanctions_refresh(db, actor=session.operator_name, org_id=session.org_id)

    if result["failures"]:
        return back("/admin", err="Refresh failed for: " + "; ".join(result["failures"]))

    msg = "Sanctions lists refreshed. " + "; ".join(result["loaded"])
    if result["new_alerts"]:
        msg += f" {result['new_alerts']} new alert(s) raised — check Alerts."
    return back("/admin", msg=msg)

@router.get("/admin/refresh-stream")
def admin_refresh_stream(request: Request, db: DB):
    """SSE endpoint that streams per-list sanctions refresh progress."""
    from fastapi.responses import StreamingResponse
    import json as _json

    try:
        session = require_session(request, db)
        require_role(session, "mlro")
    except PermissionError:
        return StreamingResponse(
            iter([f"data: {_json.dumps({'type': 'error', 'error': 'unauthorized'})}\n\n"]),
            media_type="text/event-stream",
        )

    from ...cases.scheduler import refresh_with_progress

    def event_stream():
        for event in refresh_with_progress(db, actor=session.operator_name, org_id=session.org_id):
            yield f"data: {_json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

# ---------------------------------------------------------------------- KYT rule config (Phase 4 enhancement, Step 8)
@router.get("/admin/rule-config", response_class=HTMLResponse)
def admin_rule_config_get(request: Request, db: DB):
    """Show KYT rule configuration form."""
    try:
        session = require_session(request, db)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/admin", err=str(exc))

    from ...screening.kyt import get_rule_config

    from ...screening.kyt import LARGE_CASH_THRESHOLD_AED

    config = get_rule_config(db, session.org_id)
    threshold = config["large_cash_threshold_aed"]
    return render(request, "admin/rule-config.html", {
        "session": session,
        "large_cash_threshold_aed": _fmt_amount(threshold).replace(",", ""),
        "large_cash_threshold_display": _fmt_amount(threshold),
        "large_cash_default_display": _fmt_amount(LARGE_CASH_THRESHOLD_AED),
        "threshold_above_default": threshold > LARGE_CASH_THRESHOLD_AED,
        "structuring_window_days": config["structuring_window_days"],
        "velocity_window_hours": config["velocity_window_hours"],
        "velocity_max_count": config["velocity_max_count"],
        "high_risk_countries": ", ".join(config["high_risk_countries"]),
    })

@router.post("/admin/rule-config")
@limiter.limit("10/minute")
def admin_rule_config_post(
    request: Request, db: DB,
    large_cash_threshold_aed: Annotated[str, Form()] = "",
    structuring_window_days: Annotated[str, Form()] = "",
    velocity_window_hours: Annotated[str, Form()] = "",
    velocity_max_count: Annotated[str, Form()] = "",
    high_risk_countries: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    """Update KYT rule configuration."""
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    from ...screening.kyt import save_rule_config

    from ...screening.kyt import LARGE_CASH_THRESHOLD_AED

    config_update = {}
    try:
        for key, raw, kind, label in (
            ("large_cash_threshold_aed", large_cash_threshold_aed, float, "Large cash threshold"),
            ("structuring_window_days", structuring_window_days, int, "Structuring window"),
            ("velocity_window_hours", velocity_window_hours, int, "Velocity window"),
            ("velocity_max_count", velocity_max_count, int, "Velocity max count"),
        ):
            raw = raw.strip().replace(",", "")
            if not raw:
                continue
            try:
                config_update[key] = kind(raw)
            except ValueError:
                return back("/admin/rule-config", err=(
                    f"{label} must be a "
                    f"{'number' if kind is float else 'whole number'} (for example "
                    f"{'55,000' if kind is float else '7'}); '{raw[:40]}' is not valid."))
        if high_risk_countries:
            config_update["high_risk_countries"] = [
                c.strip().upper() for c in high_risk_countries.split(",") if c.strip()
            ]

        save_rule_config(db, session.org_id, config_update, actor=session.operator_name)
        db.commit()
        msg = "Rule configuration updated successfully."
        if config_update.get("large_cash_threshold_aed", 0) > LARGE_CASH_THRESHOLD_AED:
            msg += (f" Warning: the large cash threshold is now "
                    f"{_fmt_amount(config_update['large_cash_threshold_aed'])} AED, above the "
                    f"default of {_fmt_amount(LARGE_CASH_THRESHOLD_AED)} AED. Cash transactions "
                    "between the two will no longer raise a large-cash alert.")
        return back("/admin/rule-config", msg=msg)
    except ValueError as exc:
        return back("/admin/rule-config", err=str(exc))
    except Exception as exc:
        log.exception("Failed to save rule config: %s", exc)
        return back("/admin/rule-config", err=f"Failed to save configuration: {exc}")

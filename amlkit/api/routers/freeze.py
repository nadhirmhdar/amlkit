"""Freeze obligations (UN/local list freeze workflow).

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.datastructures import FormData

from ... import queries
from ..deps import (
    require_csrf,
    require_session,
)



from fastapi import APIRouter

from ..helpers import (
    DB,
    _async_form,
    back,
    render,
)

router = APIRouter()


@router.get("/freeze-obligations", response_class=HTMLResponse)
def freeze_obligations_list_route(request: Request, db: DB):
    """List all freeze obligations for current org."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)

    filter_status = request.query_params.get("status", "all")
    obligations = queries.freeze_obligations_list(db, session.org_id, filter_status)
    stats = queries.freeze_obligations_stats(db, session.org_id)

    return render(request, "freeze_obligations.html", {
        "session": session,
        "obligations": obligations,
        "filter_status": filter_status,
        "stats": stats,
    })

@router.get("/freeze-obligations/{freeze_id}", response_class=HTMLResponse)
def freeze_obligation_detail_route(request: Request, db: DB, freeze_id: int):
    """Show freeze obligation details with full lifecycle timeline."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)

    obligation = queries.freeze_obligation_detail(db, session.org_id, freeze_id)
    if not obligation:
        return back("/freeze-obligations", err="Freeze obligation not found")

    can_execute = obligation["status"] == "pending_execution"
    # Once a CNMR draft is linked, the page links to it instead of offering
    # to draft another (file_ffr_report would just return the same draft).
    can_file_ffr = (obligation["status"] == "executed_pending_report"
                    and not obligation["report_id"])
    can_resolve = obligation["status"] in ["executed_pending_report", "reported"]
    
    return render(request, "freeze_obligation_detail.html", {
        "session": session,
        "obligation": obligation,
        "can_execute": can_execute,
        "can_file_ffr": can_file_ffr,
        "can_resolve": can_resolve,
    })

@router.post("/freeze-obligations/{freeze_id}/execute")
def freeze_obligation_execute(request: Request, db: DB, freeze_id: int, form: Annotated[FormData, Depends(_async_form)]):
    """Execute freeze obligation - mark as executed with assets frozen."""
    try:
        session = require_session(request, db)
        csrf_token = form.get("csrf_token", "")
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(f"/freeze-obligations/{freeze_id}", err=str(exc))

    if session.operator_role != "mlro":
        return back(f"/freeze-obligations/{freeze_id}", err="Execute freeze requires MLRO role")

    from ...cases import freeze as freeze_ops, manager
    assets_frozen = freeze_ops.parse_freeze_assets_from_form(form)

    try:
        manager.execute_freeze(
            db,
            freeze_id,
            org_id=session.org_id,
            executed_by=session.operator_name,
            assets_frozen=assets_frozen,
            notes=form.get("notes", "")
        )
    except ValueError as exc:
        return back(f"/freeze-obligations/{freeze_id}", err=str(exc))

    # A freeze record is evidence of a time-bound legal obligation: get it to
    # the replica now rather than whenever litestream next gets CPU.
    from ...replication import sync_replica
    sync_replica(timeout=10, reason="freeze executed")
    return back(f"/freeze-obligations/{freeze_id}", msg="Freeze executed successfully.")

@router.post("/freeze-obligations/{freeze_id}/file-ffr")
def freeze_obligation_file_ffr(request: Request, db: DB, freeze_id: int, form: Annotated[FormData, Depends(_async_form)]):
    """Create a CNMR (formerly FFR) report from a freeze obligation."""
    try:
        session = require_session(request, db)
        csrf_token = form.get("csrf_token", "")
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(f"/freeze-obligations/{freeze_id}", err=str(exc))

    if session.operator_role != "mlro":
        return back(f"/freeze-obligations/{freeze_id}", err="Filing a CNMR requires the MLRO role")

    from ...cases import freeze as freeze_ops
    from ...sanctions_scope import freeze_obligation_in_scope
    if not freeze_obligation_in_scope(db, freeze_id, session.org_id):
        return back(
            f"/freeze-obligations/{freeze_id}",
            err="A CNMR applies only to matches on the UN Security Council or UAE Local "
                "Terrorist lists. This match is on another list: consult your supervisory "
                "authority and consider an STR/SAR instead.",
        )
    reporter_name = form.get("reporter_name") or session.operator_name
    reporter_email = form.get("reporter_email", "")

    try:
        report_id = freeze_ops.file_ffr_report(
            db,
            freeze_id,
            session.org_id,
            reporter_name,
            reporter_email,
            session.operator_name
        )
    except ValueError as exc:
        return back(f"/freeze-obligations/{freeze_id}", err=str(exc))
    except Exception as exc:
        # Catch GoAMLValidationError for missing entity_reference
        from ...reporting.goaml import is_entity_reference_error
        if is_entity_reference_error(exc):
            return back(
                f"/freeze-obligations/{freeze_id}",
                err='Set your goAML entity reference under Admin → Organisation profile before filing. '
                    '<a href="/admin">Go to Admin</a>'
            )
        raise

    db.commit()
    return RedirectResponse(f"/reports/{report_id}", status_code=303)

@router.post("/freeze-obligations/{freeze_id}/resolve")
def freeze_obligation_resolve(request: Request, db: DB, freeze_id: int, form: Annotated[FormData, Depends(_async_form)]):
    """Resolve (close) freeze obligation."""
    try:
        session = require_session(request, db)
        csrf_token = form.get("csrf_token", "")
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(f"/freeze-obligations/{freeze_id}", err=str(exc))

    if session.operator_role != "mlro":
        return back(f"/freeze-obligations/{freeze_id}", err="Resolve freeze requires MLRO role")

    operator = session.operator_name

    resolution_reason = form.get("resolution_reason")
    authority_ref = form.get("authority_ref", "")
    notes = form.get("notes", "")
    
    from ...cases import manager
    try:
        manager.resolve_freeze_obligation(
            db,
            freeze_id,
            org_id=session.org_id,
            resolved_by=operator,
            resolution_reason=resolution_reason,
            authority_ref=authority_ref,
            notes=notes
        )
    except ValueError as exc:
        return back(f"/freeze-obligations/{freeze_id}", err=str(exc))

    return back(f"/freeze-obligations/{freeze_id}", msg="Obligation resolved successfully.")

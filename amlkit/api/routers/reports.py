"""STR/SAR reports (goAML export), signatures and narrative drafting.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

from typing import Annotated

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import queries
from ..limits import limiter
from ...cases.manager import (
    record_signature,
)
from ...db import utcnow
from ..deps import (
    client_ip,
    require_csrf,
    require_role,
    require_session,
)



from fastapi import APIRouter

from ..helpers import (
    DB,
    _audit_export,
    back,
    render,
)

router = APIRouter()


@router.post("/customers/{customer_id}/signatures")
def customer_add_signature(
    request: Request, db: DB, customer_id: int,
    purpose: Annotated[str, Form()],
    statement: Annotated[str, Form()],
    signer_name: Annotated[str, Form()],
    signer_role: Annotated[str, Form()] = "customer",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        record_signature(
            db, customer_id, session.org_id,
            purpose=purpose, statement=statement, signer_name=signer_name,
            signer_role=signer_role, ip_address=client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            actor=session.operator_name,
        )
    except (PermissionError, ValueError) as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    return back(f"/customers/{customer_id}", msg=f"Signed by {signer_name.strip()}.")

# ---------------------------------------------------------------------- regulatory reports
@router.get("/reports", response_class=HTMLResponse)
def reports_view(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    
    r_list = queries.report_list(db, session.org_id)
    return render(request, "reports.html", {"session": session, "reports": r_list}, db)

@router.get("/reports/new", response_class=HTMLResponse)
def report_new_view(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)

    from ...reporting.goaml import CREATABLE_REPORT_TYPES, REPORT_TYPE_LABELS
    customers = queries.customer_list(db, session.org_id)
    report_types = [(t, REPORT_TYPE_LABELS[t]) for t in CREATABLE_REPORT_TYPES]
    return render(request, "report_new.html", {
        "session": session, "customers": customers, "report_types": report_types,
    }, db)

@router.get("/reports/build", response_class=HTMLResponse)
def report_build_view(
    request: Request, db: DB,
    customer_id: int,
    report_type: str = "STR",
    report_id: int | None = None,
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    
    cust_data = queries.customer(db, customer_id, session.org_id)
    if not cust_data:
        return back("/reports", err="Customer not found")
        
    payload = {}
    if report_id:
        existing = queries.report(db, report_id, session.org_id)
        if existing:
            import json
            payload = json.loads(existing["payload"] or "{}")

    # Prefill the entity reference from the org's saved goAML reference; a
    # reference already stored on the draft wins. Empty (never a hard-coded
    # literal) when the org has not configured one.
    org_ref_row = db.execute(
        "SELECT goaml_entity_reference FROM organizations WHERE id = ?",
        (session.org_id,),
    ).fetchone()
    org_entity_reference = (org_ref_row["goaml_entity_reference"] or "") if org_ref_row else ""

    return render(request, "str_builder.html", {
        "org_entity_reference": org_entity_reference,
        "session": session,
        "customer": cust_data["customer"],
        "type": report_type,
        "payload": payload,
        "report_id": report_id,
    }, db)

@router.post("/reports")
def report_save(
    request: Request, db: DB,
    customer_id: Annotated[int, Form()],
    report_type: Annotated[str, Form()],
    reporting_entity_name: Annotated[str, Form()],
    entity_reference: Annotated[str, Form()],
    reporter_name: Annotated[str, Form()],
    reporter_email: Annotated[str, Form()],
    first_name: Annotated[str, Form()],
    last_name: Annotated[str, Form()] = "",
    nationality: Annotated[str, Form()] = "AE",
    birth_date: Annotated[str, Form()] = "",
    gender: Annotated[str, Form()] = "",
    id_type: Annotated[str, Form()] = "",
    id_number: Annotated[str, Form()] = "",
    amount: Annotated[str, Form()] = "",
    transaction_type: Annotated[str, Form()] = "",
    transaction_date: Annotated[str, Form()] = "",
    source_account: Annotated[str, Form()] = "",
    destination_account: Annotated[str, Form()] = "",
    reason_description: Annotated[str, Form()] = "",
    action_taken: Annotated[str, Form()] = "",
    evidence_pack_attached: Annotated[str, Form()] = "",
    report_id: Annotated[int, Form()] = None,
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back("/reports", err=str(exc))

    from ...cases.reports import save_report
    result = save_report(
        db, session.org_id, session.operator_name,
        customer_id, report_type, reporting_entity_name, entity_reference,
        reporter_name, reporter_email, first_name, last_name, nationality,
        birth_date, gender, id_type, id_number, amount, transaction_type,
        transaction_date, source_account, destination_account,
        reason_description, action_taken, evidence_pack_attached, report_id
    )

    if not result.success:
        return back("/reports", err=result.error)
    return back(f"/reports/{result.report_id}", msg="Draft report saved.")

@router.get("/reports/{report_id}", response_class=HTMLResponse)
def report_detail_view(request: Request, db: DB, report_id: int):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
        
    rep = queries.report(db, report_id, session.org_id)
    if not rep:
        return back("/reports", err="Report not found")
        
    import json
    payload = json.loads(rep["payload"] or "{}")

    return render(request, "report_detail.html", {
        "session": session,
        "report": rep,
        "payload": payload,
    }, db)

@router.post("/reports/{report_id}/submit")
def report_submit(request: Request, db: DB, report_id: int, csrf_token: Annotated[str, Form()] = ""):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        return back(f"/reports/{report_id}", err=str(exc))

    rep = queries.report(db, report_id, session.org_id)
    if not rep:
        return back("/reports", err="Report not found")

    # Already-finalized / invalid payload / missing required fields (t2, p17)
    from ...cases.manager import report_finalize_error
    problem = report_finalize_error(rep, db, session.org_id)
    if problem:
        return back(f"/reports/{report_id}", err=problem)

    now = utcnow()
    with db:
        db.execute(
            "UPDATE reports SET status='submitted', submitted_at=? WHERE id=? AND org_id=?",
            (now, report_id, session.org_id)
        )
        from ...db import audit
        audit(db, session.operator_name, "report.finalized", "report", report_id,
              {"report_type": rep["report_type"]}, org_id=session.org_id)
        # A finalised CNMR is what moves its freeze to 'reported'.
        from ...cases.freeze import mark_freeze_reported
        mark_freeze_reported(db, report_id, session.org_id, session.operator_name, now)
        if rep["customer_id"]:
            from ...cases.manager import recompute_retention
            recompute_retention(db, session.org_id, rep["customer_id"],
                                trigger="report.finalized", actor=session.operator_name)

    from ...replication import sync_replica
    sync_replica(timeout=10, reason="report finalized")
    return back(f"/reports/{report_id}",
               msg="Report finalized in groAML. It has not been sent to the UAE FIU; download the goAML XML and file it manually via the goAML portal.")

@router.get("/reports/{report_id}/export")
def report_export_xml(request: Request, db: DB, report_id: int):
    try:
        session = require_session(request, db)
    except PermissionError:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")

    rep = queries.report(db, report_id, session.org_id)
    if not rep:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Report not found")

    import json
    from ...reporting.goaml import (
        GoAMLValidationError, inject_reporting_entity, is_entity_reference_error,
        serialize_goaml_xml)

    payload = json.loads(rep["payload"] or "{}")

    # Inject org details into payload (follow-up to #231/#142)
    try:
        inject_reporting_entity(payload, db, session.org_id)
    except GoAMLValidationError as exc:
        if is_entity_reference_error(exc):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail='Set your goAML entity reference under Admin → Organisation profile before exporting. '
                       '<a href="/admin">Go to Admin</a>'
            )
        raise

    try:
        xml_content = serialize_goaml_xml(payload)
    except GoAMLValidationError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc))

    _audit_export(db, session, "export.goaml_xml", "report", report_id,
                  {"report_type": rep["report_type"]})
    from fastapi.responses import Response
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename=goAML_{rep['report_type']}_{report_id}.xml"
        }
    )

@router.post("/api/ai/draft-narrative")
@limiter.limit("5/minute")
def ai_draft_narrative(
    request: Request,
    db: DB,
    customer_id: int = Form(...),
    include_notes: bool = Form(False),
    csrf_token: Annotated[str, Form()] = "",
):
    """Return an AI-generated STR narrative draft for a customer.

    Form fields:
        customer_id   — required
        include_notes — bool, default false
        csrf_token    — CSRF synchronizer token

    Response (JSON):
        { "narrative": "...", "model": "gemini-...", "advisory": "..." }

    Returns 503 when GEMINI_API_KEY is unset or the Gemini call fails —
    the UI should show a degraded state, not an error page.
    """
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse

    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
    except PermissionError:
        raise HTTPException(status_code=401, detail="Unauthorized")

    case = queries.customer(db, customer_id, session.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Customer not found")

    from ...ai.gemini import GeminiUnavailable, draft_str_narrative, GEMINI_MODEL

    try:
        narrative = draft_str_narrative(
            customer=case["customer"],
            alerts=case["alerts"][:20],
            risk=case["risk"],
            notes=case["notes"][:5] if include_notes else [],
        )
    except GeminiUnavailable as exc:
        return JSONResponse(
            status_code=503,
            content={"error": str(exc), "advisory": "AI assistant unavailable."},
        )

    return JSONResponse({
        "narrative": narrative,
        "model": GEMINI_MODEL,
        "advisory": (
            "AI-GENERATED DRAFT — must be reviewed and approved by a qualified "
            "MLRO before use in any regulatory filing."
        ),
    })

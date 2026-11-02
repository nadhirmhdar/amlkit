"""Screening and transaction alerts: queue, disposition, review and CSV export.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

from typing import Annotated

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import queries
from ...cases.manager import (
    disposition_transaction_alert,
    record_transaction,
)
from ...cases.review import (
    REASON_CODES,
    ReviewError,
    assign_alert,
    bulk_dismiss_alerts,
    confirm_disposition,
    propose_disposition,
    review_history,
)
from ..deps import (
    CSRF_COOKIE,
    require_csrf,
    require_session,
)



from fastapi import APIRouter

from ..helpers import (
    DB,
    _audit_export,
    _csv_response,
    back,
    render,
    templates,
)

router = APIRouter()


@router.post("/customers/{customer_id}/transactions")
def customer_add_transaction(
    request: Request, db: DB, customer_id: int,
    direction: Annotated[str, Form()],
    method: Annotated[str, Form()],
    amount: Annotated[str, Form()],
    currency: Annotated[str, Form()] = "AED",
    amount_aed: Annotated[str, Form()] = "",
    counterparty_name: Annotated[str, Form()] = "",
    counterparty_country: Annotated[str, Form()] = "",
    occurred_at: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        amt = float(amount)
        aed = float(amount_aed) if amount_aed.strip() else None
        transaction_id, triggered = record_transaction(
            db, customer_id, session.org_id,
            direction=direction, method=method, amount=amt, currency=currency,
            amount_aed=aed, counterparty_name=counterparty_name.strip() or None,
            counterparty_country=counterparty_country.strip() or None,
            occurred_at=(occurred_at.strip() + "T00:00:00+00:00") if occurred_at.strip() else None,
            actor=session.operator_name,
        )
    except (PermissionError, ValueError) as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    note = (
        f"Transaction recorded. {len(triggered)} rule(s) triggered: "
        + ", ".join(r.rule_key for r in triggered)
        if triggered else "Transaction recorded. No rules triggered."
    )
    return back(f"/customers/{customer_id}", msg=note)

@router.post("/transaction-alerts/{alert_id}/disposition")
def transaction_alert_disposition(
    request: Request, db: DB, alert_id: int,
    status: Annotated[str, Form()],
    note: Annotated[str, Form()] = "",
    customer_id: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    back_url = f"/customers/{customer_id}" if customer_id.strip() else "/"
    try:
        require_csrf(request, csrf_token)
        disposition_transaction_alert(
            db, alert_id, session.org_id, status=status, note=note,
            actor=session.operator_name,
        )
    except (PermissionError, ValueError) as exc:
        return back(back_url, err=str(exc))
    return back(back_url, msg="Transaction alert dispositioned.")

# --------------------------------------------------------------------- alerts
_ALERT_STATUSES = ("open", "pending_review", "false_positive", "true_positive", "escalated", "all")

@router.get("/alerts", response_class=HTMLResponse)
def alerts(request: Request, db: DB, status: str = "open", sort: str = "age_asc", group_by: str = "",
           category: str = ""):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    # L-62: say so when a filter value isn't recognised, instead of silently
    # showing a different list.
    unknown_filter = (
        status not in _ALERT_STATUSES
        or sort not in ("age_asc", "age_desc")
        or (bool(category) and category not in queries.CATEGORY_LABELS)
        or group_by not in ("", "customer")
    )
    if status not in _ALERT_STATUSES:
        status = "open"
    sort_by = sort if sort in ("age_asc", "age_desc") else "age_asc"
    effective_status = None if status == "all" else status
    cat = category if category in queries.CATEGORY_LABELS else None
    cat_ctx = {"category": cat or "", "category_label": queries.CATEGORY_LABELS.get(cat, ""),
               "unknown_filter": unknown_filter}
    if group_by == "customer":
        grouped = queries.alert_queue_grouped(db, session.org_id, status=effective_status, category=cat)
        for g in grouped:
            for a in g["alerts"]:
                a["reviews"] = review_history(db, a["id"], session.org_id)
        return render(request, "alerts.html", {
            "session": session, "alerts": [], "grouped": grouped,
            "status": status, "sort": sort_by, "group_by": group_by, "reason_codes": REASON_CODES,
            **cat_ctx,
        }, db)
    queue = queries.alert_queue(db, session.org_id, status=effective_status, sort_by=sort_by, category=cat)
    for a in queue:
        a["reviews"] = review_history(db, a["id"], session.org_id)
    return render(request, "alerts.html", {
        "session": session, "alerts": queue, "grouped": [],
        "status": status, "sort": sort_by, "group_by": group_by, "reason_codes": REASON_CODES,
        **cat_ctx,
    }, db)

@router.post("/alerts/bulk-dismiss")
def alerts_bulk_dismiss(
    request: Request, db: DB,
    customer_id: Annotated[int, Form()],
    reason_code: Annotated[str, Form()] = "name_coincidence",
    back_to: Annotated[str, Form()] = "/alerts?group_by=customer",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        outcome = bulk_dismiss_alerts(
            db, session.org_id, customer_id=customer_id,
            reason_code=reason_code, operator=session.operator_name,
            operator_id=session.operator_id,
        )
    except (PermissionError, ReviewError) as exc:
        return back(back_to, err=str(exc))
    if outcome.pending_review:
        msg = (
            f"Dismissed {outcome.dismissed} alert(s). {outcome.pending_review} sanctions/PF "
            "match(es) staged for independent review - a second operator must confirm."
        )
    else:
        msg = f"Dismissed {outcome.dismissed} alert(s)."
    return back(back_to, msg=msg)

@router.get("/alerts/{alert_id}/panel", response_class=HTMLResponse)
def alert_panel(request: Request, db: DB, alert_id: int):
    try:
        session = require_session(request, db)
    except PermissionError:
        return HTMLResponse(
            '<div class="muted small">Session expired. Please sign in again.</div>',
            status_code=401,
        )
    rows = queries.alert_queue(db, session.org_id, status=None, alert_id=alert_id)
    if not rows:
        return HTMLResponse(
            '<div class="muted small">Alert not found.</div>', status_code=404,
        )
    html = templates.get_template("_alert_panel.html").render(
        a=rows[0], session=session,
        csrf_token=request.cookies.get(CSRF_COOKIE, ""),
        request=request,
    )
    return HTMLResponse(html)

@router.post("/alerts/{alert_id}/disposition")
def alert_disposition(
    request: Request, db: DB, alert_id: int,
    status: Annotated[str, Form()],
    reason_code: Annotated[str, Form()] = "",
    narrative: Annotated[str, Form()] = "",
    back_to: Annotated[str, Form()] = "/alerts",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        outcome = propose_disposition(
            db, alert_id, org_id=session.org_id, status=status, reason_code=reason_code,
            operator=session.operator_name, operator_id=session.operator_id, narrative=narrative,
        )
    except (PermissionError, ReviewError) as exc:
        return back(back_to, err=str(exc))
    return back(back_to, msg=outcome.message)

@router.post("/alerts/{alert_id}/confirm")
def alert_confirm(
    request: Request, db: DB, alert_id: int,
    agree: Annotated[str, Form()] = "yes",
    narrative: Annotated[str, Form()] = "",
    back_to: Annotated[str, Form()] = "/alerts",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        outcome = confirm_disposition(
            db, alert_id, org_id=session.org_id, operator=session.operator_name,
            operator_id=session.operator_id, agree=(agree == "yes"), narrative=narrative,
        )
    except (PermissionError, ReviewError) as exc:
        return back(back_to, err=str(exc))
    return back(back_to, msg=outcome.message)

@router.post("/alerts/{alert_id}/assign")
def alert_assign_route(
    request: Request, db: DB, alert_id: int,
    operator: Annotated[str, Form()] = "",
    back_to: Annotated[str, Form()] = "/alerts",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        assign_alert(db, alert_id, session.org_id,
                    operator=operator.strip() or None, actor=session.operator_name)
    except (PermissionError, ReviewError) as exc:
        return back(back_to, err=str(exc))
    msg = f"Assigned to {operator.strip()}." if operator.strip() else "Assignment cleared."
    return back(back_to, msg=msg)

@router.get("/alerts.csv")
def alerts_csv(request: Request, db: DB, status: str = "all", category: str = ""):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    cat = category if category in queries.CATEGORY_LABELS else None
    queue = queries.alert_queue(db, session.org_id, status=None if status == "all" else status,
                                category=cat)
    _audit_export(db, session, "export.alerts_csv", None, None,
                  {"status": status, "category": cat, "rows": len(queue)})
    return _csv_response(
        "alerts.csv",
        ["id", "category", "score", "caption", "matched_party", "status", "reason_code",
         "assigned_to", "customer_reference", "created_at"],
        [
            [a["id"], a["category"], f"{a['score']:.3f}", a["caption"], a["matched_party"],
             a["status"], a.get("reason_code") or "", a.get("assigned_to") or "",
             a.get("reference") or "", a["created_at"]]
            for a in queue
        ],
    )

"""Dashboard, onboarding dismissal, global search and the alerts summary API.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

from typing import Annotated

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import onboarding, queries
from ..deps import (
    can_view_audit,
    require_csrf,
    require_session,
)



from fastapi import APIRouter

from ..helpers import (
    DB,
    render,
)

router = APIRouter()


# ------------------------------------------------------------------ dashboard
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    d = queries.dashboard(db, session.org_id)
    lines = queries.alert_lines(d["open_alerts"], d["alert_counts"])
    # Adverse media is not an alert category (no queue, no second reviewer), but
    # it is a stream of findings waiting on a person, so it gets a line after PEP.
    adverse_line = queries.adverse_media_line(db, session.org_id)
    lines.insert(next((i + 1 for i, ln in enumerate(lines) if ln["key"] == "pep"), len(lines)), adverse_line)
    ctx = {
        "session": session,
        "d": d,
        "alert_lines": lines,
        "adverse_open_total": adverse_line["total"],
        "greeting": queries.dubai_greeting(),
        "datasets": queries.datasets(db),
    }
    if can_view_audit(session):
        ctx["recent_audit"] = queries.recent_audit(db, session.org_id)
    ctx["onboarding"] = onboarding.checklist(
        db, session.org_id, session.operator_id, session.operator_role)
    return render(request, "dashboard.html", ctx, db)

@router.post("/dashboard/onboarding/dismiss")
def dashboard_onboarding_dismiss(request: Request, db: DB,
                                 csrf_token: Annotated[str, Form()] = ""):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    onboarding.dismiss(db, session.org_id, session.operator_id)
    return RedirectResponse("/dashboard", status_code=303)

# --------------------------------------------------------------------- search
@router.get("/search")
def global_search(request: Request, db: DB, q: str = ""):
    from fastapi.responses import JSONResponse
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    return JSONResponse(queries.global_search(db, session.org_id, q))

@router.get("/api/alerts-summary")
def alerts_summary(request: Request, db: DB):
    from fastapi.responses import JSONResponse
    try:
        session = require_session(request, db)
    except PermissionError:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    screening = queries.alert_queue(db, session.org_id, status="open")[:10]
    txn = queries.transaction_alert_queue(db, session.org_id, status="open")[:10]
    overdue = [
        c for c in queries.customer_list(db, session.org_id)
        if c.get("review_overdue")
    ][:10]

    return JSONResponse({
        "total": len(screening) + len(txn) + len(overdue),
        "screening_alerts": [
            {"category": a["category"], "caption": a["caption"], "score": a["score"]}
            for a in screening
        ],
        "transaction_alerts": [
            {"customer_id": a["customer_id"], "customer_name": a["customer_name"],
             "severity": a["severity"], "rule_key": a["rule_key"], "amount_aed": a["amount_aed"]}
            for a in txn
        ],
        "overdue_reviews": [
            {"id": c["id"], "full_name": c["full_name"], "next_review": c["next_review"]}
            for c in overdue
        ],
    })

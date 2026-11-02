"""Platform super-admin console.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations


from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import queries
from ..deps import (
    current_session,
    require_session,
)



from fastapi import APIRouter

from ..helpers import (
    DB,
    back,
    render,
)

router = APIRouter()


# ---------------------------------------------------------------------- super-admin console
@router.get("/console", response_class=HTMLResponse)
def console_view(request: Request, db: DB):
    """Multi-org console for super-admin users."""
    try:
        session = require_session(request, db)
        from ..deps import require_super_admin
        require_super_admin(session)
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/", err=str(exc))

    from ... import ops
    data = queries.console_overview(db)
    return render(request, "console.html", {
        "session": session,
        "replica": ops.system_status(db, raw_replica=True)["replica"],
        **data,
    })

@router.get("/console/org/{org_id}/alerts", response_class=HTMLResponse)
def console_org_alerts(request: Request, db: DB, org_id: int, status: str = "open"):
    """Drill down into alerts for a specific org (super-admin only)."""
    try:
        session = require_session(request, db)
        from ..deps import require_super_admin
        require_super_admin(session)
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/console", err=str(exc))

    org = db.execute("SELECT name FROM organizations WHERE id=?", (org_id,)).fetchone()
    if org is None:
        return back("/console", err="Organization not found.")

    # A-02-5: Audit cross-tenant access by super-admin
    from ...db import audit
    audit(
        db, session.email, "console.org_alerts.view", "organization", str(org_id),
        {"super_admin_org_id": session.org_id, "status_filter": status},
        org_id=org_id
    )
    db.commit()

    from ...cases.review import review_history, REASON_CODES
    alert_list = queries.org_alerts(db, org_id, status=status if status != "all" else None)
    from ...cases.review import review_history
    for a in alert_list:
        a["reviews"] = review_history(db, a["id"], org_id)

    return render(request, "alerts.html", {
        "session": session,
        "alerts": alert_list,
        "status": status,
        "reason_codes": REASON_CODES,
        "org_name": org["name"],
        "super_admin_view": True,
    })

@router.get("/console/org/{org_id}/customers", response_class=HTMLResponse)
def console_org_customers(request: Request, db: DB, org_id: int):
    """Drill down into customers for a specific org (super-admin only)."""
    try:
        session = require_session(request, db)
        from ..deps import require_super_admin
        require_super_admin(session)
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/console", err=str(exc))

    org = db.execute("SELECT name FROM organizations WHERE id=?", (org_id,)).fetchone()
    if org is None:
        return back("/console", err="Organization not found.")

    # A-02-5: Audit cross-tenant access by super-admin
    from ...db import audit
    audit(
        db, session.email, "console.org_customers.view", "organization", str(org_id),
        {"super_admin_org_id": session.org_id},
        org_id=org_id
    )
    db.commit()

    customer_list = queries.org_customers(db, org_id)
    return render(request, "customers.html", {
        "session": session,
        "customers": customer_list,
        "org_name": org["name"],
        "super_admin_view": True,
    })

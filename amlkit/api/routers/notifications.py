"""In-app notifications.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

from typing import Annotated

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ... import notifications, queries
from ..deps import (
    require_csrf,
    require_session,
)



from fastapi import APIRouter

from ..helpers import (
    DB,
    back,
    render,
)

router = APIRouter()


@router.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    return render(request, "notifications.html", {
        "session": session,
        "items": queries.notifications_for(db, session.org_id, session.operator_id, limit=100),
    }, db)

@router.get("/notifications/unread-count")
def notifications_unread_count(request: Request, db: DB):
    """Polled by the bell in the page header."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return {"count": queries.unread_notification_count(db, session.org_id, session.operator_id)}

@router.post("/notifications/read-all")
def notifications_read_all(
    request: Request, db: DB, csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back("/notifications", err=str(exc))
    n = notifications.mark_all_read(db, session.org_id, session.operator_id)
    return back("/notifications", msg=f"{n} notification{'s' if n != 1 else ''} marked read.")

@router.post("/notifications/{notification_id}/read")
def notification_open(
    request: Request, db: DB, notification_id: int, csrf_token: Annotated[str, Form()] = "",
):
    """Mark one notification read and go to what it points at."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back("/notifications", err=str(exc))
    row = db.execute(
        "SELECT link FROM notifications WHERE id=? AND org_id=? AND operator_id=?",
        (notification_id, session.org_id, session.operator_id),
    ).fetchone()
    if row is None:
        return back("/notifications", err="Notification not found.")
    notifications.mark_read(db, session.org_id, session.operator_id, notification_id)
    link = row["link"] or "/notifications"
    # Links are written by notifications.py, but never redirect off-site regardless.
    if not link.startswith("/") or link.startswith("//"):
        link = "/notifications"
    return RedirectResponse(link, status_code=303)

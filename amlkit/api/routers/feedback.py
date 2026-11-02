"""Feedback submission and the admin feedback views.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

from typing import Annotated

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import queries
from ..limits import limiter
from ...db import utcnow
from ..csv_utils import _escape_csv_formula
from ..deps import (
    clamp_page,
    current_session,
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


# ---------------------------------------------------------------------- feedback
MAX_FEEDBACK_LENGTH = 5000

MAX_FEEDBACK_PAGE_LENGTH = 200

@router.post("/feedback")
@limiter.limit("10/minute")  # per IP (default key)
def feedback_submit(
    request: Request, db: DB,
    page: Annotated[str, Form()],
    message: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    """Accept user feedback from pilot users.

    Feedback is org-scoped so each firm's feedback stays separate. Used to
    collect bug reports, feature requests, and UX issues during pilot phase.
    """
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=401)

    message = message.strip()
    if not message:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Feedback message cannot be empty."}, status_code=400)
    if len(message) > MAX_FEEDBACK_LENGTH:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"error": f"Feedback is too long (maximum {MAX_FEEDBACK_LENGTH} characters)."}, status_code=400)
    page = page.strip()[:MAX_FEEDBACK_PAGE_LENGTH]

    now = utcnow()
    with db:
        db.execute(
            """INSERT INTO feedback (org_id, operator_id, page, message, created_at)
               VALUES (?,?,?,?,?)""",
            (session.org_id, session.operator_id, page.strip(), message, now),
        )
        from ...db import audit
        audit(db, session.operator_name, "feedback.submit", "feedback", None,
              {"page": page.strip()}, org_id=session.org_id)

    from fastapi.responses import JSONResponse
    return JSONResponse({"success": True, "message": "Thank you for your feedback!"})

@router.get("/admin/feedback", response_class=HTMLResponse)
def feedback_view(request: Request, db: DB, page: str = "1"):
    """MLRO-only viewer for feedback submitted via the in-app widget above.

    Same pagination shape as /audit: no COUNT query, just "is this page
    full?" to decide whether a Next link is shown.
    """
    try:
        session = require_session(request, db)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/", err=str(exc))

    page = clamp_page(page)
    per_page = 50
    offset = (page - 1) * per_page

    return render(request, "feedback_admin.html", {
        "session": session,
        "entries": queries.feedback_list(db, session.org_id, limit=per_page, offset=offset),
        "page": page,
        "per_page": per_page,
    })

@router.get("/admin/feedback/export")
def feedback_export(request: Request, db: DB):
    """Export this org's feedback as CSV. MLRO only, same shape as /audit/export."""
    try:
        session = require_session(request, db)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import Response as _R
        return _R(status_code=403)

    import csv
    import io as _io
    from fastapi.responses import StreamingResponse

    from ...pii import redact as _redact_pii

    entries = queries.feedback_list(db, session.org_id, limit=100000)
    _audit_export(db, session, "export.feedback_csv", None, None, {"rows": len(entries)})
    buf = _io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["created_at", "operator", "page", "message"])
    for e in entries:
        writer.writerow([
            _escape_csv_formula(e.get("created_at", "")),
            _escape_csv_formula(e.get("operator_name") or ""),
            _escape_csv_formula(e.get("page", "")),
            _escape_csv_formula(_redact_pii(e.get("message", ""))),
        ])
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=feedback.csv"},
    )

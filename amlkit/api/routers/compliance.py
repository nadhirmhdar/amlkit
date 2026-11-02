"""Compliance calendar and deadlines.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations


from fastapi import Request
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from ... import queries
from ..deps import (
    require_csrf,
    require_role,
    require_session,
)



from fastapi import APIRouter

from ..helpers import (
    DB,
    render,
)

router = APIRouter()


# ----------------------------------------------------- compliance calendar (p21)
@router.get("/compliance/calendar", response_class=HTMLResponse)
def compliance_calendar_view(request: Request, db: DB):
    """Compliance calendar list view."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)

    deadlines = queries.compliance_deadlines(db, session.org_id)
    from ...db import utcnow
    now = utcnow()
    for d in deadlines:
        d["is_overdue"] = d["due_date"] < now and d["completed_at"] is None

    return render(request, "compliance_calendar.html", {"session": session, "deadlines": deadlines})

@router.get("/compliance/deadlines")
def compliance_deadlines_list(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    if session.operator_role not in _DEADLINE_ROLES:
        return Response(status_code=403)
    return queries.compliance_deadlines(db, session.org_id)

class _DeadlineCreate(BaseModel):
    title: str = ""
    due_date: str = ""
    description: str = ""
    recurrence: str = "none"

class _DeadlineUpdate(BaseModel):
    title: str | None = None
    due_date: str | None = None
    description: str | None = None
    recurrence: str | None = None

_DEADLINE_ROLES = ("officer", "mlro")

_DEADLINE_RECURRENCES = ("none", "one-time", "monthly", "quarterly", "annual", "annually")

def _deadline_gate(request: Request, db: DB, *, write: bool):
    """Session and role (officer/MLRO). Returns (session, error_response).

    Write routes also call `require_csrf` themselves (the static CSRF scan in
    tests/test_goaml_reference_csrf_finalise.py wants it visible in each route).
    """
    try:
        session = require_session(request, db)
        require_role(session, *_DEADLINE_ROLES)
    except PermissionError:
        return None, Response(status_code=403)
    return session, None

def _clean_deadline_fields(title, due_date, recurrence, *, require_all: bool):
    """Validate deadline input. Returns (fields, error message or None)."""
    from datetime import date
    out: dict[str, str] = {}
    if title is not None or require_all:
        t = (title or "").strip()
        if not t:
            return out, "A title is required."
        out["title"] = t
    if due_date is not None or require_all:
        try:
            out["due_date"] = date.fromisoformat((due_date or "").strip()).isoformat()
        except ValueError:
            return out, "due_date must be an ISO date (YYYY-MM-DD)."
    if recurrence is not None:
        rec = recurrence.strip().lower() or "none"
        if rec not in _DEADLINE_RECURRENCES:
            return out, "recurrence must be one of: " + ", ".join(_DEADLINE_RECURRENCES) + "."
        out["recurrence"] = rec
    return out, None

@router.post("/compliance/deadlines")
def compliance_deadlines_create(request: Request, db: DB, body: _DeadlineCreate):
    try:
        require_csrf(request, request.headers.get("X-CSRF-Token") or "")
    except PermissionError:
        return Response(status_code=403)
    session, denied = _deadline_gate(request, db, write=True)
    if denied is not None:
        return denied
    fields, err = _clean_deadline_fields(body.title, body.due_date, body.recurrence, require_all=True)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    fields.setdefault("recurrence", "none")
    from ...db import audit, utcnow
    cur = db.execute(
        "INSERT INTO compliance_deadlines (org_id, title, description, due_date, recurrence, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session.org_id, fields["title"], body.description, fields["due_date"],
         fields["recurrence"], utcnow())
    )
    deadline_id = cur.lastrowid
    audit(db, session.operator_name, "compliance.deadline_created", "compliance_deadline", deadline_id,
          {"title": fields["title"], "due_date": fields["due_date"],
           "recurrence": fields["recurrence"]}, org_id=session.org_id)
    db.commit()
    return queries.compliance_deadline(db, session.org_id, deadline_id)

@router.patch("/compliance/deadlines/{deadline_id}")
def compliance_deadlines_update(request: Request, db: DB, deadline_id: int, body: _DeadlineUpdate):
    try:
        require_csrf(request, request.headers.get("X-CSRF-Token") or "")
    except PermissionError:
        return Response(status_code=403)
    session, denied = _deadline_gate(request, db, write=True)
    if denied is not None:
        return denied
    existing = queries.compliance_deadline(db, session.org_id, deadline_id)
    if existing is None:
        return Response(status_code=404)
    fields, err = _clean_deadline_fields(
        body.title if body.title else None, body.due_date, body.recurrence, require_all=False)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    if body.description is not None:
        fields["description"] = body.description
    changes = {k: v for k, v in fields.items() if existing.get(k) != v}
    if changes:
        from ...db import audit
        # Column names come from the fixed set built above, never from the client.
        sets = ", ".join(f"{k}=?" for k in changes)
        # One literal filled by .format(), not an f-string: the static tenant scan
        # (tests/test_tenant_isolation.py) otherwise sees the split-off prefix.
        db.execute("UPDATE compliance_deadlines SET {} WHERE id=? AND org_id=?".format(sets),
                   (*changes.values(), deadline_id, session.org_id))
        audit(db, session.operator_name, "compliance.deadline_updated", "compliance_deadline",
              deadline_id,
              {"old": {k: existing.get(k) for k in changes}, "new": changes},
              org_id=session.org_id)
        db.commit()
    return queries.compliance_deadline(db, session.org_id, deadline_id)

@router.delete("/compliance/deadlines/{deadline_id}")
def compliance_deadlines_delete(request: Request, db: DB, deadline_id: int):
    try:
        require_csrf(request, request.headers.get("X-CSRF-Token") or "")
    except PermissionError:
        return Response(status_code=403)
    session, denied = _deadline_gate(request, db, write=True)
    if denied is not None:
        return denied
    existing = queries.compliance_deadline(db, session.org_id, deadline_id)
    if existing is None:
        return Response(status_code=404)
    from ...db import audit
    db.execute("DELETE FROM compliance_deadlines WHERE id=? AND org_id=?", (deadline_id, session.org_id))
    audit(db, session.operator_name, "compliance.deadline_deleted", "compliance_deadline",
          deadline_id, {"old": existing}, org_id=session.org_id)
    db.commit()
    return Response(status_code=204)

"""Audit trail view and export.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations


from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import queries
from ..csv_utils import _escape_csv_formula
from ..deps import (
    AUDIT_VIEW_ROLES,
    clamp_page,
    current_session,
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


# ---------------------------------------------------------------------- audit
@router.get("/audit", response_class=HTMLResponse)
def audit_view(request: Request, db: DB, page: str = "1"):
    try:
        session = require_session(request, db)
        require_role(session, *AUDIT_VIEW_ROLES)
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/", err=str(exc))

    page = clamp_page(page)
    per_page = 50
    offset = (page - 1) * per_page

    return render(request, "audit.html", {
        "session": session,
        "entries": queries.audit_trail(db, session.org_id, limit=per_page, offset=offset),
        "page": page,
        "per_page": per_page,
    })

@router.get("/audit/export")
def audit_export(request: Request, db: DB):
    """Export the full audit log for the org as a CSV file. MLRO only."""
    try:
        session = require_session(request, db)
        require_role(session, *AUDIT_VIEW_ROLES)
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/", err=str(exc))

    import csv
    import json
    import io as _io
    from fastapi.responses import StreamingResponse

    from ...pii import redact as _redact_pii

    entries = queries.audit_trail(db, session.org_id, limit=100000)
    _audit_export(db, session, "export.audit_csv", None, None, {"rows": len(entries)})
    buf = _io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "action", "user", "object_type", "object_id", "detail"])
    for e in entries:
        writer.writerow([
            _escape_csv_formula(e.get("ts", "")),
            _escape_csv_formula(e.get("action", "")),
            _escape_csv_formula(e.get("actor", "")),
            _escape_csv_formula(e.get("object_type", "")),
            _escape_csv_formula(e.get("object_id", "")),
            # audit_trail() returns detail already JSON-decoded (usually a
            # dict); redact() needs the serialised text.
            _escape_csv_formula(_redact_pii(
                e["detail"] if isinstance(e.get("detail"), str)
                else json.dumps(e["detail"], ensure_ascii=False) if e.get("detail") is not None
                else ""
            )),
        ])
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )

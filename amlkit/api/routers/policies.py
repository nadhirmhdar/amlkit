"""Policy document upload and download.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

from typing import Annotated

from fastapi import Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from ..limits import limiter
from ..deps import (
    current_session,
    require_csrf,
    require_role,
    require_session,
)



from fastapi import APIRouter

from ..helpers import (
    DB,
    back,
    render,
)

router = APIRouter()


# ---------------------------------------------------------------------- policies (Phase 4 enhancement)
@router.get("/policies", response_class=HTMLResponse)
def policies_list(request: Request, db: DB):
    """List all policy documents grouped by title with version history."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)

    from ...cases.manager import list_policies

    policies_by_title = list_policies(db, session.org_id)
    categories = ["AML_Policy", "CDD_Procedures", "Risk_Methodology", "Other"]

    return render(
        request,
        "policies.html",
        {
            "session": session,
            "policies_by_title": policies_by_title,
            "categories": categories,
        },
        db
    )

@router.post("/policies/upload")
@limiter.limit("10/hour")
def policies_upload(
    request: Request,
    db: DB,
    title: Annotated[str, Form()],
    category: Annotated[str, Form()],
    file: UploadFile,
    csrf_token: Annotated[str, Form()] = "",
):
    """Upload new policy document (MLRO only)."""
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/policies", err=str(exc))

    from ...cases.manager import upload_policy

    try:
        from ...validation import read_capped
        file_content = read_capped(file.file)

        # Validate MIME type by magic bytes
        from ...validation import DOCX, PDF, UploadRejected, validate_upload
        try:
            detected_mime = validate_upload(file_content, allowed_mimes={PDF, DOCX})
            ext = (file.filename or "").lower().rsplit(".", 1)[-1]
            if {"pdf": PDF, "docx": DOCX}.get(ext, detected_mime) != detected_mime:
                raise UploadRejected("File content does not match its extension.")
        except UploadRejected as exc:
            return back("/policies", err=f"File validation failed: {exc}")

        policy_id, version = upload_policy(
            db,
            session.org_id,
            title=title,
            category=category,
            filename=file.filename,
            file_content=file_content,
            uploaded_by=session.operator_name,
        )
        db.commit()

        return back("/policies", msg=f"Policy '{title}' uploaded successfully (version {version})")
    except ValueError as e:
        return back("/policies", err=f"Upload failed: {e}")

@router.get("/policies/{policy_id:int}/download")
def policies_download(request: Request, db: DB, policy_id: int):
    """Download policy document."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)

    from ...cases.manager import get_policy

    try:
        policy = get_policy(db, policy_id, org_id=session.org_id)
        db.commit()  # Commit audit log

        content_type = (
            "application/pdf" if policy["filename"].endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

        return Response(
            content=policy["file_content"],
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{policy["filename"]}"'
            }
        )
    except ValueError as e:
        # get_policy() raises ValueError for a missing policy (or an
        # unreadable file). There is no error.html template and no HTML
        # exception handler, so render a proper 404 the same way the report
        # and customer download routes do, rather than a 500.
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=str(e))

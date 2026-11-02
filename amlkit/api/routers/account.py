"""Account pages: profile, password change, trusted devices, disclaimer acknowledgement.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

from typing import Annotated

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import auth
from ...db import utcnow
from ..deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    current_session,
    require_csrf,
    require_session,
)

import os


from fastapi import APIRouter

from ..helpers import (
    DB,
    _COOKIE_MAX_AGE,
    back,
    render,
)

router = APIRouter()


@router.get("/account/password")
def password_change_form(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    return render(request, "password_change.html", {"session": session, "nav": None})

def _keep_signed_in_after_password_change(db, session, resp):
    """auth.set_password revokes every session, this one included. Mint a fresh
    one for the operator who just changed the password so the banner ("all
    OTHER sessions have been signed out") is true (L-79). The caller has
    already passed require_session, so MFA was satisfied."""
    token = auth.create_session(db, session.operator_id, session.org_id, mfa_verified=True)
    _behind_proxy = os.environ.get("AMLKIT_BEHIND_PROXY") == "1"
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict",
                    secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    resp.set_cookie(CSRF_COOKIE, auth.new_csrf_token(), httponly=True,
                    samesite="lax", secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    return resp

@router.post("/account/password")
def password_change_submit(
    request: Request, db: DB,
    current_password: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return RedirectResponse("/login", status_code=303)

    # Verify current password
    op_row = db.execute("SELECT password_hash FROM operators WHERE id=?", (session.operator_id,)).fetchone()
    if not auth.verify_password(current_password, op_row["password_hash"]):
        return render(request, "password_change.html", {
            "session": session, "nav": None, "err": "Current password is incorrect."
        })

    # Verify new passwords match
    if new_password != confirm_password:
        return render(request, "password_change.html", {
            "session": session, "nav": None, "err": "New passwords do not match."
        })

    # Validate password complexity (and that it differs from the current one)
    try:
        auth.check_new_password(new_password, current_hash=op_row["password_hash"])
    except auth.PasswordComplexityError as exc:
        return render(request, "password_change.html", {
            "session": session, "nav": None, "err": str(exc)
        })

    # Update password
    auth.set_password(db, session.operator_id, new_password)
    
    from ...db import audit
    audit(db, session.operator_name, "operator.password_changed", "operator", session.operator_id,
          None, org_id=session.org_id)
    db.commit()

    return _keep_signed_in_after_password_change(
        db, session, back("/", msg="Password changed successfully. All other sessions have been signed out."))

@router.post("/account/forget-devices")
def forget_devices_submit(
    request: Request, db: DB,
    csrf_token: Annotated[str, Form()] = "",
):
    """Revoke every remembered ('skip MFA for 30 days') device for the
    current operator. Next login anywhere will ask for a TOTP code again."""
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)

    auth.revoke_trusted_devices_for(db, session.operator_id)
    from ...db import audit
    audit(db, session.operator_name, "mfa.devices_forgotten", "operator", session.operator_id,
          None, org_id=session.org_id)
    db.commit()

    return back("/account/password", msg="All remembered devices have been forgotten. "
                                          "They will be asked for a code on next sign-in.")

@router.post("/acknowledge-disclaimer")
def acknowledge_disclaimer(
    request: Request, db: DB,
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back("/", err=str(exc))

    db.execute(
        "UPDATE operators SET disclaimer_acknowledged_at=? WHERE id=? AND org_id=?",
        (utcnow(), session.operator_id, session.org_id),
    )
    db.commit()
    return back("/", msg="Disclaimer acknowledged.")

# ------------------------------------------------------------------ profile/password change (p16)
@router.get("/profile", response_class=HTMLResponse)
def profile_view(request: Request, db: DB):
    """User profile page with password change form."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    return render(request, "profile.html", {"session": session})

@router.post("/profile/change-password")
def change_password(
    request: Request, db: DB,
    old_password: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    """Self-service password change."""
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/profile", err=str(exc))

    operator = db.execute(
        "SELECT id, password_hash FROM operators WHERE id=?",
        (session.operator_id,)
    ).fetchone()

    if not operator or not auth.verify_password(old_password, operator["password_hash"]):
        return back("/profile", err="Current password is incorrect.")

    try:
        auth.check_new_password(new_password, current_hash=operator["password_hash"])
    except auth.PasswordComplexityError as exc:
        return back("/profile", err=str(exc))

    auth.set_password(db, session.operator_id, new_password)

    from ...db import audit
    audit(db, session.operator_name, "operator.password_changed", "operator", session.operator_id,
          None, org_id=session.org_id)
    db.commit()

    return _keep_signed_in_after_password_change(
        db, session, back("/profile", msg="Password changed successfully. All other sessions have been signed out."))

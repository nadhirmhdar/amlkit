"""Two-factor (TOTP) verify, setup and disable.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

from typing import Annotated

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import auth
from ..limits import limiter
from ..deps import (
    SESSION_COOKIE,
    require_csrf,
    require_session,
)

import os


from fastapi import APIRouter

from ..helpers import (
    DB,
    back,
    render,
)

router = APIRouter()


@router.get("/mfa/verify", response_class=HTMLResponse)
def mfa_verify_form(request: Request, db: DB):
    """Render TOTP code entry form for MFA challenge (p15)."""
    session_row = auth.mfa_session_state(db, request.cookies.get(SESSION_COOKIE))
    if not session_row:
        return RedirectResponse("/login", status_code=303)
    if session_row["mfa_verified"]:
        return RedirectResponse("/", status_code=303)
    if not auth.mfa_is_enrolled(db, session_row["operator_id"]):
        return RedirectResponse("/mfa/setup", status_code=303)

    return render(request, "mfa_verify.html", {
        "session": None,  # No full session yet
        "operator_name": session_row["name"],
    })

@router.post("/mfa/verify")
@limiter.limit("5/minute")  # per IP; auth.mfa_check_code() adds the per-operator lockout
def mfa_verify_submit(
    request: Request, db: DB,
    code: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
    remember_device: Annotated[str, Form()] = "",
):
    """Verify TOTP code and upgrade session to mfa_verified=1 (p15)."""
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back("/mfa/verify", err=str(exc))

    token = request.cookies.get(SESSION_COOKIE)
    session_row = auth.mfa_session_state(db, token)
    if not session_row:
        return RedirectResponse("/login", status_code=303)
    if session_row["mfa_verified"]:
        return RedirectResponse("/", status_code=303)

    operator_id = session_row["operator_id"]
    if not auth.mfa_is_enrolled(db, operator_id):
        return RedirectResponse("/mfa/setup", status_code=303)
    outcome = auth.mfa_check_code(db, operator_id, code, stage="verify",
                                  actor=session_row["name"], org_id=session_row["org_id"])
    if outcome == "ok":
        auth.set_session_mfa_verified(db, token, True)
        resp = RedirectResponse("/", status_code=303)
        if remember_device:
            raw_device_token = auth.create_trusted_device(db, operator_id)
            _behind_proxy = os.environ.get("AMLKIT_BEHIND_PROXY") == "1"
            resp.set_cookie(
                auth.TRUSTED_DEVICE_COOKIE, raw_device_token, httponly=True, samesite="strict",
                secure=_behind_proxy, max_age=int(auth.TRUSTED_DEVICE_LIFETIME.total_seconds()),
            )
            from ...db import audit
            audit(db, session_row["name"], "mfa.device_trusted", "operator", operator_id,
                  None, org_id=session_row["org_id"])
            db.commit()
        return resp
    if outcome == "locked":
        return back("/mfa/verify", err=_MFA_LOCKED_MESSAGE)
    return back("/mfa/verify", err="Invalid verification code. Please try again.")

_MFA_LOCKED_MESSAGE = ("Too many failed codes. Two-factor sign-in is locked for 15 minutes; "
                       "the attempts have been recorded in the audit trail.")

@router.get("/mfa/setup", response_class=HTMLResponse)
def mfa_setup_form(request: Request, db: DB):
    """Display QR code for MFA enrollment (p15 - forced for MLRO)."""
    session_row = auth.mfa_session_state(db, request.cookies.get(SESSION_COOKIE))
    if not session_row:
        return RedirectResponse("/login", status_code=303)
    if session_row["mfa_verified"]:
        return RedirectResponse("/", status_code=303)

    # Block re-enrollment if already enrolled (prevents CSRF secret overwrite)
    if auth.mfa_is_enrolled(db, session_row["operator_id"]):
        return RedirectResponse("/mfa/verify", status_code=303)

    # Reuses a pending secret, so a reload after scanning keeps the app valid.
    secret, qr_uri = auth.mfa_enroll(db, session_row["operator_id"])

    # Rendered locally: the provisioning URI carries the TOTP secret, so it must
    # never be sent to a third-party QR service (and the CSP would block one).
    # svg_data_uri() keeps the xmlns declaration; svg_inline() strips it, and an
    # <img> decoder refuses a namespace-less SVG (broken-image icon).
    import segno
    qr_data_uri = segno.make(qr_uri, error="m").svg_data_uri(scale=5, border=2)

    return render(request, "mfa_setup.html", {
        "session": None,
        "operator_name": session_row["name"],
        "secret": secret,
        "qr_data_uri": qr_data_uri,
    })

@router.post("/mfa/setup")
@limiter.limit("5/minute")  # per IP; auth.mfa_check_code() adds the per-operator lockout
def mfa_setup_confirm(
    request: Request, db: DB,
    code: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    """Confirm MFA enrollment by verifying a test TOTP code (p15)."""
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back("/mfa/setup", err=str(exc))

    token = request.cookies.get(SESSION_COOKIE)
    session_row = auth.mfa_session_state(db, token)
    if not session_row:
        return RedirectResponse("/login", status_code=303)

    if session_row["mfa_verified"]:
        return RedirectResponse("/", status_code=303)

    # Enrolment is confirmed by proving possession of the authenticator once;
    # until then the secret shown on the page is only pending.
    operator_id = session_row["operator_id"]
    outcome = auth.mfa_check_code(db, operator_id, code, stage="setup",
                                  actor=session_row["name"], org_id=session_row["org_id"])
    if outcome == "ok":
        backup_codes = auth.mfa_confirm(db, operator_id)
        auth.set_session_mfa_verified(db, token, True)
        from ...db import audit
        audit(db, session_row["name"], "mfa.enrolled", "operator", operator_id, None,
              org_id=session_row["org_id"])
        db.commit()
        # Shown exactly once: the codes are stored hashed, so this response is
        # the only place they ever appear in plaintext.
        return render(request, "mfa_backup_codes.html", {
            "session": None, "backup_codes": backup_codes,
        })
    if outcome == "locked":
        return back("/mfa/setup", err=_MFA_LOCKED_MESSAGE)
    return back("/mfa/setup", err="Invalid verification code. Please scan the QR code and try again.")

@router.post("/mfa/disable")
def mfa_disable_submit(
    request: Request, db: DB,
    totp_code: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    """Disable MFA for operator. Requires valid TOTP code (p15)."""
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back("/account", err=str(exc))

    # Require TOTP code only (password alone is insufficient - prevents MFA removal via password compromise)
    # Use mfa_check_code with stage="verify" to apply lockout and failed-attempt audit logging
    if not totp_code:
        return back("/account", err="Enter a valid TOTP code to disable MFA.")

    outcome = auth.mfa_check_code(db, session.operator_id, totp_code, stage="verify",
                                  actor=session.operator_name, org_id=session.org_id)
    if outcome == "locked":
        return back("/account", err="Too many failed attempts. Try again in 15 minutes.")
    if outcome != "ok":
        return back("/account", err="Enter a valid TOTP code to disable MFA.")

    # Disable MFA
    db.execute("DELETE FROM mfa_secrets WHERE operator_id=?", (session.operator_id,))
    db.execute("DELETE FROM mfa_backup_codes WHERE operator_id=?", (session.operator_id,))
    db.commit()

    from ...db import audit
    audit(db, session.operator_name, "operator.mfa_disabled", "operator", session.operator_id,
          None, org_id=session.org_id)

    return back("/account", msg="Two-factor authentication has been disabled.")

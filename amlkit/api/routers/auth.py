"""Sign-in, sign-out, registration, e-mail verification, setup tokens, self-unlock and UAE PASS operator SSO.

Moved verbatim from api/app.py (WP-18, issue #73): no route, dependency or limit changed.
"""

from __future__ import annotations

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import auth, uaepass
from ...billing import self_serve_enabled
from ..limits import limiter, login_rate_limit_key
from ..deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    client_ip,
    current_session,
    require_csrf,
)

import os
import secrets


from fastapi import APIRouter

from ..helpers import (
    DB,
    _COOKIE_MAX_AGE,
    _clear_uaepass_state_cookie,
    _set_uaepass_state_cookie,
    _uaepass_redirect_uri,
    back,
    render,
)

router = APIRouter()


# ----------------------------------------------------------------- sign-in
@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, db: DB):
    # A locked MLRO session bounced here by require_session() belongs on the
    # MFA challenge, not on the password form it has already passed.
    pending = auth.mfa_session_state(db, request.cookies.get(SESSION_COOKIE))
    if pending and pending["role"] == "mlro" and not pending["mfa_verified"]:
        return RedirectResponse(auth.mfa_challenge_path(db, pending["operator_id"]), status_code=303)
    ctx: dict = {"session": None}
    evicted = auth.pop_evicted_notice(db, request.cookies.get(SESSION_COOKIE))
    if evicted:
        ctx["err"] = evicted
    return render(request, "login.html", ctx)

def _login_page_error(request: Request, message: str) -> HTMLResponse:
    return render(request, "login.html", {"session": None, "err": message})

@router.post("/login")
@limiter.limit("10/minute")  # IP ceiling: prevents brute force attacks from single IP
@limiter.limit("3/minute", key_func=login_rate_limit_key)  # Per-account: prevents rapid stuffing of one account
def login_submit(
    request: Request, db: DB,
    email: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return _login_page_error(request, str(exc))
    if not email.strip() or not password:
        # An empty field is "missing" to FastAPI's Form(); answer with the
        # form, not a raw 422 JSON body.
        return _login_page_error(request, "Enter your email and password.")
    try:
        token, info = auth.login(db, email, password, ip=client_ip(request))
    except auth.AuthError as exc:
        if "verify your email" in str(exc):
            return render(request, "login.html", {
                "session": None, "err": str(exc), "unverified_email": email.strip().lower(),
            })
        return _login_page_error(request, str(exc))

    # p15: an MLRO session is issued locked; enrolled operators must pass the
    # TOTP challenge, un-enrolled ones are sent straight to enrolment.
    _behind_proxy = os.environ.get("AMLKIT_BEHIND_PROXY") == "1"
    target = auth.mfa_lock_session(
        db, token, info.operator_id, info.operator_role,
        trusted_device_token=request.cookies.get(auth.TRUSTED_DEVICE_COOKIE),
    ) or "/"

    resp = RedirectResponse(target, status_code=303)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict",
                    secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    # M-01: Rotate CSRF token on login (defence-in-depth)
    resp.set_cookie(CSRF_COOKIE, auth.new_csrf_token(), httponly=True,
                    samesite="lax", secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    return resp

@router.get("/auth/uaepass/start")
@limiter.limit("10/minute")  # IP ceiling, matching /login's: an alternative way to get a session
def uaepass_operator_start(request: Request, db: DB):
    """Redirect to UAE PASS for "Sign in with UAE PASS" (operator/MLRO SSO).

    No session required -- this IS an alternative way to get one, alongside
    /login. Inert (404) until UAEPASS_CLIENT_ID/UAEPASS_CLIENT_SECRET are
    configured; see uaepass.load_config().
    """
    config = uaepass.load_config()
    if config is None:
        raise HTTPException(status_code=404)
    redirect_uri = _uaepass_redirect_uri("/auth/uaepass/callback")
    state = auth.create_uaepass_state(db, purpose="operator_sso", redirect_uri=redirect_uri)
    resp = RedirectResponse(
        uaepass.build_authorize_url(
            config, state=state, redirect_uri=redirect_uri, acr=uaepass.ACR_LEVEL_DEFAULT
        ),
        status_code=303,
    )
    _set_uaepass_state_cookie(resp, state)
    return resp

@router.get("/auth/uaepass/callback")
@limiter.limit("10/minute")  # IP ceiling, matching /login's: unthrottled otherwise unlike every other auth entry point
def uaepass_operator_callback(request: Request, db: DB, code: str = "", state: str = ""):
    """UAE PASS redirects here with ?code=&state=. See
    auth.resolve_uaepass_operator() for the operator-linking policy (never
    auto-provisions an account), auth.consume_uaepass_state() for the
    DB-side state/replay check, and UAEPASS_STATE_COOKIE's comment for why
    that check alone is not enough (login CSRF / session swapping) and this
    route also requires the state to match this exact browser's cookie.
    """
    config = uaepass.load_config()
    if config is None:
        raise HTTPException(status_code=404)

    if not auth.csrf_valid(request.cookies.get(auth.UAEPASS_STATE_COOKIE), state):
        return _clear_uaepass_state_cookie(
            back("/login", err="UAE PASS sign-in expired or was already used. Please try again.")
        )
    row = auth.consume_uaepass_state(db, state, purpose="operator_sso")
    if row is None:
        return _clear_uaepass_state_cookie(
            back("/login", err="UAE PASS sign-in expired or was already used. Please try again.")
        )
    if not code:
        return _clear_uaepass_state_cookie(
            back("/login", err="UAE PASS sign-in was cancelled or did not return a code.")
        )

    try:
        token_payload = uaepass.exchange_code(config, code=code, redirect_uri=row["redirect_uri"])
        profile = uaepass.fetch_userinfo(config, token_payload["access_token"])
    except uaepass.UaePassError as exc:
        return _clear_uaepass_state_cookie(back("/login", err=f"UAE PASS sign-in failed: {exc}"))

    operator, _newly_linked = auth.resolve_uaepass_operator(db, profile)
    if operator is None:
        return _clear_uaepass_state_cookie(back(
            "/login",
            err="No groAML account is linked to this UAE PASS identity yet. "
                "Ask an admin to link your account, then try again.",
        ))

    if auth.operator_login_locked(db, operator["id"]):
        # Password lock (8 failures) also blocks SSO; same text password
        # login gives for a locked account. The MFA lock is a separate matter.
        from ...db import audit
        audit(db, operator["name"], "operator.sso_refused_locked", "operator", operator["id"],
              {"method": "uaepass"}, org_id=operator["org_id"])
        db.commit()
        return _clear_uaepass_state_cookie(back("/login", err="Incorrect email or password."))

    token, info = auth.login_via_uaepass(db, operator, ip=client_ip(request))
    _behind_proxy = os.environ.get("AMLKIT_BEHIND_PROXY") == "1"
    # Same MFA-lock + redirect-target logic as password login_submit() above
    # -- no entry point hands an MLRO an unlocked session (see
    # auth.mfa_lock_session()'s docstring).
    target = auth.mfa_lock_session(
        db, token, info.operator_id, info.operator_role,
        trusted_device_token=request.cookies.get(auth.TRUSTED_DEVICE_COOKIE),
    ) or "/"
    resp = RedirectResponse(target, status_code=303)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict",
                    secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    resp.set_cookie(CSRF_COOKIE, auth.new_csrf_token(), httponly=True,
                    samesite="lax", secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    return _clear_uaepass_state_cookie(resp)

@router.post("/logout")
def logout_submit(request: Request, db: DB, csrf_token: Annotated[str, Form()] = ""):
    session = current_session(request, db)
    if session is None:
        # Nothing to protect: no session means a forged logout cannot sign
        # anyone out, so a stale tab or an expired session just lands on the
        # sign-in page instead of a bare 403.
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie(SESSION_COOKIE)
        return resp
    try:
        require_csrf(request, csrf_token)
    except PermissionError:
        # Signed in but the token is stale/missing: keep the session (a
        # cross-site forced logout stays blocked) and ask the user to retry.
        return back("/", err="Please try logging out again.")
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        auth.logout(db, token, session, ip=client_ip(request))
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp

def _valid_setup_token(db: sqlite3.Connection, raw_token: str):
    if not raw_token:
        return None
    from datetime import datetime, timezone
    from hashlib import sha256
    row = db.execute(
        "SELECT id, org_id, used_at, expires_at FROM setup_tokens WHERE token_hash=?",
        (sha256(raw_token.encode()).hexdigest(),),
    ).fetchone()
    if row is None or row["used_at"] is not None:
        return None
    # NULL expires_at (a row from before setup_tokens had this column) is
    # treated as already expired -- fail closed rather than granting an old,
    # possibly long-forwarded link an unbounded lifetime.
    if row["expires_at"] is None or datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        return None
    return row

@router.get("/setup", response_class=HTMLResponse)
def setup_form(request: Request, db: DB, token: str = ""):
    row = _valid_setup_token(db, token)
    if row is None:
        return render(request, "setup.html", {
            "session": None, "valid": False,
            "err": "This setup link is invalid, expired, or already used.",
        })
    org = db.execute("SELECT name FROM organizations WHERE id=?", (row["org_id"],)).fetchone()
    if org is None:
        return render(request, "setup.html", {
            "session": None, "valid": False,
            "err": "This setup link is invalid, expired, or already used.",
        })
    return render(request, "setup.html", {
        "session": None, "valid": True, "token": token, "org_name": org["name"],
    })

@router.post("/setup")
def setup_submit(
    request: Request, db: DB,
    token: Annotated[str, Form()],
    name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return render(request, "setup.html", {"session": None, "valid": True, "token": token, "err": str(exc)})

    from ...cases.operators import complete_initial_setup

    try:
        result = complete_initial_setup(db, token, name, email, password)
    except (auth.PasswordComplexityError, auth.IdentityError) as exc:
        # The link itself is still good: keep the form so the user can fix the field.
        tok_row = _valid_setup_token(db, token)
        org = db.execute("SELECT name FROM organizations WHERE id=?", (tok_row["org_id"],)).fetchone() if tok_row else None
        if org is None:
            return render(request, "setup.html", {"session": None, "valid": False, "err": str(exc)})
        return render(request, "setup.html", {
            "session": None, "valid": True, "token": token, "org_name": org["name"], "err": str(exc),
        })
    except ValueError as exc:
        return render(request, "setup.html", {
            "session": None, "valid": False, "err": str(exc),
        })

    session_token, info = auth.login(db, result["email"], password, ip=client_ip(request))
    # p15: the first operator is the MLRO, so this session starts locked too.
    target = auth.mfa_lock_session(
        db, session_token, info.operator_id, info.operator_role,
        trusted_device_token=request.cookies.get(auth.TRUSTED_DEVICE_COOKIE),
    ) or "/"
    resp = RedirectResponse(target, status_code=303)
    _behind_proxy = os.environ.get("AMLKIT_BEHIND_PROXY") == "1"
    resp.set_cookie(SESSION_COOKIE, session_token, httponly=True, samesite="strict",
                    secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    resp.set_cookie(CSRF_COOKIE, auth.new_csrf_token(), httponly=True,
                    samesite="lax", secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    return resp

@router.get("/register-organization", response_class=HTMLResponse)
def register_org_form(request: Request, db: DB):
    self_serve = self_serve_enabled()
    invite_configured = bool(os.environ.get("AMLKIT_REGISTRATION_INVITE_CODE", "").strip())
    # Stripe mode: open sign-up (trial starts at Checkout). Otherwise invite-gated.
    return render(request, "register_organization.html", {
        "session": None, "registration_open": self_serve or invite_configured,
        "needs_invite": not self_serve,
    })

@router.post("/register-organization")
@limiter.limit("5/minute")
def register_org_submit(
    request: Request, db: DB,
    org_name: Annotated[str, Form()],
    name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
    invite_code: Annotated[str, Form()] = "",
):
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return render(request, "register_organization.html", {
            "session": None, "registration_open": True, "err": str(exc),
            "needs_invite": not self_serve_enabled(),
        })

    self_serve = self_serve_enabled()
    expected = os.environ.get("AMLKIT_REGISTRATION_INVITE_CODE", "").strip()
    # The invite code is honoured only when self-serve (Stripe) is off.
    if not self_serve and (not expected or not secrets.compare_digest(invite_code.strip().encode(), expected.encode())):
        auth._log_auth_event(db, "register_denied", email.strip().lower(),
                             {"reason": "invalid_invite_code", "via": "web"})
        db.commit()
        return render(request, "register_organization.html", {
            "session": None, "registration_open": bool(expected), "needs_invite": True,
            "err": "Invalid invite code.",
        })

    from ...cases.operators import register_organization
    from ... import mail

    try:
        result = register_organization(db, org_name, name, email, password,
                                      pending_payment=self_serve)
    except ValueError as exc:
        return render(request, "register_organization.html", {
            "session": None, "err": str(exc), "registration_open": True,
            "needs_invite": not self_serve,
        })

    ctx = {"session": None, "pending_email": result["email"]}
    if result["delivery"] == mail.NOT_CONFIGURED and not self_serve:
        # Never in open sign-up: showing the link to whoever typed the address
        # would skip the ownership check and differ from the existing-email page.
        ctx["dev_verify_url"] = mail.verify_url(result["verification_token"])
    elif result["delivery"] == mail.FAILED:
        ctx["send_failed"] = True
        ctx["err"] = ("We could not send the verification email right now. Use Resend in a "
                      "few minutes or contact info@grovisor.ae.")
    return render(request, "register_organization.html", ctx)

def operator_org_pending(db, org_id: int) -> bool:
    row = db.execute("SELECT plan_status FROM organizations WHERE id=?", (org_id,)).fetchone()
    return bool(row) and row["plan_status"] == "pending_payment"


@router.get("/verify-email", response_class=HTMLResponse)
@limiter.limit("10/minute")
def verify_email(request: Request, db: DB, token: str = ""):
    operator = auth.consume_email_verify_token(db, token)
    if operator is None:
        return render(request, "verify_email.html", {
            "session": None, "valid": False,
            "err": "This verification link is invalid, expired, or already used.",
        })
    from ...db import audit
    audit(db, operator["name"], "operator.email_verified", "operator", operator["id"],
          {"email": operator["email"]}, org_id=operator["org_id"])
    db.commit()

    from urllib.parse import quote

    session_token = auth.create_session(db, operator["id"], operator["org_id"])
    # create_session() only writes the sessions row -- unlike auth.login(),
    # it has no reason to audit a "login" on every call, since most callers
    # (login() itself) already do that around it. This route bypasses
    # login() entirely (no password to re-check), so without this the
    # operator's very first session would leave no audit trail entry at all.
    audit(db, operator["name"], "operator.login", "operator", operator["id"],
          None, org_id=operator["org_id"])
    db.commit()
    # p15: a brand-new MLRO must enrol now, not whenever they next log out.
    target = auth.mfa_lock_session(
        db, session_token, operator["id"], operator["role"],
        trusted_device_token=request.cookies.get(auth.TRUSTED_DEVICE_COOKIE),
    )
    if target is None and operator_org_pending(db, operator["org_id"]):
        # Self-serve sign-up: the next step is payment details, not the home page.
        target = "/billing?msg=" + quote("Email verified. Add payment details to start your 14-day trial.")
    resp = RedirectResponse(target or "/?msg=" + quote("Email verified. Welcome to groAML."),
                            status_code=303)
    _behind_proxy = os.environ.get("AMLKIT_BEHIND_PROXY") == "1"
    resp.set_cookie(SESSION_COOKIE, session_token, httponly=True, samesite="strict",
                    secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    # M-01: Rotate CSRF token on email verification (creates new session)
    resp.set_cookie(CSRF_COOKIE, auth.new_csrf_token(), httponly=True,
                    samesite="lax", secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    return resp

_UNLOCK_INVALID = "This unlock link is invalid, expired, or already used."

def _unlock_invalid_page(request: Request, db):
    return render(request, "verify_email.html", {
        "session": None, "valid": False, "heading": "Unlock your account",
        "err": _UNLOCK_INVALID,
    })

@router.get("/unlock/{token}", response_class=HTMLResponse)
# scope="unlock": one per-IP bucket for GET+POST; slowapi otherwise keys on the
# request path, which carries the token, so rotating tokens would dodge the limit.
@limiter.shared_limit("10/minute", scope="unlock")
def self_unlock_confirm(request: Request, db: DB, token: str):
    """Break-glass unlock (L-101), step 1 (CR-30): show a confirmation page. The
    GET changes nothing and does not consume the token, so a mail scanner or
    link prefetcher cannot burn or use it; the button POSTs. Every failure
    shows the same generic page so a token cannot be probed."""
    if not auth.unlock_token_is_live(db, token):
        return _unlock_invalid_page(request, db)
    return render(request, "unlock_confirm.html", {"session": None, "token": token})

@router.post("/unlock/{token}")
@limiter.shared_limit("10/minute", scope="unlock")
def self_unlock(request: Request, db: DB, token: str,
                csrf_token: Annotated[str, Form()] = ""):
    """Break-glass unlock, step 2: redeem the emailed single-use link. No
    session. Clears the password lock only, never the MFA lock."""
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(f"/unlock/{token}", err=str(exc))
    operator = auth.consume_unlock_token(db, token)
    if operator is None:
        return _unlock_invalid_page(request, db)
    from ...db import audit
    audit(db, operator["name"], "operator.self_unlock", "operator", operator["id"],
          None, org_id=operator["org_id"])
    db.commit()
    return back("/login", msg="Your account is unlocked \u2014 sign in again.")

@router.post("/resend-verification")
@limiter.limit("10/minute")
def resend_verification(
    request: Request, db: DB,
    email: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    """Always redirects to the same generic message, whether or not the
    email belongs to a real, still-unverified account -- same
    anti-enumeration reasoning as auth.login()'s single error string."""
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return _login_page_error(request, str(exc))

    generic_msg = "If that email has a pending registration, a new verification link has been sent."
    clean_email = email.strip().lower()
    row = db.execute(
        "SELECT id, org_id, name, email_verified_at FROM operators WHERE lower(email)=?",
        (clean_email,),
    ).fetchone()
    if row is not None and row["email_verified_at"] is None:
        age = auth.last_email_verify_token_age_seconds(db, row["id"])
        if age is None or age >= 60:
            from ... import mail
            from ...db import audit

            raw_token = auth.create_email_verify_token(db, row["id"])
            delivery = mail.send_verification_email(clean_email, row["name"], raw_token)
            # The response stays deliberately generic (see generic_msg) to
            # avoid confirming whether an account exists, so the audit log is
            # the only place a repeatedly-failing provider becomes visible.
            audit(db, row["name"], "operator.verification_resent", "operator", row["id"],
                  {"email": clean_email, "delivery": delivery}, org_id=row["org_id"])
            db.commit()
    return render(request, "login.html", {"session": None, "msg": generic_msg})

"""FastAPI application.

Routes are thin: they authenticate the request, collect form input, call the
existing engine functions with the session's org_id, and render. All
screening, risk, review and tenancy logic lives in `amlkit.match`,
`amlkit.cases`, `amlkit.risk`, `amlkit.auth` and `amlkit.db` -- duplicating
any of it here would create a second implementation that tests do not cover.

Every route that reads or writes tenant data resolves a session first and
passes `session.org_id` into the library call. There is no route that skips
this: `queries.py` and the write-path functions in `cases`/`match`/`risk`
require `org_id` as a mandatory argument, so a route that forgot to check the
session would fail to even construct the call, not silently query across
every tenant.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, Request, UploadFile
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import FormData
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .. import auth, queries
from .limits import limiter
from ..cases.manager import (
    ADVERSE_MEDIA_BATCH_LIMIT,
    StaleDatasetsError,
    add_case_note,
    add_ubo,
    close_relationship,
    reactivate_customer,
    disposition_adverse_media_finding,
    disposition_transaction_alert,
    onboard,
    record_signature,
    record_transaction,
    run_adverse_media,
    run_due_adverse_media,
)
from ..cases.review import (
    REASON_CODES,
    ReviewError,
    assign_alert,
    bulk_dismiss_alerts,
    confirm_disposition,
    propose_disposition,
    review_history,
    single_operator_mode,
)
from ..db import retry_on_lock, set_org_alert_threshold, utcnow
from ..match.engine import DEFAULT_THRESHOLD, screen
from ..names.arabic import has_arabic_script
from ..risk.model import ruleset
from ..screening.adverse_media import ATTRIBUTION as GDELT_ATTRIBUTION, DEFAULT_WINDOW_MONTHS
from .csv_utils import _escape_csv_formula
from .deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    client_ip,
    current_session,
    db_path,
    get_db,
    require_csrf,
    require_role,
    require_session,
    startup_warning,
)

WEB = Path(__file__).resolve().parent.parent / "web"

# ---------------------------------------------------------------------- scheduler
import contextlib
import logging
import os
import secrets
import uuid

from ..cases.scheduler import check_and_notify_staleness, run_sanctions_refresh

log = logging.getLogger("amlkit.scheduler")


def _run_scheduled_refresh() -> None:
    """APScheduler entry point: opens its own connection (not tied to a
    request) and delegates to run_sanctions_refresh.

    This in-process scheduler is the RIGHT mechanism when amlkit runs on a
    compliance officer's own machine, per its core design (see db.py's
    module docstring) -- a long-lived local process has no scale-to-zero
    surprises. It is the WRONG (unreliable) mechanism on Cloud Run, where
    the container can be frozen or killed between requests regardless of
    in-process timers -- that deployment relies on Cloud Scheduler calling
    /system/refresh instead (see .github/workflows/source-canary.yml's
    Cloud Scheduler wiring).
    Kept enabled unconditionally rather than detecting the environment: it
    is a harmless, idempotent-ish extra refresh if it ever does fire
    alongside Cloud Scheduler's call, never a correctness risk.
    """
    from ..db import connect

    log.info("Scheduled sanctions refresh starting…")
    conn = None
    try:
        conn = connect(db_path())
        result = run_sanctions_refresh(conn, actor="scheduler")
        log.info("Scheduled refresh complete: %s", result)

        # Audit the scheduled refresh so MLROs can see automated actions
        from ..db import audit
        audit(conn, "scheduler", "system.scheduled_refresh", details={
            "orgs_screened": result["orgs_screened"],
            "new_alerts": result["new_alerts"],
            "datasets_loaded": len(result["loaded"]),
            "failures": result["failures"]
        }, org_id=None)
        conn.commit()

        # Check for staleness and notify MLROs if needed
        staleness_result = check_and_notify_staleness(conn)
        log.info("Staleness check complete: %s", staleness_result)
    except Exception:
        log.exception("Scheduled sanctions refresh failed with an unexpected error")
    finally:
        if conn is not None:
            conn.close()


@contextlib.asynccontextmanager
async def _lifespan(app):
    """Start the 23-hour refresh scheduler when the container boots.

    Also initializes structured JSON logging with request-ID correlation.

    Cloud Run may scale to zero (killing the scheduler) when idle for long
    periods. The /system/refresh endpoint below provides a reliable fallback
    that Cloud Scheduler can call via HTTP even after a cold start.

    Skipped entirely when AMLKIT_BEHIND_PROXY=1 (Cloud Run): the eager
    next_run_time=datetime.now() below means this fired run_sanctions_refresh()
    -- six external network fetches plus a full re-screen of every active
    org's entire customer book -- on every cold start, on the same
    single-vCPU instance that was simultaneously trying to serve the request
    that caused that cold start. With min-instances=0 a cold start happens on
    most session gaps, so in practice this meant most testers' first request
    of a session raced a multi-source ingest+rescreen job for CPU, network,
    and SQLite write locks. Cloud Scheduler's daily call to /system/refresh
    already covers the 24-hour rule reliably here (see
    .github/workflows/source-canary.yml) and runs as one ordinary request at
    a controlled time instead of unpredictably stacking onto whichever
    request happens to cold-start the container.
    """
    from ..logging_config import configure_logging
    configure_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
    # p53: APScheduler removed. Use Cloud Scheduler to call /system/refresh.
    # In-process background scheduling doesn't survive Cloud Run scale-to-zero,
    # and adds unnecessary complexity. External cron (Cloud Scheduler, systemd
    # timer, or similar) calling /system/refresh is more reliable.
    if os.environ.get("AMLKIT_DISABLE_AUTO_REFRESH") != "1":
        log.info("Auto-refresh via /system/refresh endpoint (call from Cloud Scheduler).")
    yield


# N001: Disable OpenAPI by default unless explicitly enabled
_openapi_url = "/openapi.json" if os.getenv("AMLKIT_ENABLE_OPENAPI") == "1" else None

app = FastAPI(title="amlkit", docs_url=None, redoc_url=None, openapi_url=_openapi_url, lifespan=_lifespan)

# Issue #102: Flash messages via signed cookies (no itsdangerous dependency)
# Uses the same signing mechanism as CSRF tokens
_FLASH_COOKIE = "amlkit_flash"

# Rate limiting to prevent brute-force attacks and DoS


def rate_limit_key_func(request: Request) -> str:
    """Rate limiter key: real client IP, respecting X-Forwarded-For behind proxy.

    Without this, Cloud Run / nginx proxies cause all requests to share one
    link-local IP, so every tenant lands in the same rate-limit bucket.
    Only trusts X-Forwarded-For when AMLKIT_BEHIND_PROXY=1.
    """
    from .deps import client_ip
    return client_ip(request) or "unknown"


def login_rate_limit_key(request: Request) -> str:
    """Composite rate limit key for login: IP + email.

    Allows multiple operators from the same office IP/NAT to log in concurrently
    (each account gets its own 3/minute budget) while still protecting each
    account from credential-stuffing attempts.

    Reads the email from request.state.login_email, which is set by middleware.
    """
    ip = rate_limit_key_func(request)
    email = getattr(request.state, 'login_email', None)
    if email:
        return f"{ip}:{email.lower().strip()}"
    return ip


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# JSON API for the native mobile app -- bearer-token auth, no CSRF, no HTML.
# Registered before the static mount so /api/v1/* never falls through to it.
from .mobile import router as mobile_router  # noqa: E402

app.include_router(mobile_router)

app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")
templates = Jinja2Templates(directory=str(WEB / "templates"))
templates.env.globals["has_arabic"] = has_arabic_script


async def _async_form(request: Request) -> FormData:
    """Async dependency to read request form data.

    Allows sync routes to use DB connections (avoiding threading issues)
    while still reading async form data with dynamic fields.
    """
    return await request.form()


DB = Annotated[sqlite3.Connection, Depends(get_db)]

# Cookie lifetime for the CSRF token mirrors the session's: no point in one
# outliving the other.
_COOKIE_MAX_AGE = int(auth.SESSION_LIFETIME.total_seconds())


def render(request: Request, name: str, ctx: dict, db: sqlite3.Connection | None = None) -> HTMLResponse:
    """Render with the context every page needs, including a fresh CSRF token
    for any form on the page.

    The CSRF token is set BOTH in the template context (for the hidden form
    field) AND as a cookie on the response. Both must use the same value —
    using the existing cookie value if present, or generating one new token
    that is written to both places at once. Generating one token for the form
    and a separate one for the cookie (as a middleware would) causes every
    first-visit form submission to fail the CSRF check.
    """
    session = ctx.get("session")
    if session is None and db is not None:
        session = current_session(request, db)
    ctx.setdefault("session", session)
    ctx.setdefault("security_warning", startup_warning())
    ctx.setdefault("single_operator", single_operator_mode())
    # Read flash message from cookie (Issue #102) with URL param fallback.
    # Cookie value is base64-encoded JSON to avoid HTTP quoting of {/"/} chars.
    import json as _json
    import base64 as _b64
    _flash_raw = request.cookies.get(_FLASH_COOKIE)
    _flash_msg = _flash_err = ""
    if _flash_raw:
        try:
            _flash = _json.loads(_b64.b64decode(_flash_raw.encode()).decode())
            if _flash.get("type") == "msg":
                _flash_msg = _flash.get("text", "")
            elif _flash.get("type") == "err":
                _flash_err = _flash.get("text", "")
        except Exception:
            pass
    ctx.setdefault("msg", _flash_msg or request.query_params.get("msg"))
    ctx.setdefault("err", _flash_err or request.query_params.get("err"))

    # Check dataset health for authenticated sessions
    if session and db is not None:
        banner = queries.dataset_health_banner(db)
        ctx.setdefault("dataset_banner", banner)

    # Inject organization name for authenticated sessions
    if session:
        ctx.setdefault("org_name", session.org_name)

    # Use the cookie value if already present; otherwise mint one token that
    # goes into BOTH the form field AND the cookie on this same response.
    existing = request.cookies.get(CSRF_COOKIE)
    token = existing or auth.new_csrf_token()
    ctx.setdefault("csrf_token", token)

    resp = templates.TemplateResponse(request, name, ctx)
    if _flash_raw:
        resp.delete_cookie(_FLASH_COOKIE)
    if not existing:
        _behind_proxy = os.environ.get("AMLKIT_BEHIND_PROXY") == "1"
        resp.set_cookie(
            CSRF_COOKIE, token,
            httponly=True,
            samesite="lax",
            secure=_behind_proxy,
            max_age=_COOKIE_MAX_AGE,
        )
    return resp


def _safe_url(url: str) -> str:
    """Return a safe same-origin path extracted from url, or '/' as fallback.

    Rejects any URL that has a scheme or netloc (open-redirect vector), then
    re-encodes the path via urllib.parse.quote to produce a new string that is
    not tainted by the original user input (breaks CodeQL's taint chain).
    """
    from urllib.parse import urlparse, quote
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc:
        return "/"
    path = parsed.path
    if not path.startswith("/") or path.startswith("//"):
        return "/"
    # quote() produces a fresh string independent of the user-supplied value,
    # preserving valid path/query characters while encoding everything else.
    return quote(path, safe="/:@!$&'()*+,;=-._~%")


def back(url: str, msg: str = "", err: str = "") -> RedirectResponse:
    """Redirect without exposing messages in URL (Issue #102).

    Previously appended msg/err as URL query params, exposing sensitive auth
    errors in browser history and server logs. Now stores them in a short-lived
    flash cookie consumed by render() on the next page load.
    """
    resp = RedirectResponse(_safe_url(url), status_code=303)
    if msg or err:
        set_flash_cookie(resp, msg=msg, err=err)
    return resp


def set_flash_cookie(response: Response, msg: str = "", err: str = ""):
    """Store flash message in signed cookie for one-time display after redirect.

    The flash cookie is consumed (deleted) on first read, ensuring messages
    appear exactly once.  Value is base64-encoded JSON so the cookie contains
    only safe characters and avoids HTTP quoting of { / " / } which causes
    JSONDecodeError when the quoted value is read back with backslash escapes.
    """
    import json, base64
    if msg:
        raw = json.dumps({"type": "msg", "text": msg})
        flash_data = base64.b64encode(raw.encode()).decode()
        response.set_cookie(_FLASH_COOKIE, flash_data, max_age=60, httponly=True,
                           samesite="lax", secure=os.environ.get("AMLKIT_BEHIND_PROXY") == "1")
    elif err:
        raw = json.dumps({"type": "err", "text": err})
        flash_data = base64.b64encode(raw.encode()).decode()
        response.set_cookie(_FLASH_COOKIE, flash_data, max_age=60, httponly=True,
                           samesite="lax", secure=os.environ.get("AMLKIT_BEHIND_PROXY") == "1")


def _set_csrf_cookie(resp, request: Request) -> None:
    """Ensure every response carries a CSRF cookie, issuing one if absent.

    secure=True is required on Cloud Run (HTTPS). Without it, modern browsers
    silently drop the cookie on HTTPS pages, causing every form submission to
    fail the CSRF check with "stale page" even on a fresh load.

    samesite="lax" (not strict) allows the cookie to survive navigating to the
    login page from an external link or bookmark -- strict would drop it on the
    very first GET, which is the most common path for a new user.
    """
    if not request.cookies.get(CSRF_COOKIE):
        _behind_proxy = os.environ.get("AMLKIT_BEHIND_PROXY") == "1"
        resp.set_cookie(CSRF_COOKIE, auth.new_csrf_token(), httponly=True,
                        samesite="lax", secure=_behind_proxy,
                        max_age=_COOKIE_MAX_AGE)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Generate a unique request ID for correlation and attach it to the response."""
    request_id = str(uuid.uuid4())
    from ..logging_config import set_request_id, clear_request_id
    set_request_id(request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        clear_request_id()


@app.middleware("http")
async def extract_login_email(request: Request, call_next):
    """Extract email from login POST requests for rate limiting.

    This runs before the rate limiter, allowing the rate limit key function to
    access the email synchronously via request.state.login_email.

    We read the raw body and manually parse the email without consuming the
    stream, ensuring the route handler can still access the form data.
    """
    if request.method == "POST" and request.url.path == "/login":
        try:
            # Read the raw body first (this caches it in request._body)
            body = await request.body()
            # Parse email manually without consuming the form stream
            from urllib.parse import parse_qs
            body_str = body.decode('utf-8') if isinstance(body, bytes) else str(body)
            parsed = parse_qs(body_str)
            email = parsed.get('email', [''])[0]
            if email:
                request.state.login_email = email.strip()
        except Exception:
            # If body reading/parsing fails, fall back to IP-only rate limiting
            pass
    response = await call_next(request)
    return response


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add security headers to all responses.

    - CSP: Restricts resource loading to same-origin, with 'unsafe-inline' for
      scripts/styles since the templates use inline <script> blocks and onclick
      handlers. Still protects against loading scripts from unauthorized domains.
    - X-Content-Type-Options: Prevents MIME-sniffing attacks
    - X-Frame-Options: Prevents clickjacking
    - HSTS: Forces HTTPS in production (when AMLKIT_BEHIND_PROXY=1)
    """
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "  # All inline scripts migrated to external files (Issue #82)
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    # HSTS only on HTTPS (production behind proxy)
    if os.environ.get("AMLKIT_BEHIND_PROXY") == "1":
        # 1 year HSTS, includeSubDomains
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ----------------------------------------------------------------- health
@app.get("/health")
def health_check(db: DB):
    from fastapi.responses import JSONResponse
    from ..ingest.loader import staleness_report
    # N002: Public /health returns status (healthy/degraded) but not dataset details.
    # Degraded = mandatory list breach (compliance signal for Cloud Run probes).
    # Details moved to /admin/compliance (auth-required).
    datasets = staleness_report(db)
    any_breach = any(d["breach"] for d in datasets)
    return JSONResponse({
        "status": "degraded" if any_breach else "healthy",
    })


# ----------------------------------------------------------------- sign-in
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, db: DB):
    # A locked MLRO session bounced here by require_session() belongs on the
    # MFA challenge, not on the password form it has already passed.
    pending = auth.mfa_session_state(db, request.cookies.get(SESSION_COOKIE))
    if pending and pending["role"] == "mlro" and not pending["mfa_verified"]:
        return RedirectResponse(auth.mfa_challenge_path(db, pending["operator_id"]), status_code=303)
    return render(request, "login.html", {"session": None})


def _login_page_error(request: Request, message: str) -> HTMLResponse:
    return render(request, "login.html", {"session": None, "err": message})


@app.post("/login")
@limiter.limit("10/minute")  # IP ceiling: prevents brute force attacks from single IP
@limiter.limit("3/minute", key_func=login_rate_limit_key)  # Per-account: prevents rapid stuffing of one account
def login_submit(
    request: Request, db: DB,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return _login_page_error(request, str(exc))
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
    target = auth.mfa_lock_session(db, token, info.operator_id, info.operator_role) or "/"

    resp = RedirectResponse(target, status_code=303)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict",
                    secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    # M-01: Rotate CSRF token on login (defence-in-depth)
    resp.set_cookie(CSRF_COOKIE, auth.new_csrf_token(), httponly=True,
                    samesite="lax", secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    return resp


@app.post("/logout")
def logout_submit(request: Request, db: DB):
    session = current_session(request, db)
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        auth.logout(db, token, session, ip=client_ip(request))
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp




@app.get("/account/password")
def password_change_form(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    return render(request, "password_change.html", {"session": session, "nav": None})


@app.post("/account/password")
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

    # Validate password complexity
    try:
        auth.validate_password_complexity(new_password)
    except auth.PasswordComplexityError as exc:
        return render(request, "password_change.html", {
            "session": session, "nav": None, "err": str(exc)
        })

    # Update password
    auth.set_password(db, session.operator_id, new_password)
    
    from ..db import audit
    audit(db, session.operator_name, "operator.password_changed", "operator", session.operator_id,
          None, org_id=session.org_id)
    db.commit()

    return back("/", msg="Password changed successfully. All other sessions have been signed out.")


@app.get("/mfa/verify", response_class=HTMLResponse)
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


@app.post("/mfa/verify")
@limiter.limit("5/minute")  # per IP; auth.mfa_check_code() adds the per-operator lockout
def mfa_verify_submit(
    request: Request, db: DB,
    code: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
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
        return RedirectResponse("/", status_code=303)
    if outcome == "locked":
        return back("/mfa/verify", err=_MFA_LOCKED_MESSAGE)
    return back("/mfa/verify", err="Invalid verification code. Please try again.")


_MFA_LOCKED_MESSAGE = ("Too many failed codes. Two-factor sign-in is locked for 15 minutes; "
                       "the attempts have been recorded in the audit trail.")


@app.get("/mfa/setup", response_class=HTMLResponse)
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


@app.post("/mfa/setup")
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
        from ..db import audit
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


@app.post("/mfa/disable")
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
    if not totp_code or not auth.mfa_verify(db, session.operator_id, totp_code):
        return back("/account", err="Enter a valid TOTP code to disable MFA.")

    # Disable MFA
    db.execute("DELETE FROM mfa_secrets WHERE operator_id=?", (session.operator_id,))
    db.execute("DELETE FROM mfa_backup_codes WHERE operator_id=?", (session.operator_id,))
    db.commit()

    from ..db import audit
    audit(db, session.operator_name, "operator.mfa_disabled", "operator", session.operator_id,
          None, org_id=session.org_id)

    return back("/account", msg="Two-factor authentication has been disabled.")


@app.post("/acknowledge-disclaimer")
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


@app.get("/setup", response_class=HTMLResponse)
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


@app.post("/setup")
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

    from ..cases.operators import complete_initial_setup

    try:
        result = complete_initial_setup(db, token, name, email, password)
    except ValueError as exc:
        return render(request, "setup.html", {
            "session": None, "valid": False, "err": str(exc),
        })

    session_token, info = auth.login(db, result["email"], password, ip=client_ip(request))
    # p15: the first operator is the MLRO, so this session starts locked too.
    target = auth.mfa_lock_session(db, session_token, info.operator_id, info.operator_role) or "/"
    resp = RedirectResponse(target, status_code=303)
    _behind_proxy = os.environ.get("AMLKIT_BEHIND_PROXY") == "1"
    resp.set_cookie(SESSION_COOKIE, session_token, httponly=True, samesite="strict",
                    secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    resp.set_cookie(CSRF_COOKIE, auth.new_csrf_token(), httponly=True,
                    samesite="lax", secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    return resp




@app.get("/register-organization", response_class=HTMLResponse)
def register_org_form(request: Request, db: DB):
    invite_configured = bool(os.environ.get("AMLKIT_REGISTRATION_INVITE_CODE", "").strip())
    return render(request, "register_organization.html", {
        "session": None, "registration_open": invite_configured,
    })


@app.post("/register-organization")
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
        })

    expected = os.environ.get("AMLKIT_REGISTRATION_INVITE_CODE", "").strip()
    if not expected or not secrets.compare_digest(invite_code.strip().encode(), expected.encode()):
        auth._log_auth_event(db, "register_denied", email.strip().lower(),
                             {"reason": "invalid_invite_code", "via": "web"})
        db.commit()
        return render(request, "register_organization.html", {
            "session": None, "registration_open": bool(expected), "err": "Invalid invite code.",
        })

    from ..cases.operators import register_organization
    from .. import mail

    try:
        result = register_organization(db, org_name, name, email, password)
    except ValueError as exc:
        return render(request, "register_organization.html", {"session": None, "err": str(exc)})

    ctx = {
        "session": None,
        "pending_email": result["email"],
        "msg": f"Account created. Check {result['email']} for a verification link before signing in.",
    }
    if result["delivery"] == mail.NOT_CONFIGURED:
        ctx["dev_verify_url"] = mail.verify_url(result["verification_token"])
    elif result["delivery"] == mail.FAILED:
        ctx["msg"] = (
            f"Account created, but the verification email to {result['email']} "
            "could not be sent. The mail service is not responding — ask your "
            "administrator to check it, then use the resend link below."
        )
        ctx["err"] = "Verification email could not be sent."
    return render(request, "register_organization.html", ctx)


@app.get("/verify-email", response_class=HTMLResponse)
@limiter.limit("10/minute")
def verify_email(request: Request, db: DB, token: str = ""):
    operator = auth.consume_email_verify_token(db, token)
    if operator is None:
        return render(request, "verify_email.html", {
            "session": None, "valid": False,
            "err": "This verification link is invalid, expired, or already used.",
        })
    from ..db import audit
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
    target = auth.mfa_lock_session(db, session_token, operator["id"], operator["role"])
    resp = RedirectResponse(target or "/?msg=" + quote("Email verified. Welcome to amlkit."),
                            status_code=303)
    _behind_proxy = os.environ.get("AMLKIT_BEHIND_PROXY") == "1"
    resp.set_cookie(SESSION_COOKIE, session_token, httponly=True, samesite="strict",
                    secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    # M-01: Rotate CSRF token on email verification (creates new session)
    resp.set_cookie(CSRF_COOKIE, auth.new_csrf_token(), httponly=True,
                    samesite="lax", secure=_behind_proxy, max_age=_COOKIE_MAX_AGE)
    return resp


@app.post("/resend-verification")
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
            from .. import mail
            from ..db import audit

            raw_token = auth.create_email_verify_token(db, row["id"])
            delivery = mail.send_verification_email(clean_email, row["name"], raw_token)
            # The response stays deliberately generic (see generic_msg) to
            # avoid confirming whether an account exists, so the audit log is
            # the only place a repeatedly-failing provider becomes visible.
            audit(db, row["name"], "operator.verification_resent", "operator", row["id"],
                  {"email": clean_email, "delivery": delivery}, org_id=row["org_id"])
            db.commit()
    return render(request, "login.html", {"session": None, "msg": generic_msg})


# ------------------------------------------------------------------ freeze obligations

@app.get("/freeze-obligations", response_class=HTMLResponse)
def freeze_obligations_list_route(request: Request, db: DB):
    """List all freeze obligations for current org."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)

    filter_status = request.query_params.get("status", "all")
    obligations = queries.freeze_obligations_list(db, session.org_id, filter_status)
    stats = queries.freeze_obligations_stats(db, session.org_id)

    return render(request, "freeze_obligations.html", {
        "session": session,
        "obligations": obligations,
        "filter_status": filter_status,
        "stats": stats,
    })

@app.get("/freeze-obligations/{freeze_id}", response_class=HTMLResponse)
def freeze_obligation_detail_route(request: Request, db: DB, freeze_id: int):
    """Show freeze obligation details with full lifecycle timeline."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)

    obligation = queries.freeze_obligation_detail(db, session.org_id, freeze_id)
    if not obligation:
        return back("/freeze-obligations", err="Freeze obligation not found")

    can_execute = obligation["status"] == "pending_execution"
    can_file_ffr = obligation["status"] == "executed_pending_report"
    can_resolve = obligation["status"] in ["executed_pending_report", "reported"]
    
    return render(request, "freeze_obligation_detail.html", {
        "session": session,
        "obligation": obligation,
        "can_execute": can_execute,
        "can_file_ffr": can_file_ffr,
        "can_resolve": can_resolve,
    })

@app.post("/freeze-obligations/{freeze_id}/execute")
def freeze_obligation_execute(request: Request, db: DB, freeze_id: int, form: Annotated[FormData, Depends(_async_form)]):
    """Execute freeze obligation - mark as executed with assets frozen."""
    try:
        session = require_session(request, db)
        csrf_token = form.get("csrf_token", "")
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(f"/freeze-obligations/{freeze_id}", err=str(exc))

    if session.operator_role != "mlro":
        return back(f"/freeze-obligations/{freeze_id}", err="Execute freeze requires MLRO role")

    from ..cases import freeze as freeze_ops, manager
    assets_frozen = freeze_ops.parse_freeze_assets_from_form(form)

    try:
        manager.execute_freeze(
            db,
            freeze_id,
            org_id=session.org_id,
            executed_by=session.operator_name,
            assets_frozen=assets_frozen,
            notes=form.get("notes", "")
        )
    except ValueError as exc:
        return back(f"/freeze-obligations/{freeze_id}", err=str(exc))

    return back(f"/freeze-obligations/{freeze_id}", msg="Freeze executed successfully.")

@app.post("/freeze-obligations/{freeze_id}/file-ffr")
def freeze_obligation_file_ffr(request: Request, db: DB, freeze_id: int, form: Annotated[FormData, Depends(_async_form)]):
    """Create FFR report from freeze obligation."""
    try:
        session = require_session(request, db)
        csrf_token = form.get("csrf_token", "")
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(f"/freeze-obligations/{freeze_id}", err=str(exc))

    if session.operator_role != "mlro":
        return back(f"/freeze-obligations/{freeze_id}", err="File FFR requires MLRO role")

    from ..cases import freeze as freeze_ops
    reporter_name = form.get("reporter_name") or session.operator_name
    reporter_email = form.get("reporter_email", "")

    try:
        report_id = freeze_ops.file_ffr_report(
            db,
            freeze_id,
            session.org_id,
            reporter_name,
            reporter_email,
            session.operator_name
        )
    except ValueError as exc:
        return back(f"/freeze-obligations/{freeze_id}", err=str(exc))

    return RedirectResponse(f"/reports/{report_id}", status_code=303)

@app.post("/freeze-obligations/{freeze_id}/resolve")
def freeze_obligation_resolve(request: Request, db: DB, freeze_id: int, form: Annotated[FormData, Depends(_async_form)]):
    """Resolve (close) freeze obligation."""
    try:
        session = require_session(request, db)
        csrf_token = form.get("csrf_token", "")
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(f"/freeze-obligations/{freeze_id}", err=str(exc))

    if session.operator_role != "mlro":
        return back(f"/freeze-obligations/{freeze_id}", err="Resolve freeze requires MLRO role")

    operator = session.operator_name

    resolution_reason = form.get("resolution_reason")
    authority_ref = form.get("authority_ref", "")
    notes = form.get("notes", "")
    
    from ..cases import manager
    try:
        manager.resolve_freeze_obligation(
            db,
            freeze_id,
            org_id=session.org_id,
            resolved_by=operator,
            resolution_reason=resolution_reason,
            authority_ref=authority_ref,
            notes=notes
        )
    except ValueError as exc:
        return back(f"/freeze-obligations/{freeze_id}", err=str(exc))

    return back(f"/freeze-obligations/{freeze_id}", msg="Obligation resolved successfully.")

# ------------------------------------------------------------------ home
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: DB):
    """The first screen after sign-in -- an orientation page, not the
    dashboard. A new or occasional operator needs "what do I do" before
    "what's outstanding"; the dashboard (queue/stale-list detail) is one
    click away via the nav or the alerts bar below, not buried."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)

    from datetime import datetime, timedelta, timezone

    # Gulf Standard Time, fixed UTC+4 (no DST) -- the app is UAE-only and
    # this greeting is cosmetic, so a fixed offset avoids a per-operator
    # timezone setting that nothing else in the schema has either.
    gst_now = datetime.now(timezone.utc) + timedelta(hours=4)
    if gst_now.hour < 12:
        greeting = "Good morning"
    elif gst_now.hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    first_name = (session.operator_name or "").split()
    first_name = first_name[0] if first_name else session.operator_name

    return render(request, "home.html", {
        "session": session,
        "d": queries.dashboard(db, session.org_id),
        "contextual_card": queries.contextual_home_card(db, session.org_id),
        "greeting": greeting,
        "first_name": first_name,
        "today": gst_now.strftime("%A, %d %B %Y"),
    }, db)


# ------------------------------------------------------------------ dashboard
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    return render(request, "dashboard.html", {
        "session": session,
        "d": queries.dashboard(db, session.org_id),
        "datasets": queries.datasets(db),
    }, db)


# --------------------------------------------------------------------- screen
@app.get("/screen", response_class=HTMLResponse)
def screen_form(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    return render(request, "screen.html", {"session": session, "result": None, "query": ""}, db)


@app.post("/screen", response_class=HTMLResponse)
@limiter.limit("10/minute")
def screen_run(
    request: Request, db: DB,
    name: Annotated[str, Form()],
    country: Annotated[str, Form()] = "",
    birth_date: Annotated[str, Form()] = "",
    gender: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return render(request, "screen.html", {"session": session, "result": None, "query": name, "err": str(exc)}, db)

    name = name.strip()
    if not name:
        return render(request, "screen.html",
                      {"session": session, "result": None, "query": "", "err": "Enter a name to screen."}, db)

    result = screen(
        db, name, org_id=session.org_id, trigger="adhoc",
        threshold=queries.org_alert_threshold(db, session.org_id) or DEFAULT_THRESHOLD,
        country=country.strip() or None,
        birth_date=birth_date.strip() or None,
        gender=gender.strip() or None,
        actor=session.operator_name,
    )
    hits = []
    for h in result.hits:
        hits.append({
            "score": h.score, "caption": h.caption, "dataset": h.dataset,
            "schema_type": h.schema_type, "matched_name": h.matched_name,
            "category": ("proliferation" if h.is_proliferation
                         else "terrorism" if h.is_terrorism
                         else "sanction" if h.is_sanction else "other"),
            "obligation": h.obligation, "programs": h.programs,
            "detail": h.detail, "entity_id": h.entity_id,
            "aliases": queries.entity_names(db, h.entity_id),
        })
    return render(request, "screen.html", {
        "session": session, "query": name, "result": result, "hits": hits,
        "low_confidence": len(name.split()) < 2,
    }, db)


# ------------------------------------------------------------------ customers
@app.get("/customers", response_class=HTMLResponse)
def customers(request: Request, db: DB, q: str = ""):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    if q.strip():
        results = queries.search_customers(db, session.org_id, q)
    else:
        results = queries.customer_list(db, session.org_id)
    return render(request, "customers.html",
                 {"session": session, "customers": results, "search_query": q}, db)


@app.get("/customers/new", response_class=HTMLResponse)
def customer_new(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    rs = ruleset()
    return render(request, "customer_new.html", {
        "session": session,
        "sectors": sorted(rs["factors"]["sector"]["points_by_sector"]),
        "channels": sorted(rs["factors"]["delivery_channel"]["points_by_channel"]),
        "structures": sorted(rs["factors"]["structure"]["points_by_type"]),
        "tiers": sorted(rs["factors"]["jurisdiction"]["points_by_tier"]),
    })


@app.post("/customers")
def customer_create(
    request: Request, db: DB,
    reference: Annotated[str, Form()],
    full_name: Annotated[str, Form()],
    customer_type: Annotated[str, Form()] = "natural",
    name_arabic: Annotated[str, Form()] = "",
    nationality: Annotated[str, Form()] = "",
    birth_date: Annotated[str, Form()] = "",
    gender: Annotated[str, Form()] = "",
    trade_licence: Annotated[str, Form()] = "",
    sector: Annotated[str, Form()] = "other",
    delivery_channel: Annotated[str, Form()] = "face_to_face",
    cash_level: Annotated[str, Form()] = "non_cash",
    jurisdiction_tier: Annotated[str, Form()] = "standard",
    structure: Annotated[str, Form()] = "natural_person",
    ubo_names: Annotated[list[str], Form()] = [],
    ubo_pcts: Annotated[list[str], Form()] = [],
    ubo_controls: Annotated[list[str], Form()] = [],
    purpose_of_relationship: Annotated[str, Form()] = "",
    expected_activity: Annotated[str, Form()] = "",
    risk_level: Annotated[str, Form()] = "",
    source_of_wealth: Annotated[str, Form()] = "",
    source_of_funds: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back("/customers/new", err=str(exc))

    # Validate EDD fields for high-risk customers (at onboarding, use declared risk_level)
    if risk_level and risk_level.strip() == "high":
        if not source_of_wealth or not source_of_wealth.strip():
            return back("/customers/new", err="Source of Wealth is required for high-risk customers")
        if not source_of_funds or not source_of_funds.strip():
            return back("/customers/new", err="Source of Funds is required for high-risk customers")

    ubos = []
    for i, nm in enumerate(ubo_names):
        nm = (nm or "").strip()
        if not nm:
            continue
        pct_raw = ubo_pcts[i] if i < len(ubo_pcts) else ""
        try:
            pct = float(pct_raw) if str(pct_raw).strip() else None
        except ValueError:
            pct = None

        # Validate ownership percentage is in valid range
        if pct is not None and not (0 <= pct <= 100):
            return back("/customers/new", err=f"UBO ownership percentage must be between 0 and 100, got {pct}")

        ubos.append({
            "person_name": nm,
            "ownership_pct": pct,
            "control_type": (ubo_controls[i] if i < len(ubo_controls) else "ownership") or "ownership",
        })

    try:
        result = onboard(
            db, org_id=session.org_id, reference=reference.strip(), full_name=full_name.strip(),
            customer_type=customer_type, name_arabic=name_arabic.strip() or None,
            nationality=nationality.strip() or None, birth_date=birth_date.strip() or None,
            gender=gender.strip() or None, trade_licence=trade_licence.strip() or None,
            sector=sector, delivery_channel=delivery_channel, cash_level=cash_level,
            jurisdiction_tier=jurisdiction_tier, structure=structure,
            purpose_of_relationship=purpose_of_relationship.strip() or None,
            expected_activity=expected_activity.strip() or None,
            risk_level=risk_level.strip() or None,
            source_of_wealth=source_of_wealth.strip() or None,
            source_of_funds=source_of_funds.strip() or None,
            ubos=ubos, actor=session.operator_name,
            threshold=queries.org_alert_threshold(db, session.org_id) or DEFAULT_THRESHOLD,
        )
    except StaleDatasetsError as exc:
        return back("/customers/new", err=str(exc))
    except ValueError as exc:
        return back("/customers/new", err=str(exc))
    except sqlite3.IntegrityError:
        return back("/customers/new", err=f"Reference {reference!r} already exists.")

    note = (
        "Onboarded. MATCH FOUND - see alerts, freeze without delay and do not tip off."
        if result.blocked else
        f"Onboarded. Risk rating: {result.risk.rating}."
    )
    return back(f"/customers/{result.customer_id}", msg=note)


@app.post("/customers/scan-passport")
def customer_scan_passport(
    request: Request, db: DB,
    passport_file: UploadFile,
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail=str(exc))

    import io
    from ..cases.ocr import extract_passport_data

    try:
        content = passport_file.file.read()
        file_like = io.BytesIO(content)
        data = extract_passport_data(file_like)
        return data
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/customers/{customer_id}", response_class=HTMLResponse)
def customer_detail(request: Request, db: DB, customer_id: int):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    data = queries.customer(db, customer_id, session.org_id)
    if data is None:
        return back("/customers", err=f"Customer {customer_id} not found.")
    from ..cases.diagram import generate_ubo_diagram
    diagram_svg = generate_ubo_diagram(db, customer_id, session.org_id)
    for alert in data["alerts"]:
        alert["reviews"] = review_history(db, alert["id"], session.org_id)
    eff_risk = queries.effective_risk(db, customer_id, session.org_id)
    return render(request, "customer.html",
                 data | {"session": session, "reason_codes": REASON_CODES, "ubo_diagram": diagram_svg,
                         "effective_risk": eff_risk})


@app.get("/customers/{customer_id}/evidence", response_class=HTMLResponse)
def evidence_pack(request: Request, db: DB, customer_id: int):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    data = queries.customer(db, customer_id, session.org_id)
    if data is None:
        return back("/customers", err=f"Customer {customer_id} not found.")
    for alert in data["alerts"]:
        alert["reviews"] = review_history(db, alert["id"], session.org_id)
    eff_risk = queries.effective_risk(db, customer_id, session.org_id)
    return render(request, "evidence.html", data | {"session": session, "generated_at": utcnow(),
                                                     "effective_risk": eff_risk}, db)


@app.get("/customers/{customer_id}/gdelt-bq")
def customer_gdelt_bq(request: Request, db: DB, customer_id: int):
    from fastapi.responses import JSONResponse
    try:
        session = require_session(request, db)
    except PermissionError:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    cust = queries.customer(db, customer_id, session.org_id)
    if not cust:
        return JSONResponse({"error": "not found"}, status_code=404)

    from ..screening.gdelt_bq import GdeltBqScreener
    screener = GdeltBqScreener()
    result = screener.screen(cust["customer"]["full_name"])

    from dataclasses import asdict
    return JSONResponse(asdict(result))


@app.get("/customers/{customer_id}/kg-screen")
def customer_kg_screen(request: Request, db: DB, customer_id: int):
    from fastapi.responses import JSONResponse
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    cust = queries.customer(db, customer_id, session.org_id)
    if cust is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    from ..screening.knowledge_graph import KnowledgeGraphScreener
    from dataclasses import asdict
    screener = KnowledgeGraphScreener()
    result = screener.screen(cust["customer"]["full_name"])
    return JSONResponse(asdict(result))


@app.post("/customers/{customer_id}/close")
def customer_close(request: Request, db: DB, customer_id: int,
                   csrf_token: Annotated[str, Form()] = ""):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    until = close_relationship(db, customer_id, org_id=session.org_id, actor=session.operator_name)
    return back(f"/customers/{customer_id}", msg=f"Relationship closed. Records retained until {until}.")


@app.post("/customers/{customer_id}/reactivate")
def customer_reactivate(
    request: Request, db: DB, customer_id: int,
    reason: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    try:
        require_role(session, "mlro")
    except PermissionError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    try:
        reactivate_customer(db, customer_id, org_id=session.org_id,
                            reason=reason.strip() or "No reason provided",
                            actor=session.operator_name)
    except ValueError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    return back(f"/customers/{customer_id}", msg="Customer reactivated.")


@app.post("/customers/{customer_id}/ubo")
def customer_add_ubo(
    request: Request, db: DB, customer_id: int,
    person_name: Annotated[str, Form()],
    ownership_pct: Annotated[str, Form()] = "",
    control_type: Annotated[str, Form()] = "ownership",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    try:
        pct = float(ownership_pct) if ownership_pct.strip() else None
    except ValueError:
        pct = None

    # Validate ownership percentage is in valid range
    if pct is not None and not (0 <= pct <= 100):
        return back(
            f"/customers/{customer_id}",
            err=f"UBO ownership percentage must be between 0 and 100, got {pct}"
        )

    # H-01: Validate total direct UBO ownership won't exceed 100%
    if pct is not None:
        existing_total = db.execute(
            """SELECT COALESCE(SUM(ownership_pct), 0) FROM ubo_links
               WHERE customer_id=? AND org_id=? AND parent_ubo_id IS NULL""",
            (customer_id, session.org_id)
        ).fetchone()[0]
        new_total = existing_total + pct
        if round(new_total, 2) > 100:
            return back(
                f"/customers/{customer_id}",
                err=f"Total UBO ownership would be {round(new_total, 2)}% (cannot exceed 100%)"
            )

    try:
        ubo_id = add_ubo(db, customer_id, org_id=session.org_id, person_name=person_name.strip(),
                         ownership_pct=pct, control_type=control_type, actor=session.operator_name)
    except ValueError as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    res = screen(db, person_name.strip(), org_id=session.org_id, trigger="onboarding",
                 customer_id=customer_id, ubo_id=ubo_id, actor=session.operator_name,
                 threshold=queries.org_alert_threshold(db, session.org_id) or DEFAULT_THRESHOLD)
    note = ("Beneficial owner added. MATCH FOUND - review alerts."
            if res.hits else "Beneficial owner added and screened clear.")
    return back(f"/customers/{customer_id}", msg=note)


@app.post("/customers/{customer_id}/notes")
def customer_add_note(
    request: Request, db: DB, customer_id: int,
    body: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        add_case_note(db, customer_id, session.org_id, author=session.operator_name, body=body)
    except (PermissionError, ValueError) as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    return back(f"/customers/{customer_id}", msg="Note added.")


@app.post("/customers/{customer_id}/transactions")
def customer_add_transaction(
    request: Request, db: DB, customer_id: int,
    direction: Annotated[str, Form()],
    method: Annotated[str, Form()],
    amount: Annotated[str, Form()],
    currency: Annotated[str, Form()] = "AED",
    amount_aed: Annotated[str, Form()] = "",
    counterparty_name: Annotated[str, Form()] = "",
    counterparty_country: Annotated[str, Form()] = "",
    occurred_at: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        amt = float(amount)
        aed = float(amount_aed) if amount_aed.strip() else None
        transaction_id, triggered = record_transaction(
            db, customer_id, session.org_id,
            direction=direction, method=method, amount=amt, currency=currency,
            amount_aed=aed, counterparty_name=counterparty_name.strip() or None,
            counterparty_country=counterparty_country.strip() or None,
            occurred_at=(occurred_at.strip() + "T00:00:00+00:00") if occurred_at.strip() else None,
            actor=session.operator_name,
        )
    except (PermissionError, ValueError) as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    note = (
        f"Transaction recorded. {len(triggered)} rule(s) triggered: "
        + ", ".join(r.rule_key for r in triggered)
        if triggered else "Transaction recorded. No rules triggered."
    )
    return back(f"/customers/{customer_id}", msg=note)


@app.post("/transaction-alerts/{alert_id}/disposition")
def transaction_alert_disposition(
    request: Request, db: DB, alert_id: int,
    status: Annotated[str, Form()],
    note: Annotated[str, Form()] = "",
    customer_id: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    back_url = f"/customers/{customer_id}" if customer_id.strip() else "/"
    try:
        require_csrf(request, csrf_token)
        disposition_transaction_alert(
            db, alert_id, session.org_id, status=status, note=note,
            actor=session.operator_name,
        )
    except (PermissionError, ValueError) as exc:
        return back(back_url, err=str(exc))
    return back(back_url, msg="Transaction alert dispositioned.")


# --------------------------------------------------------------- adverse media
@app.post("/customers/{customer_id}/adverse-media")
def customer_run_adverse_media(
    request: Request, db: DB, customer_id: int,
    window_months: Annotated[int, Form()] = DEFAULT_WINDOW_MONTHS,
    csrf_token: Annotated[str, Form()] = "",
):
    """Run an adverse-media check for one customer, on demand.

    Deliberately operator-triggered rather than part of onboarding or the
    post-refresh re-screen: the provider is a free public service rate-limited
    to one request every five seconds, so this cannot run in a loop over a
    whole customer book. See screening/adverse_media.py's module docstring.
    """
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    back_url = f"/customers/{customer_id}"
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back(back_url, err=str(exc))

    data = queries.customer(db, customer_id, session.org_id)
    if data is None:
        return back("/customers", err=f"Customer {customer_id} not found.")
    c = data["customer"]

    _, result, new_findings = run_adverse_media(
        db,
        org_id=session.org_id,
        customer_id=customer_id,
        name=c["full_name"],
        name_arabic=c["name_arabic"],
        trigger="adhoc",
        window_months=max(1, min(int(window_months or DEFAULT_WINDOW_MONTHS), 120)),
        actor=session.operator_name,
    )
    # A provider outage is reported as a warning, not an error: the check was
    # attempted and the attempt is on the record. Presenting it as a failed
    # action would invite the operator to assume nothing was written.
    if result.status != "ok":
        return back(back_url, err=f"Adverse media check could not complete: {result.error}")
    if not result.findings:
        return back(back_url, msg=f"Adverse media: no adverse coverage found "
                                  f"({result.articles_considered} articles screened).")
    return back(back_url, msg=f"Adverse media: {len(result.findings)} finding(s), "
                              f"{new_findings} new to review.")


@app.post("/adverse-media/run-due")
def adverse_media_run_due(
    request: Request, db: DB,
    limit: Annotated[int, Form()] = ADVERSE_MEDIA_BATCH_LIMIT,
    csrf_token: Annotated[str, Form()] = "",
):
    """Re-check the next few customers whose adverse media is due.

    Bounded and operator-triggered, not a scheduled sweep -- the provider's
    rate limit makes a whole-book batch impossible, so this is "work through
    the next few" with the throttle still between each one. The request blocks
    for the duration, which is why the form caps the batch rather than
    offering "run all".
    """
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back("/dashboard", err=str(exc))

    outcome = run_due_adverse_media(
        db, session.org_id,
        limit=max(1, min(int(limit or ADVERSE_MEDIA_BATCH_LIMIT), 20)),
        actor=session.operator_name,
    )
    if outcome["attempted"] == 0:
        return back("/dashboard", msg="Nothing due for an adverse media check.")
    # Failures are reported alongside successes rather than instead of them:
    # a batch where the provider died halfway still checked the first few, and
    # saying only "it failed" would understate what is on the record.
    msg = (f"Adverse media: checked {outcome['checked']}, "
           f"{outcome['new_findings']} new finding(s), "
           f"{outcome['still_due']} still due.")
    if outcome["failed"]:
        return back("/dashboard", err=msg + f" {outcome['failed']} could not complete.")
    return back("/dashboard", msg=msg)


@app.post("/adverse-media/{finding_id}/disposition")
def adverse_media_disposition(
    request: Request, db: DB, finding_id: int,
    status: Annotated[str, Form()],
    note: Annotated[str, Form()] = "",
    customer_id: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    back_url = f"/customers/{customer_id}" if customer_id.strip() else "/alerts"
    try:
        require_csrf(request, csrf_token)
        rating = disposition_adverse_media_finding(
            db, finding_id, session.org_id, status=status, note=note,
            actor=session.operator_name,
        )
    except (PermissionError, ValueError) as exc:
        return back(back_url, err=str(exc))
    # The re-rating is surfaced rather than left to be discovered on reload:
    # confirming a finding relevant is the one action here that can move a
    # customer's risk band, and the operator should see that it did.
    msg = "Adverse media finding dispositioned."
    if status == "relevant" and rating:
        msg += f" Customer re-rated {rating}."
    return back(back_url, msg=msg)


@app.post("/customers/{customer_id}/signatures")
def customer_add_signature(
    request: Request, db: DB, customer_id: int,
    purpose: Annotated[str, Form()],
    statement: Annotated[str, Form()],
    signer_name: Annotated[str, Form()],
    signer_role: Annotated[str, Form()] = "customer",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        record_signature(
            db, customer_id, session.org_id,
            purpose=purpose, statement=statement, signer_name=signer_name,
            signer_role=signer_role, ip_address=client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            actor=session.operator_name,
        )
    except (PermissionError, ValueError) as exc:
        return back(f"/customers/{customer_id}", err=str(exc))
    return back(f"/customers/{customer_id}", msg=f"Signed by {signer_name.strip()}.")


# --------------------------------------------------------------------- alerts
@app.get("/alerts", response_class=HTMLResponse)
def alerts(request: Request, db: DB, status: str = "open", sort: str = "age_asc", group_by: str = ""):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    sort_by = sort if sort in ("age_asc", "age_desc") else "age_asc"
    effective_status = None if status == "all" else status
    if group_by == "customer":
        grouped = queries.alert_queue_grouped(db, session.org_id, status=effective_status)
        for g in grouped:
            for a in g["alerts"]:
                a["reviews"] = review_history(db, a["id"], session.org_id)
        return render(request, "alerts.html", {
            "session": session, "alerts": [], "grouped": grouped,
            "status": status, "sort": sort_by, "group_by": group_by, "reason_codes": REASON_CODES,
        }, db)
    queue = queries.alert_queue(db, session.org_id, status=effective_status, sort_by=sort_by)
    for a in queue:
        a["reviews"] = review_history(db, a["id"], session.org_id)
    return render(request, "alerts.html", {
        "session": session, "alerts": queue, "grouped": [],
        "status": status, "sort": sort_by, "group_by": group_by, "reason_codes": REASON_CODES,
    }, db)


@app.post("/alerts/bulk-dismiss")
def alerts_bulk_dismiss(
    request: Request, db: DB,
    customer_id: Annotated[int, Form()],
    reason_code: Annotated[str, Form()] = "name_coincidence",
    back_to: Annotated[str, Form()] = "/alerts?group_by=customer",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        count = bulk_dismiss_alerts(
            db, session.org_id, customer_id=customer_id,
            reason_code=reason_code, operator=session.operator_name,
        )
    except (PermissionError, ReviewError) as exc:
        return back(back_to, err=str(exc))
    return back(back_to, msg=f"Dismissed {count} alert(s).")


@app.post("/alerts/{alert_id}/disposition")
def alert_disposition(
    request: Request, db: DB, alert_id: int,
    status: Annotated[str, Form()],
    reason_code: Annotated[str, Form()] = "",
    narrative: Annotated[str, Form()] = "",
    back_to: Annotated[str, Form()] = "/alerts",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        outcome = propose_disposition(
            db, alert_id, org_id=session.org_id, status=status, reason_code=reason_code,
            operator=session.operator_name, narrative=narrative,
        )
    except (PermissionError, ReviewError) as exc:
        return back(back_to, err=str(exc))
    return back(back_to, msg=outcome.message)


@app.post("/alerts/{alert_id}/confirm")
def alert_confirm(
    request: Request, db: DB, alert_id: int,
    agree: Annotated[str, Form()] = "yes",
    narrative: Annotated[str, Form()] = "",
    back_to: Annotated[str, Form()] = "/alerts",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        outcome = confirm_disposition(
            db, alert_id, org_id=session.org_id, operator=session.operator_name,
            agree=(agree == "yes"), narrative=narrative,
        )
    except (PermissionError, ReviewError) as exc:
        return back(back_to, err=str(exc))
    return back(back_to, msg=outcome.message)


@app.post("/alerts/{alert_id}/assign")
def alert_assign_route(
    request: Request, db: DB, alert_id: int,
    operator: Annotated[str, Form()] = "",
    back_to: Annotated[str, Form()] = "/alerts",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    try:
        require_csrf(request, csrf_token)
        assign_alert(db, alert_id, session.org_id,
                    operator=operator.strip() or None, actor=session.operator_name)
    except (PermissionError, ReviewError) as exc:
        return back(back_to, err=str(exc))
    msg = f"Assigned to {operator.strip()}." if operator.strip() else "Assignment cleared."
    return back(back_to, msg=msg)


@app.get("/alerts.csv")
def alerts_csv(request: Request, db: DB, status: str = "all"):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    queue = queries.alert_queue(db, session.org_id, status=None if status == "all" else status)
    return _csv_response(
        "alerts.csv",
        ["id", "category", "score", "caption", "matched_party", "status", "reason_code",
         "assigned_to", "customer_reference", "created_at"],
        [
            [a["id"], a["category"], f"{a['score']:.3f}", a["caption"], a["matched_party"],
             a["status"], a.get("reason_code") or "", a.get("assigned_to") or "",
             a.get("reference") or "", a["created_at"]]
            for a in queue
        ],
    )


@app.get("/customers.csv")
def customers_csv(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    rows = queries.customer_list(db, session.org_id)
    return _csv_response(
        "customers.csv",
        ["reference", "full_name", "customer_type", "sector", "status", "rating",
         "risk_score", "open_alerts", "last_screened", "review_overdue"],
        [
            [c["reference"], c["full_name"], c["customer_type"], c.get("sector") or "",
             c["status"], c.get("rating") or "", c.get("risk_score") or "",
             c["open_alerts"], c.get("last_screened") or "", c["review_overdue"]]
            for c in rows
        ],
    )


def _csv_response(filename: str, header: list[str], rows: list[list]):
    import csv
    import io

    from fastapi.responses import StreamingResponse

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([_escape_csv_formula(h) for h in header])
    writer.writerows([[_escape_csv_formula(cell) for cell in row] for row in rows])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ----------------------------------------------------------------------- about
# Deliberately public -- a company-identity page makes more sense reachable
# without an account (linked externally, or read by an examiner) than gated
# behind login like every operational page. current_session (not
# require_session) so a signed-in visitor still gets the sidebar shell.
@app.get("/about", response_class=HTMLResponse)
def about_view(request: Request, db: DB):
    session = current_session(request, db)
    return render(request, "about.html", {"session": session}, db)


# ---------------------------------------------------------------------- feedback
@app.post("/feedback")
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

    now = utcnow()
    with db:
        db.execute(
            """INSERT INTO feedback (org_id, operator_id, page, message, created_at)
               VALUES (?,?,?,?,?)""",
            (session.org_id, session.operator_id, page.strip(), message, now),
        )
        from ..db import audit
        audit(db, session.operator_name, "feedback.submit", "feedback", None,
              {"page": page.strip()}, org_id=session.org_id)

    from fastapi.responses import JSONResponse
    return JSONResponse({"success": True, "message": "Thank you for your feedback!"})


# ---------------------------------------------------------------------- audit
@app.get("/audit", response_class=HTMLResponse)
def audit_view(request: Request, db: DB, page: int = 1):
    try:
        session = require_session(request, db)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/", err=str(exc))

    per_page = 50
    offset = (page - 1) * per_page

    return render(request, "audit.html", {
        "session": session,
        "entries": queries.audit_trail(db, session.org_id, limit=per_page, offset=offset),
        "page": page,
        "per_page": per_page,
    })


@app.get("/audit/export")
def audit_export(request: Request, db: DB):
    """Export the full audit log for the org as a CSV file. MLRO only."""
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

    entries = queries.audit_trail(db, session.org_id, limit=100000)
    buf = _io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "action", "user", "object_type", "object_id", "detail"])
    for e in entries:
        writer.writerow([
            e.get("ts", ""),
            e.get("action", ""),
            e.get("actor", ""),
            e.get("object_type", ""),
            e.get("object_id", ""),
            e.get("detail", ""),
        ])
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )


# ---------------------------------------------------------------------- super-admin console
@app.get("/console", response_class=HTMLResponse)
def console_view(request: Request, db: DB):
    """Multi-org console for super-admin users."""
    try:
        session = require_session(request, db)
        from .deps import require_super_admin
        require_super_admin(session)
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/", err=str(exc))

    data = queries.console_overview(db)
    return render(request, "console.html", {
        "session": session,
        **data,
    })


@app.get("/console/org/{org_id}/alerts", response_class=HTMLResponse)
def console_org_alerts(request: Request, db: DB, org_id: int, status: str = "open"):
    """Drill down into alerts for a specific org (super-admin only)."""
    try:
        session = require_session(request, db)
        from .deps import require_super_admin
        require_super_admin(session)
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/console", err=str(exc))

    org = db.execute("SELECT name FROM organizations WHERE id=?", (org_id,)).fetchone()
    if org is None:
        return back("/console", err="Organization not found.")

    from ..cases.review import review_history, REASON_CODES
    alert_list = queries.org_alerts(db, org_id, status=status if status != "all" else None)
    from ..cases.review import review_history
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


@app.get("/console/org/{org_id}/customers", response_class=HTMLResponse)
def console_org_customers(request: Request, db: DB, org_id: int):
    """Drill down into customers for a specific org (super-admin only)."""
    try:
        session = require_session(request, db)
        from .deps import require_super_admin
        require_super_admin(session)
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/console", err=str(exc))

    org = db.execute("SELECT name FROM organizations WHERE id=?", (org_id,)).fetchone()
    if org is None:
        return back("/console", err="Organization not found.")

    customer_list = queries.org_customers(db, org_id)
    return render(request, "customers.html", {
        "session": session,
        "customers": customer_list,
        "org_name": org["name"],
        "super_admin_view": True,
    })


# ---------------------------------------------------------------------- admin
@app.get("/admin", response_class=HTMLResponse)
def admin_view(request: Request, db: DB):
    try:
        session = require_session(request, db)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/", err=str(exc))
    org = db.execute("""
        SELECT name, slug, org_address, reporting_person_name,
               reporting_person_title, reporting_person_phone
        FROM organizations WHERE id=?
    """, (session.org_id,)).fetchone()
    if org is None:
        return back("/", err="Organization not found.")
    from ..ingest.loader import staleness_report

    # Check for EU FSF token configuration issues
    eu_warning = None
    import os
    from datetime import datetime, timezone, timedelta

    # Check if token is unset or using the demo default
    eu_token = os.environ.get("AMLKIT_EU_FSF_TOKEN", "").strip()
    demo_token = "dG9rZW4tMjAxNy0xMS0xMw"  # from ingest/eu.py

    if not eu_token or eu_token == demo_token:
        eu_warning = (
            "EU Consolidated Sanctions List is using the demo token. "
            "Register at https://webgate.ec.europa.eu/fsd/fsf and set AMLKIT_EU_FSF_TOKEN "
            "before production use — the demo token may be rate-limited or rotated without notice."
        )
    else:
        # Check if EU refresh has been failing for >3 days
        eu_ds = db.execute(
            "SELECT last_error, error_at FROM datasets WHERE key='eu_sanctions'"
        ).fetchone()
        if eu_ds and eu_ds["last_error"] and eu_ds["error_at"]:
            error_time = datetime.fromisoformat(eu_ds["error_at"])
            # Make timezone-aware if naive (database stores UTC timestamps)
            if error_time.tzinfo is None:
                error_time = error_time.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - error_time > timedelta(days=3):
                eu_warning = (
                    f"EU sanctions refresh has been failing for >3 days (since {error_time.strftime('%Y-%m-%d')}). "
                    f"Error: {eu_ds['last_error'][:200]}"
                )

    return render(request, "admin.html", {
        "session": session, "org": dict(org),
        "operators": queries.operators(db, session.org_id),
        "threshold": queries.org_alert_threshold(db, session.org_id),
        "default_threshold": DEFAULT_THRESHOLD,
        "sanctions": staleness_report(db),
        "eu_warning": eu_warning,
    })


@app.post("/admin/org-profile")
def admin_save_org_profile(
    request: Request, db: DB,
    org_address: Annotated[str, Form()] = "",
    reporting_person_name: Annotated[str, Form()] = "",
    reporting_person_title: Annotated[str, Form()] = "",
    reporting_person_phone: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = ""
):
    """Save organization reporting entity profile for goAML exports (p46)."""
    try:
        session = require_session(request, db)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/admin", err=str(exc))

    # Update org profile
    db.execute("""
        UPDATE organizations
        SET org_address = ?,
            reporting_person_name = ?,
            reporting_person_title = ?,
            reporting_person_phone = ?
        WHERE id = ?
    """, (
        org_address.strip() or None,
        reporting_person_name.strip() or None,
        reporting_person_title.strip() or None,
        reporting_person_phone.strip() or None,
        session.org_id
    ))

    # Audit the change
    from ..db import audit
    audit(db, session.operator_name, "org.profile_update", "organization", session.org_id, {
        "org_address": org_address.strip() or None,
        "reporting_person_name": reporting_person_name.strip() or None,
        "reporting_person_title": reporting_person_title.strip() or None,
        "reporting_person_phone": reporting_person_phone.strip() or None,
    }, org_id=session.org_id)

    db.commit()
    return back("/admin", msg="Reporting entity profile updated.")


@app.get("/admin/compliance", response_class=HTMLResponse)
def compliance_health_view(request: Request, db: DB):
    try:
        session = require_session(request, db)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/", err=str(exc))
    from ..ingest.loader import staleness_report
    report = staleness_report(db)
    # Enrich with last_error / error_at from the datasets table
    error_info = {
        row["key"]: {"last_error": row["last_error"], "error_at": row["error_at"]}
        for row in db.execute("SELECT key, last_error, error_at FROM datasets").fetchall()
    }
    datasets = []
    for ds in report:
        ei = error_info.get(ds["key"], {})
        last_error = ei.get("last_error")
        error_at = ei.get("error_at")
        max_age = ds["max_age_hours"]
        # Determine status
        if last_error:
            status = "FAIL"
        elif ds["breach"]:
            status = "BREACH"
        elif ds["hours_since_refresh"] is not None and ds["hours_since_refresh"] > max_age:
            status = "STALE"
        else:
            status = "OK"
        datasets.append({
            **ds,
            "last_error": last_error,
            "error_at": error_at,
            "status": status,
        })
    return render(request, "compliance.html", {
        "session": session,
        "datasets": datasets,
    })


@app.post("/admin/threshold")
def admin_set_threshold(
    request: Request, db: DB,
    threshold: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    raw = threshold.strip()
    if not raw:
        set_org_alert_threshold(db, session.org_id, None)
        return back("/admin", msg=f"Threshold reset to the engine default ({DEFAULT_THRESHOLD}).")
    try:
        value = float(raw)
    except ValueError:
        return back("/admin", err="Threshold must be a number.")
    if not (0.0 <= value <= 1.0):
        return back("/admin", err="Threshold must be between 0.0 and 1.0.")
    set_org_alert_threshold(db, session.org_id, value)
    from ..db import audit
    audit(db, session.operator_name, "org.threshold_set", "organization", session.org_id,
          {"threshold": value}, org_id=session.org_id)
    db.commit()
    return back("/admin", msg=f"Alert threshold set to {value}.")


@app.post("/admin/operators/{operator_id}/reset-password")
def admin_reset_password(
    request: Request, db: DB, operator_id: int,
    new_password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    row = db.execute(
        "SELECT id FROM operators WHERE id=? AND org_id=?", (operator_id, session.org_id)
    ).fetchone()
    if row is None:
        return back("/admin", err="Operator not found.")
    if len(new_password) < 10:
        return back("/admin", err="Password must be at least 10 characters.")

    auth.set_password(db, operator_id, new_password)
    from ..db import audit
    audit(db, session.operator_name, "operator.password_reset", "operator", operator_id,
          None, org_id=session.org_id)
    db.commit()
    return back("/admin", msg="Password reset. All of that operator's sessions were signed out.")


@app.post("/admin/operators")
def admin_create_operator(
    request: Request, db: DB,
    name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    role: Annotated[str, Form()] = "officer",
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    if len(password) < 10:
        return back("/admin", err="Password must be at least 10 characters.")
    try:
        now = utcnow()
        cur = db.execute(
            # email_verified_at=now: an MLRO adding a known colleague inside
            # their own org is a different trust boundary from public
            # self-registration (see /register-organization) -- the admin is
            # already vouching for this person's identity, so there is no
            # separate email-ownership gap to close (see auth.login()'s
            # guard).
            """INSERT INTO operators
                   (org_id, name, email, password_hash, role, is_active, email_verified_at, created_at)
               VALUES (?,?,?,?,?,1,?,?)""",
            (session.org_id, name.strip(), email.strip().lower(),
             auth.hash_password(password), role, now, now),
        )
    except sqlite3.IntegrityError:
        return back("/admin", err="An operator with that name or email already exists.")
    from ..db import audit
    audit(db, session.operator_name, "operator.create", "operator", cur.lastrowid,
          {"email": email.strip().lower(), "role": role}, org_id=session.org_id)
    db.commit()
    return back("/admin", msg=f"Operator {name.strip()} created.")


@app.post("/admin/operators/{operator_id}/deactivate")
def admin_deactivate_operator(
    request: Request, db: DB, operator_id: int, csrf_token: Annotated[str, Form()] = ""
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    row = db.execute(
        "SELECT id FROM operators WHERE id=? AND org_id=?", (operator_id, session.org_id)
    ).fetchone()
    if row is None:
        return back("/admin", err="Operator not found.")
    db.execute("UPDATE operators SET is_active=0 WHERE id=?", (operator_id,))
    auth.revoke_sessions_for(db, operator_id)
    from ..db import audit
    audit(db, session.operator_name, "operator.deactivate", "operator", operator_id,
          None, org_id=session.org_id)
    db.commit()
    return back("/admin", msg="Operator deactivated and signed out of every session.")


# ---------------------------------------------------------------------- sanctions refresh
@app.post("/admin/refresh")
@limiter.limit("10/minute")
def admin_refresh_sanctions(
    request: Request, db: DB,
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    result = run_sanctions_refresh(db, actor=session.operator_name)

    if result["failures"]:
        return back("/admin", err="Refresh failed for: " + "; ".join(result["failures"]))

    msg = "Sanctions lists refreshed. " + "; ".join(result["loaded"])
    if result["new_alerts"]:
        msg += f" {result['new_alerts']} new alert(s) raised — check Alerts."
    return back("/admin", msg=msg)


@app.get("/admin/refresh-stream")
def admin_refresh_stream(request: Request, db: DB):
    """SSE endpoint that streams per-list sanctions refresh progress."""
    from fastapi.responses import StreamingResponse
    import json as _json

    try:
        session = require_session(request, db)
        require_role(session, "mlro")
    except PermissionError:
        return StreamingResponse(
            iter([f"data: {_json.dumps({'type': 'error', 'error': 'unauthorized'})}\n\n"]),
            media_type="text/event-stream",
        )

    from ..cases.scheduler import refresh_with_progress

    def event_stream():
        for event in refresh_with_progress(db, actor=session.operator_name):
            yield f"data: {_json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/admin/rescreen")
@limiter.limit("10/minute")
def admin_rescreen(
    request: Request, db: DB,
    csrf_token: Annotated[str, Form()] = "",
):
    """Manually trigger bulk re-screening of all active customers.

    MLRO-only endpoint. Calls rescreen_all() without refreshing sanctions lists.
    Returns count of customers re-screened and new alerts created.
    """
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    from ..match.engine import rescreen_all
    from ..db import audit

    audit(db, session.operator_name, "system.rescreen_all", org_id=session.org_id)

    try:
        outcome = rescreen_all(db, session.org_id, actor=session.operator_name)
        db.commit()

        msg = f"Re-screened {outcome['customers']} customer(s)."
        if outcome["alerts"]:
            msg += f" {outcome['alerts']} new alert(s) raised — check Alerts."
        return back("/admin", msg=msg)
    except Exception as exc:
        log.exception("rescreen_all failed for org %s: %s", session.org_id, exc)
        return back("/admin", err=f"Re-screening failed: {exc}")


# ---------------------------------------------------------------------- KYT rule config (Phase 4 enhancement, Step 8)
@app.get("/admin/rule-config", response_class=HTMLResponse)
def admin_rule_config_get(request: Request, db: DB):
    """Show KYT rule configuration form."""
    try:
        session = require_session(request, db)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        return back("/admin", err=str(exc))

    from ..screening.kyt import get_rule_config

    config = get_rule_config(db, session.org_id)
    return render(request, "admin/rule-config.html", {
        "session": session,
        "large_cash_threshold_aed": config["large_cash_threshold_aed"],
        "structuring_window_days": config["structuring_window_days"],
        "velocity_window_hours": config["velocity_window_hours"],
        "velocity_max_count": config["velocity_max_count"],
        "high_risk_countries": ", ".join(config["high_risk_countries"]),
    })


@app.post("/admin/rule-config")
@limiter.limit("10/minute")
def admin_rule_config_post(
    request: Request, db: DB,
    large_cash_threshold_aed: Annotated[str, Form()] = "",
    structuring_window_days: Annotated[str, Form()] = "",
    velocity_window_hours: Annotated[str, Form()] = "",
    velocity_max_count: Annotated[str, Form()] = "",
    high_risk_countries: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
):
    """Update KYT rule configuration."""
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return RedirectResponse("/login", status_code=303)
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=403)

    from ..screening.kyt import save_rule_config, get_rule_config

    config_update = {}
    try:
        if large_cash_threshold_aed:
            config_update["large_cash_threshold_aed"] = float(large_cash_threshold_aed)
        if structuring_window_days:
            config_update["structuring_window_days"] = int(structuring_window_days)
        if velocity_window_hours:
            config_update["velocity_window_hours"] = int(velocity_window_hours)
        if velocity_max_count:
            config_update["velocity_max_count"] = int(velocity_max_count)
        if high_risk_countries:
            config_update["high_risk_countries"] = [
                c.strip().upper() for c in high_risk_countries.split(",") if c.strip()
            ]

        save_rule_config(db, session.org_id, config_update, actor=session.operator_name)
        db.commit()
        return back("/admin/rule-config", msg="Rule configuration updated successfully")
    except ValueError as exc:
        return back("/admin/rule-config", err=str(exc))
    except Exception as exc:
        log.exception("Failed to save rule config: %s", exc)
        return back("/admin/rule-config", err=f"Failed to save configuration: {exc}")


# ---------------------------------------------------------------------- policies (Phase 4 enhancement)
@app.get("/policies", response_class=HTMLResponse)
def policies_list(request: Request, db: DB):
    """List all policy documents grouped by title with version history."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)

    from ..cases.manager import list_policies

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


@app.post("/policies/upload")
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

    from ..cases.manager import upload_policy

    try:
        file_content = file.file.read()

        # Validate MIME type by magic bytes
        from ..validation import validate_file_mime
        try:
            detected_mime = validate_file_mime(file_content, file.filename or "upload.pdf")
        except ValueError as exc:
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


@app.get("/policies/{policy_id:int}/download")
def policies_download(request: Request, db: DB, policy_id: int):
    """Download policy document."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)

    from ..cases.manager import get_policy

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


# ---------------------------------------------------------------------- system/refresh (Cloud Scheduler endpoint)
@app.post("/system/refresh")
def system_refresh(request: Request):
    """HTTP endpoint for Cloud Scheduler to call automatically, on a
    schedule set in Cloud Scheduler (see .github/workflows/source-canary.yml's
    "Wire up Cloud Scheduler sanctions refresh" step) -- not
    once every 23 hours in-process, which cannot survive Cloud Run scaling
    the container to zero between calls.

    Protected by a bearer token stored in the SCHEDULER_SECRET environment
    variable. If the variable is not set the endpoint is disabled entirely
    (returns 403) to prevent accidental exposure on a fresh deploy.

    Runs SYNCHRONOUSLY rather than spawning a background thread. A prior
    version fired the refresh in a daemon thread and returned immediately --
    which meant Cloud Run's autoscaler, which only tracks in-flight HTTP
    requests, had no signal that work was still happening, and could freeze
    or tear down the instance mid-refresh with no error and no way to tell
    whether it had actually finished. Running inline means the instance is
    guaranteed to stay up for the request's duration (see the deploy
    script's --timeout, set generously above this refresh's expected
    duration), and the caller gets a real result back instead of a fire-
    and-forget acknowledgment.
    """
    secret = os.environ.get("SCHEDULER_SECRET", "").strip()
    if not secret:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "endpoint disabled — set SCHEDULER_SECRET"}, status_code=403)

    auth_header = request.headers.get("Authorization", "")
    if not secrets.compare_digest(auth_header, f"Bearer {secret}"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    from ..db import connect
    from fastapi.responses import JSONResponse

    conn = None
    try:
        conn = connect(db_path())
        result = run_sanctions_refresh(conn, actor="cloud-scheduler")

        # Check for staleness and notify MLROs if needed
        staleness_result = check_and_notify_staleness(conn)
        result["staleness_check"] = staleness_result
    finally:
        if conn is not None:
            conn.close()

    # 500 on mandatory-source failure so Cloud Scheduler retries (it only
    # retries on non-2xx). 207 for non-mandatory partial failures leaves a
    # record without triggering unnecessary retries.
    if result["mandatory_failures"]:
        status_code = 500
    elif result["failures"] or result["rescreen_failures"]:
        status_code = 207
    else:
        status_code = 200
    return JSONResponse({"status": "complete", **result}, status_code=status_code)


@app.post("/system/create-operator")
async def system_create_operator(request: Request):
    """Provision an operator without a browser session."""
    secret = os.environ.get("ADMIN_API_SECRET", "").strip()
    if not secret:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "endpoint disabled — set ADMIN_API_SECRET"}, status_code=403)

    auth_header = request.headers.get("Authorization", "")
    if not secrets.compare_digest(auth_header, f"Bearer {secret}"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    from fastapi.responses import JSONResponse
    from ..db import connect
    from ..cases.operators import provision_operator

    body = await request.json()
    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    role = body.get("role") or "officer"
    org_slug = (body.get("org_slug") or "").strip()

    conn = connect(db_path())
    try:
        result = provision_operator(conn, name, email, password, role, org_slug, actor="system")
        return JSONResponse({
            "status": "created",
            "operator_id": result["operator_id"],
            "organization": result["organization"],
            "email": result["email"],
            "role": result["role"],
        })
    except ValueError as exc:
        status = 404 if "no matching" in str(exc) else 409 if "already exists" in str(exc) else 400
        return JSONResponse({"error": str(exc)}, status_code=status)
    finally:
        conn.close()


# ---------------------------------------------------------------------- regulatory reports
@app.get("/reports", response_class=HTMLResponse)
def reports_view(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    
    r_list = queries.report_list(db, session.org_id)
    return render(request, "reports.html", {"session": session, "reports": r_list}, db)


@app.get("/reports/new", response_class=HTMLResponse)
def report_new_view(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)

    customers = queries.customer_list(db, session.org_id)
    return render(request, "report_new.html", {"session": session, "customers": customers}, db)


@app.get("/reports/build", response_class=HTMLResponse)
def report_build_view(
    request: Request, db: DB,
    customer_id: int,
    report_type: str = "STR",
    report_id: int | None = None,
):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    
    cust_data = queries.customer(db, customer_id, session.org_id)
    if not cust_data:
        return back("/reports", err="Customer not found")
        
    payload = {}
    if report_id:
        existing = queries.report(db, report_id, session.org_id)
        if existing:
            import json
            payload = json.loads(existing["payload"] or "{}")

    return render(request, "str_builder.html", {
        "session": session,
        "customer": cust_data["customer"],
        "type": report_type,
        "payload": payload,
        "report_id": report_id,
    }, db)


@app.post("/reports")
def report_save(
    request: Request, db: DB,
    customer_id: Annotated[int, Form()],
    report_type: Annotated[str, Form()],
    reporting_entity_name: Annotated[str, Form()],
    entity_reference: Annotated[str, Form()],
    reporter_name: Annotated[str, Form()],
    reporter_email: Annotated[str, Form()],
    first_name: Annotated[str, Form()],
    last_name: Annotated[str, Form()] = "",
    nationality: Annotated[str, Form()] = "AE",
    birth_date: Annotated[str, Form()] = "",
    gender: Annotated[str, Form()] = "",
    id_type: Annotated[str, Form()] = "",
    id_number: Annotated[str, Form()] = "",
    amount: Annotated[str, Form()] = "",
    transaction_type: Annotated[str, Form()] = "",
    transaction_date: Annotated[str, Form()] = "",
    source_account: Annotated[str, Form()] = "",
    destination_account: Annotated[str, Form()] = "",
    reason_description: Annotated[str, Form()] = "",
    action_taken: Annotated[str, Form()] = "",
    evidence_pack_attached: Annotated[str, Form()] = "",
    report_id: Annotated[int, Form()] = None,
    csrf_token: Annotated[str, Form()] = "",
):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
    except PermissionError as exc:
        return back("/reports", err=str(exc))

    from ..cases.reports import save_report
    result = save_report(
        db, session.org_id, session.operator_name,
        customer_id, report_type, reporting_entity_name, entity_reference,
        reporter_name, reporter_email, first_name, last_name, nationality,
        birth_date, gender, id_type, id_number, amount, transaction_type,
        transaction_date, source_account, destination_account,
        reason_description, action_taken, evidence_pack_attached, report_id
    )

    if not result.success:
        return back("/reports", err=result.error)
    return back(f"/reports/{result.report_id}", msg="Draft report saved.")


@app.get("/reports/{report_id}", response_class=HTMLResponse)
def report_detail_view(request: Request, db: DB, report_id: int):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
        
    rep = queries.report(db, report_id, session.org_id)
    if not rep:
        return back("/reports", err="Report not found")
        
    import json
    payload = json.loads(rep["payload"] or "{}")

    return render(request, "report_detail.html", {
        "session": session,
        "report": rep,
        "payload": payload,
    }, db)


@app.post("/reports/{report_id}/submit")
def report_submit(request: Request, db: DB, report_id: int, csrf_token: Annotated[str, Form()] = ""):
    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        return back(f"/reports/{report_id}", err=str(exc))

    rep = queries.report(db, report_id, session.org_id)
    if not rep:
        return back("/reports", err="Report not found")

    # Check if already submitted (t2)
    if rep["status"] == "submitted":
        return back(f"/reports/{report_id}", err="Report has already been submitted to UAE FIU.")

    # Validate required fields before submission (p17)
    import json
    try:
        payload = json.loads(rep["payload"])
    except (json.JSONDecodeError, TypeError):
        return back(f"/reports/{report_id}", err="Report data is invalid. Cannot submit.")
    
    # Check for required fields
    required_fields = ["reporting_entity_name"]
    missing = [f for f in required_fields if not payload.get(f)]

    if missing:
        return back(f"/reports/{report_id}",
                   err=f"Cannot submit report. Missing required fields: {', '.join(missing)}")

    now = utcnow()
    with db:
        db.execute(
            "UPDATE reports SET status='submitted', submitted_at=? WHERE id=? AND org_id=?",
            (now, report_id, session.org_id)
        )
        from ..db import audit
        audit(db, session.operator_name, "report.submit", "report", report_id,
              {"report_type": rep["report_type"]}, org_id=session.org_id)

    return back(f"/reports/{report_id}", msg="Report submitted to UAE FIU successfully.")


@app.get("/reports/{report_id}/export")
def report_export_xml(request: Request, db: DB, report_id: int):
    try:
        session = require_session(request, db)
    except PermissionError:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")

    rep = queries.report(db, report_id, session.org_id)
    if not rep:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Report not found")

    import json
    from ..reporting.goaml import GoAMLValidationError, serialize_goaml_xml

    payload = json.loads(rep["payload"] or "{}")

    if not payload.get("reporting_entity_name"):
        org = db.execute(
            "SELECT name, org_address FROM organizations WHERE id = ?",
            (session.org_id,),
        ).fetchone()
        if org:
            payload["reporting_entity_name"] = org["name"]
            if org["org_address"] and not payload.get("reporting_entity_branch"):
                payload["reporting_entity_branch"] = org["org_address"]

    try:
        xml_content = serialize_goaml_xml(payload)
    except GoAMLValidationError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc))

    from fastapi.responses import Response
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename=goAML_{rep['report_type']}_{report_id}.xml"
        }
    )


# -------------------------------------------------------------- alerts drawer

@app.get("/api/alerts-summary")
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


# ------------------------------------------------------------------ AI assist

@app.post("/api/ai/draft-narrative")
@limiter.limit("5/minute")
def ai_draft_narrative(
    request: Request,
    db: DB,
    customer_id: int = Form(...),
    include_notes: bool = Form(False),
    csrf_token: Annotated[str, Form()] = "",
):
    """Return an AI-generated STR narrative draft for a customer.

    Form fields:
        customer_id   — required
        include_notes — bool, default false
        csrf_token    — CSRF synchronizer token

    Response (JSON):
        { "narrative": "...", "model": "gemini-...", "advisory": "..." }

    Returns 503 when GEMINI_API_KEY is unset or the Gemini call fails —
    the UI should show a degraded state, not an error page.
    """
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse

    try:
        session = require_session(request, db)
        require_csrf(request, csrf_token)
    except PermissionError:
        raise HTTPException(status_code=401, detail="Unauthorized")

    case = queries.customer(db, customer_id, session.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Customer not found")

    from ..ai.gemini import GeminiUnavailable, draft_str_narrative, GEMINI_MODEL

    try:
        narrative = draft_str_narrative(
            customer=case["customer"],
            alerts=case["alerts"][:20],
            risk=case["risk"],
            notes=case["notes"][:5] if include_notes else [],
        )
    except GeminiUnavailable as exc:
        return JSONResponse(
            status_code=503,
            content={"error": str(exc), "advisory": "AI assistant unavailable."},
        )

    return JSONResponse({
        "narrative": narrative,
        "model": GEMINI_MODEL,
        "advisory": (
            "AI-GENERATED DRAFT — must be reviewed and approved by a qualified "
            "MLRO before use in any regulatory filing."
        ),
    })


# ----------------------------------------------------- compliance calendar (p21)
@app.get("/compliance/calendar", response_class=HTMLResponse)
def compliance_calendar_view(request: Request, db: DB):
    """Compliance calendar list view."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)

    deadlines = queries.compliance_deadlines(db, session.org_id)
    from ..db import utcnow
    now = utcnow()
    for d in deadlines:
        d["is_overdue"] = d["due_date"] < now and d["completed_at"] is None

    return render(request, "compliance_calendar.html", {"session": session, "deadlines": deadlines})

@app.get("/compliance/deadlines")
def compliance_deadlines_list(request: Request, db: DB):
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
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


@app.post("/compliance/deadlines")
def compliance_deadlines_create(request: Request, db: DB, body: _DeadlineCreate):
    try:
        session = require_session(request, db)
        csrf_token = request.headers.get("X-CSRF-Token") or ""
        require_csrf(request, csrf_token)
    except PermissionError:
        return Response(status_code=403)
    from ..db import audit, utcnow
    cur = db.execute(
        "INSERT INTO compliance_deadlines (org_id, title, description, due_date, recurrence, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session.org_id, body.title, body.description, body.due_date, body.recurrence, utcnow())
    )
    deadline_id = cur.lastrowid
    audit(db, session.operator_name, "compliance.deadline_created", "compliance_deadline", deadline_id,
          {"title": body.title}, org_id=session.org_id)
    db.commit()
    return queries.compliance_deadline(db, session.org_id, deadline_id)


@app.patch("/compliance/deadlines/{deadline_id}")
def compliance_deadlines_update(request: Request, db: DB, deadline_id: int, body: _DeadlineUpdate):
    try:
        session = require_session(request, db)
        csrf_token = request.headers.get("X-CSRF-Token") or ""
        require_csrf(request, csrf_token)
    except PermissionError:
        return Response(status_code=403)
    existing = queries.compliance_deadline(db, session.org_id, deadline_id)
    if existing is None:
        return Response(status_code=404)
    if body.title:
        db.execute("UPDATE compliance_deadlines SET title=? WHERE id=? AND org_id=?", (body.title, deadline_id, session.org_id))
        db.commit()
    return queries.compliance_deadline(db, session.org_id, deadline_id)

@app.delete("/compliance/deadlines/{deadline_id}")
def compliance_deadlines_delete(request: Request, db: DB, deadline_id: int):
    try:
        session = require_session(request, db)
        csrf_token = request.headers.get("X-CSRF-Token") or ""
        require_csrf(request, csrf_token)
    except PermissionError:
        return Response(status_code=403)
    existing = queries.compliance_deadline(db, session.org_id, deadline_id)
    if existing is None:
        return Response(status_code=404)
    db.execute("DELETE FROM compliance_deadlines WHERE id=? AND org_id=?", (deadline_id, session.org_id))
    db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ profile/password change (p16)
@app.get("/profile", response_class=HTMLResponse)
def profile_view(request: Request, db: DB):
    """User profile page with password change form."""
    try:
        session = require_session(request, db)
    except PermissionError:
        return RedirectResponse("/login", status_code=303)
    return render(request, "profile.html", {"session": session})


@app.post("/profile/change-password")
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
        auth.validate_password_complexity(new_password)
    except auth.PasswordComplexityError as exc:
        return back("/profile", err=str(exc))

    auth.set_password(db, session.operator_id, new_password)

    from ..db import audit
    audit(db, session.operator_name, "operator.password_changed", "operator", session.operator_id,
          None, org_id=session.org_id)
    db.commit()

    return back("/profile", msg="Password changed successfully. All other sessions have been signed out.")

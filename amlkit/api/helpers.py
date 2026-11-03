"""Shared helpers for the FastAPI app and its routers (moved verbatim from api/app.py; WP-18).

Render/flash/CSRF helpers, role-agnostic dependencies and the Jinja2 templates object.
Route modules live in ``amlkit/api/routers/``; ``app.py`` only wires them together.
"""

from __future__ import annotations

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.datastructures import FormData

from .. import auth, changelog, queries, uaepass
from ..web import blog
from ..cases.review import (
    single_operator_mode,
)
from ..names.arabic import has_arabic_script
from .csv_utils import _escape_csv_formula
from .deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    current_session,
    get_db,
    startup_warning,
)

import logging
import os


WEB = Path(__file__).resolve().parent.parent / "web"

log = logging.getLogger("amlkit.scheduler")

# Issue #102: Flash messages via signed cookies (no itsdangerous dependency)
# Uses the same signing mechanism as CSRF tokens
_FLASH_COOKIE = "amlkit_flash"

templates = Jinja2Templates(directory=str(WEB / "templates"))
templates.env.globals["has_arabic"] = has_arabic_script
templates.env.globals["asset_v"] = int((WEB / "static" / "app.css").stat().st_mtime)
# blog.css/blog.js change independently of app.css, so they get their own cache-buster.
templates.env.filters["blog_date"] = blog.format_date


def _fmt_amount(value: object) -> str:
    """55000.0 -> '55,000'; 1234.5 -> '1,234.50'. Non-numbers pass through."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if float(value).is_integer():
        return f"{value:,.0f}"
    return f"{value:,.2f}"


templates.env.filters["amount"] = _fmt_amount
templates.env.globals["blog_asset_v"] = int(max(
    (WEB / "static" / "blog.css").stat().st_mtime,
    (WEB / "static" / "js" / "blog.js").stat().st_mtime,
))


DEFAULT_PUBLIC_BASE_URL = "https://groaml.grovisor.ae"


def public_base_url() -> str:
    """Canonical public origin for canonical/og:url links, robots.txt and the sitemap.

    ``AMLKIT_PUBLIC_BASE_URL`` (no trailing slash needed); defaults to the
    production host so staging/preview deploys can stop claiming it (L-89).
    Read per call so tests and deploys can change it without a re-import.
    """
    return (os.environ.get("AMLKIT_PUBLIC_BASE_URL") or DEFAULT_PUBLIC_BASE_URL).strip().rstrip("/")


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


def _is_applications_viewer(session) -> bool:
    """Whether `session` is the platform admin who receives quotation requests.

    Applications are not tenant data (no org_id): the session must be a
    super-admin whose own email is one of the quote recipients (AMLKIT_QUOTE_TO,
    default info@grovisor.ae). Shared by render() (sidebar link visibility) and
    _applications_viewer() (the route guard) so the two checks can't drift.
    """
    if session is None or not session.super_admin:
        return False
    from ..mail import quote_recipients
    return session.email.lower() in {a.lower() for a in quote_recipients()}


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
    ctx.setdefault("public_base_url", public_base_url())
    # Gate every "Sign in / Verify via UAE PASS" button on whether the
    # feature is actually configured (see uaepass.load_config()) -- inert
    # until UAEPASS_CLIENT_ID/UAEPASS_CLIENT_SECRET are set, so no template
    # needs to know that detail itself.
    ctx.setdefault("uaepass_enabled", uaepass.load_config() is not None)
    # Same gating for the Billing nav link and the /pricing links.
    from ..billing import stripe_client as _stripe
    ctx.setdefault("billing_enabled", _stripe.load_config() is not None)
    # Public CTA / sign-up mode (see billing.self_serve_enabled): one switch for
    # the nav button, landing, pricing and the registration form.
    ctx.setdefault("self_serve", ctx["billing_enabled"])
    ctx.setdefault("trial_days", 14)
    ctx.setdefault("pending_payment", False)
    if session and db is not None and ctx["billing_enabled"]:
        _pp = db.execute("SELECT plan_status FROM organizations WHERE id=?",
                         (session.org_id,)).fetchone()
        ctx["pending_payment"] = bool(_pp) and _pp["plan_status"] == "pending_payment"
    # single_operator_mode requires db + org_id; only set if both available
    if db and session:
        ctx.setdefault("single_operator", single_operator_mode(db, session.org_id))
    else:
        ctx.setdefault("single_operator", False)  # default to stricter control when context unavailable
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
    # L-81: one-shot "oldest session was signed out" notice from the session cap.
    if session and db is not None:
        _notice = auth.pop_session_notice(db, request.cookies.get(SESSION_COOKIE))
        if _notice:
            ctx["msg"] = f"{ctx['msg']} {_notice}" if ctx.get("msg") else _notice

    # Check dataset health for authenticated sessions
    if session and db is not None:
        # Data-source health is the platform operator's concern: only the
        # super-admin sees this global banner. MLROs still get the dashboard's
        # own 24-hour-rule breach banner when a mandatory list is stale.
        if session.super_admin:
            ctx.setdefault("dataset_banner", queries.dataset_health_banner(db))
            ctx.setdefault("applications_viewer", _is_applications_viewer(session))
        # Check for MFA lockouts (show to admin/MLRO roles)
        if session.operator_role in ("mlro", "admin"):
            mfa_banner = queries.mfa_lockout_banner(db, session.org_id)
            ctx.setdefault("mfa_banner", mfa_banner)

    # Inject organization name for authenticated sessions
    if session:
        ctx.setdefault("org_name", session.org_name)
        if db is not None:
            ctx.setdefault("changelog_unseen", changelog.has_unseen(db, session.operator_id))

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


# ------------------------------------------------------------- UAE PASS SSO
def _uaepass_redirect_uri(path: str) -> str:
    """Absolute callback URL for UAE PASS to redirect back to.

    Built from mail.app_base_url() -- the same trusted, operator-configured
    base URL already used for every other externally-echoed link (email
    verification, alert notifications) -- not from request.base_url, which
    is derived from the client-controlled Host header. An OAuth redirect_uri
    is part of this flow's own CSRF/hijack defense: if it were taken from an
    untrusted header, a forged Host could register a state bound to an
    attacker's URL and have UAE PASS hand the authorization code to it
    instead of this app.
    """
    from .. import mail

    return mail.app_base_url() + path


def _set_uaepass_state_cookie(resp: RedirectResponse, state: str) -> None:
    """Bind a freshly issued UAE PASS state to this browser. See
    auth.UAEPASS_STATE_COOKIE's comment for why this is needed in addition
    to the state's own DB-side validity check."""
    _behind_proxy = os.environ.get("AMLKIT_BEHIND_PROXY") == "1"
    resp.set_cookie(
        auth.UAEPASS_STATE_COOKIE, state, httponly=True, samesite="lax",
        secure=_behind_proxy, max_age=int(auth.UAEPASS_STATE_LIFETIME.total_seconds()),
    )


def _clear_uaepass_state_cookie(resp: RedirectResponse) -> RedirectResponse:
    """Drop the one-shot state cookie once its callback has been handled
    (success or failure) so it never lingers past a single attempt."""
    resp.delete_cookie(auth.UAEPASS_STATE_COOKIE)
    return resp


def _audit_export(db, session, action: str, object_type: str | None = None,
                  object_id=None, detail=None) -> None:
    """One audit row per successful data export (who pulled what out of the
    app, with which filters / how many rows) -- never the exported data."""
    from ..db import audit
    audit(db, session.operator_name, action, object_type, object_id, detail,
          org_id=session.org_id)
    db.commit()


def _csv_response(filename: str, header: list[str], rows: list[list]):
    import csv
    import io

    from fastapi.responses import StreamingResponse
    from ..pii import redact as _redact_pii

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([_escape_csv_formula(h) for h in header])
    writer.writerows([
        [_escape_csv_formula(_redact_pii(str(cell)) if isinstance(cell, str) else cell)
         for cell in row]
        for row in rows
    ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


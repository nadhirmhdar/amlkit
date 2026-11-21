"""FastAPI application: construction, middleware, exception handlers, startup hooks
and router wiring.

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

The route handlers live in ``amlkit/api/routers/`` (one module per domain);
helpers they share (render, flash, CSRF cookie, templates) live in
``amlkit/api/helpers.py``. WP-18 / issue #73 split them out of this file
without changing any route, dependency, limit or response.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .compress import SelectiveGZipMiddleware
from .head import HeadAsGetMiddleware
from .limits import limiter
from .deps import (
    db_path,
)

import contextlib
import logging
import os
import uuid

from ..cases.scheduler import check_and_notify_staleness, run_sanctions_refresh


from .helpers import WEB, templates  # noqa: F401  (templates re-exported: app.templates)

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

app = FastAPI(title="groAML by Grovisor", docs_url=None, redoc_url=None, openapi_url=_openapi_url, lifespan=_lifespan)

# Rate limiting to prevent brute-force attacks and DoS.
# rate_limit_key_func / login_rate_limit_key live in .limits (imported above)
# so mobile.py's /api/v1/auth/login can share the same per-account key
# function without importing this module and creating a circular import.


app.state.limiter = limiter
# Compress static assets and anonymous public pages only (see compress.py: BREACH).
app.add_middleware(SelectiveGZipMiddleware)
app.add_middleware(HeadAsGetMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# JSON API for the native mobile app -- bearer-token auth, no CSRF, no HTML.
# Registered before the static mount so /api/v1/* never falls through to it.
from .mobile import router as mobile_router  # noqa: E402

app.include_router(mobile_router)

# Stripe billing: routes 404 unless STRIPE_SECRET_KEY is set (billing/stripe_client.py).
from .billing import router as billing_router  # noqa: E402

app.include_router(billing_router)

app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")

def _parse_cloud_trace(header: str) -> tuple[str | None, str | None]:
    """Parse X-Cloud-Trace-Context header and return (trace_id, span_id_hex).

    Format: TRACE_ID/SPAN_ID;o=1 where SPAN_ID is decimal uint64.
    Returns (trace_id, 16-char hex span) or (trace_id, None) if span is invalid.
    Only sets span_id if it's numeric, fits in 64 bits, and can be converted to hex.
    """
    if not header:
        return None, None
    parts = header.split("/")
    if len(parts) < 2:
        return None, None
    trace_id = parts[0]
    if not trace_id:
        return None, None
    span_part = parts[1].split(";")[0]  # Remove ;o=1 suffix

    span_id_hex = None
    if span_part and span_part.isdigit():
        try:
            span_val = int(span_part)
            if 0 <= span_val < 2**64:
                span_id_hex = format(span_val, "016x")
        except (ValueError, OverflowError):
            pass

    return trace_id, span_id_hex


def _parse_w3c_traceparent(header: str) -> tuple[str | None, str | None]:
    """Parse W3C traceparent header and return (trace_id, span_id_hex).

    Format: 00-TRACE_ID-SPAN_ID-01 where SPAN_ID is already 16-char hex.
    Returns (trace_id, span_id_hex) or (None, None) if invalid.
    Only sets span_id if it's exactly 16 hex characters.
    """
    if not header:
        return None, None
    parts = header.split("-")
    if len(parts) < 4:
        return None, None
    trace_id = parts[1]
    span_id = parts[2]

    if not trace_id or not span_id:
        return None, None

    # Validate span_id is exactly 16 hex chars
    if len(span_id) == 16 and all(c in "0123456789abcdef" for c in span_id.lower()):
        return trace_id, span_id

    return trace_id, None


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Generate a unique request ID for correlation and attach it to the response.

    Also parses Cloud Trace context headers (X-Cloud-Trace-Context and W3C traceparent).
    Converts decimal span IDs to 16-char hex for Cloud Logging LogEntry.
    """
    request_id = str(uuid.uuid4())
    from ..logging_config import (
        set_request_id, clear_request_id,
        set_trace_id, set_span_id,
        set_org_id
    )

    set_request_id(request_id)

    # Parse trace context from headers
    # X-Cloud-Trace-Context: TRACE_ID/SPAN_ID;o=TRACE_TRUE (SPAN_ID is decimal)
    cloud_trace = request.headers.get("X-Cloud-Trace-Context")
    if cloud_trace:
        trace_id, span_id_hex = _parse_cloud_trace(cloud_trace)
        if trace_id:
            set_trace_id(trace_id)
        if span_id_hex:
            set_span_id(span_id_hex)

    # W3C traceparent: 00-TRACE_ID-SPAN_ID-01 (SPAN_ID is already 16-char hex)
    traceparent = request.headers.get("traceparent")
    if traceparent and not cloud_trace:  # Only use if X-Cloud-Trace-Context not present
        trace_id, span_id_hex = _parse_w3c_traceparent(traceparent)
        if trace_id:
            set_trace_id(trace_id)
        if span_id_hex:
            set_span_id(span_id_hex)

    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        clear_request_id()
        set_trace_id(None)
        set_span_id(None)
        set_org_id(None)


@app.middleware("http")
async def extract_login_email(request: Request, call_next):
    """Extract email from login POST requests for rate limiting.

    This runs before the rate limiter, allowing the rate limit key function to
    access the email synchronously via request.state.login_email.

    We read the raw body and manually parse the email without consuming the
    stream, ensuring the route handler can still access the form data. Covers
    both the web form POST (/login) and the mobile JSON POST
    (/api/v1/auth/login) -- without this, mobile login shares web login's
    decorators but never actually gets a per-account key, silently falling
    back to IP-only limiting.
    """
    if request.method == "POST" and request.url.path in ("/login", "/api/v1/auth/login"):
        try:
            # Read the raw body first (this caches it in request._body)
            body = await request.body()
            body_str = body.decode('utf-8') if isinstance(body, bytes) else str(body)
            if request.url.path == "/login":
                # Parse email manually without consuming the form stream
                from urllib.parse import parse_qs
                parsed = parse_qs(body_str)
                email = parsed.get('email', [''])[0]
            else:
                import json
                email = json.loads(body_str).get('email', '')
            if email:
                request.state.login_email = email.strip()
        except Exception:
            # If body reading/parsing fails, fall back to IP-only rate limiting
            pass
    response = await call_next(request)
    return response


@app.middleware("http")
async def background_submit(request: Request, call_next):
    """Hand a redirect back as JSON when a form was posted in the background.

    bg-submit.js posts the screening and onboarding forms with fetch so the
    loading glass can play instead of a page reload. fetch follows a 303 on
    its own, which would consume the flash cookie (and could quietly fetch
    /login when a session has expired). With X-Background-Submit the redirect
    target comes back as {"location": ...} instead, its Set-Cookie headers
    kept, and the browser navigates there itself. Declared before
    security_headers so that one wraps it and the JSON still gets CSP and
    no-store.
    """
    response = await call_next(request)
    if (request.method == "POST"
            and request.headers.get("x-background-submit") == "1"
            and response.status_code in (302, 303)):
        out = JSONResponse({"location": response.headers.get("location", "/")})
        for cookie in response.headers.getlist("set-cookie"):
            out.headers.append("set-cookie", cookie)
        return out
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
    - Cache-Control: no-store on everything except /static/ (H7)
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
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # No page uses the camera (scans are file uploads), mic or geolocation.
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # Pages and API responses carry customer PII, so nothing may be kept in
    # a shared machine's disk cache (H7). Versionless static assets are
    # exempt: re-downloading app.css/js/fonts on every page load buys nothing.
    if not request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    # HSTS only on HTTPS (production behind proxy)
    if os.environ.get("AMLKIT_BEHIND_PROXY") == "1":
        # 1 year HSTS, includeSubDomains
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Route modules. Registration order is the include order below; static-vs-parameterised
# paths (e.g. /customers/new vs /customers/{customer_id}) are kept together inside one
# router in their original order, and tests/test_app_layout.py pins the relative order.

from .routers import public as _public_routes  # noqa: E402
from .routers import auth as _auth_routes  # noqa: E402
from .routers import account as _account_routes  # noqa: E402
from .routers import mfa as _mfa_routes  # noqa: E402
from .routers import admin as _admin_routes  # noqa: E402
from .routers import freeze as _freeze_routes  # noqa: E402
from .routers import dashboard as _dashboard_routes  # noqa: E402
from .routers import screening as _screening_routes  # noqa: E402
from .routers import customers as _customers_routes  # noqa: E402
from .routers import ubo as _ubo_routes  # noqa: E402
from .routers import alerts as _alerts_routes  # noqa: E402
from .routers import notifications as _notifications_routes  # noqa: E402
from .routers import feedback as _feedback_routes  # noqa: E402
from .routers import audit as _audit_routes  # noqa: E402
from .routers import console as _console_routes  # noqa: E402
from .routers import admin_ops as _admin_ops_routes  # noqa: E402
from .routers import policies as _policies_routes  # noqa: E402
from .routers import system as _system_routes  # noqa: E402
from .routers import reports as _reports_routes  # noqa: E402
from .routers import compliance as _compliance_routes  # noqa: E402

app.include_router(_public_routes.router)
app.include_router(_auth_routes.router)
app.include_router(_account_routes.router)
app.include_router(_mfa_routes.router)
app.include_router(_admin_routes.router)
app.include_router(_freeze_routes.router)
app.include_router(_dashboard_routes.router)
app.include_router(_screening_routes.router)
app.include_router(_customers_routes.router)
app.include_router(_ubo_routes.router)
app.include_router(_alerts_routes.router)
app.include_router(_notifications_routes.router)
app.include_router(_feedback_routes.router)
app.include_router(_audit_routes.router)
app.include_router(_console_routes.router)
app.include_router(_admin_ops_routes.router)
app.include_router(_policies_routes.router)
app.include_router(_system_routes.router)
app.include_router(_reports_routes.router)
app.include_router(_compliance_routes.router)

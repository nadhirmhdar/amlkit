"""Rate limiting configuration for API routes."""
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


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
    (each account gets its own budget) while still protecting each account from
    credential-stuffing attempts.

    Reads the email from request.state.login_email, which is set by
    extract_login_email() middleware in app.py for both the web /login form
    POST and the mobile /api/v1/auth/login JSON POST.
    """
    ip = rate_limit_key_func(request)
    email = getattr(request.state, 'login_email', None)
    if email:
        return f"{ip}:{email.lower().strip()}"
    return ip


def operator_rate_limit_key(request: Request) -> str:
    """Per-operator rate limit key for authenticated routes.

    Keyed on a hash of the caller's credential (web session cookie or mobile
    bearer token), so one busy operator behind a shared office IP cannot
    exhaust a colleague's budget. Falls back to the client IP when the request
    carries no credential (such requests are rejected 401 by the route anyway).
    """
    import hashlib

    from ..auth import SESSION_COOKIE

    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        header = request.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
    if token:
        return "op:" + hashlib.sha256(token.encode()).hexdigest()[:24]
    return rate_limit_key_func(request)


limiter = Limiter(key_func=rate_limit_key_func, default_limits=["100/minute"])

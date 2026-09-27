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


limiter = Limiter(key_func=rate_limit_key_func, default_limits=["100/minute"])

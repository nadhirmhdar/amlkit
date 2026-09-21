"""Request-scoped identity, database access, and bind-safety.

Session identity replaces the earlier plain-text-name-in-a-cookie model. That
model was adequate only when the app bound to 127.0.0.1 and physical machine
access was the security boundary; it is unsafe the moment the app is
reachable from a LAN or holds more than one firm's data, so this module was
rewritten rather than extended.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterator

from fastapi import Request

from ..auth import CSRF_COOKIE, SESSION_COOKIE, SessionInfo, csrf_valid, resolve_session
from ..db import DB_PATH, connect

BIND_HOST = os.environ.get("AMLKIT_BIND_HOST", "127.0.0.1")
BIND_PORT = int(os.environ.get("AMLKIT_PORT", "8000"))
TLS_CONFIGURED = bool(
    os.environ.get("AMLKIT_SSL_KEYFILE") and os.environ.get("AMLKIT_SSL_CERTFILE")
)


def is_network_exposed() -> bool:
    return BIND_HOST not in ("127.0.0.1", "localhost", "::1")


def startup_warning() -> str | None:
    """Warning shown at startup and in the UI banner, or None when safe.

    Now real credentials and multi-tenant regulated data are on the line, so
    binding beyond loopback without TLS is not merely inadvisable, it sends
    passwords and customer PII across the LAN in cleartext.
    """
    if os.environ.get("AMLKIT_BEHIND_PROXY") == "1":
        return None
    if is_network_exposed() and not TLS_CONFIGURED:
        return (
            f"SECURITY: bound to {BIND_HOST} (reachable from the network) with no TLS "
            "configured. Passwords and customer personal data would cross the LAN in "
            "cleartext. Run behind a reverse proxy that terminates HTTPS (e.g. Caddy), "
            "or set AMLKIT_SSL_KEYFILE / AMLKIT_SSL_CERTFILE to a certificate this firm "
            "controls."
        )
    return None


def db_path() -> Path:
    override = os.environ.get("AMLKIT_DB")
    return Path(override) if override else DB_PATH


def get_db() -> Iterator[sqlite3.Connection]:
    """Per-request connection: SQLite connections are not safe to share across
    threads, and FastAPI runs sync endpoints in a threadpool."""
    conn = connect(db_path())
    try:
        yield conn
    finally:
        conn.close()


def current_session(request: Request, conn: sqlite3.Connection) -> SessionInfo | None:
    token = request.cookies.get(SESSION_COOKIE)
    return resolve_session(conn, token)


def require_session(request: Request, conn: sqlite3.Connection) -> SessionInfo:
    """Session for an action that will read or write tenant data.

    Raises PermissionError (routes turn this into a redirect to /login)
    rather than returning None, so a route cannot accidentally proceed with a
    missing session -- there is no falsy-but-usable value to check.
    """
    session = current_session(request, conn)
    if session is None:
        raise PermissionError("Sign in to continue.")
    return session


def require_csrf(request: Request, form_csrf: str | None) -> None:
    """Validate the synchronizer CSRF token on a state-changing POST.

    SameSite=Strict on the session cookie is defense-in-depth, not sufficient
    alone, once sessions gate access to another firm's regulated data -- see
    amlkit/auth.py's csrf_valid() docstring for the full reasoning.
    """
    cookie_value = request.cookies.get(CSRF_COOKIE)
    if not csrf_valid(cookie_value, form_csrf):
        raise PermissionError("Session expired or the form was submitted from a stale page. Reload and try again.")


import ipaddress as _ipaddress

_SKIP_NETWORKS = (
    _ipaddress.ip_network("10.0.0.0/8"),
    _ipaddress.ip_network("172.16.0.0/12"),
    _ipaddress.ip_network("192.168.0.0/16"),
    _ipaddress.ip_network("169.254.0.0/16"),
    _ipaddress.ip_network("127.0.0.0/8"),
)


def _is_proxy_internal_ip(ip: str) -> bool:
    """RFC 1918 + link-local + loopback — IPs that proxies/load balancers use internally."""
    try:
        addr = _ipaddress.ip_address(ip)
        return any(addr in net for net in _SKIP_NETWORKS)
    except ValueError:
        return False


def client_ip(request: Request) -> str | None:
    """Best-effort client IP for the signature audit trail.

    Trusts X-Forwarded-For only when AMLKIT_BEHIND_PROXY=1 is explicitly set
    (see startup_warning() above) -- otherwise a client could set that header
    itself and forge the recorded address. Picks the first non-private IP from
    the chain; falls back to the first hop if all are private.
    """
    if os.environ.get("AMLKIT_BEHIND_PROXY") == "1":
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            hops = [h.strip() for h in forwarded.split(",")]
            for hop in hops:
                if not _is_proxy_internal_ip(hop):
                    return hop
            return hops[0]
    return request.client.host if request.client else None


def require_role(session: SessionInfo, *roles: str) -> None:
    if session.operator_role not in roles:
        raise PermissionError(
            f"This action requires the {' or '.join(roles)} role; "
            f"your account is {session.operator_role}."
        )


def require_super_admin(session: SessionInfo) -> None:
    """Guard for super-admin-only routes (multi-org console)."""
    if not session.super_admin:
        raise PermissionError(
            "This view requires super-admin access. Contact your system administrator."
        )

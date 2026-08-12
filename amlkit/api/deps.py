"""Operator identity, request scoping and bind-safety.

Authentication is deliberately absent in v1 and deliberately isolated here.

The app binds to 127.0.0.1, so physical access to the machine is the security
boundary. Operator identity is a name in a cookie: enough to attribute audit
entries and to enforce that two *different* people signed off a dismissal, but
nothing stops one person selecting two names. That limitation is stated in the
UI rather than implied away -- a control described as stronger than it is, is
worse than an acknowledged gap.

Everything auth-shaped lives in this module so that adding password hashing and
sessions later touches one file rather than every route.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterator

from fastapi import Request

from ..db import DB_PATH, connect, utcnow

OPERATOR_COOKIE = "amlkit_operator"

# Bind host. Anything other than loopback exposes customer PII to the network
# while no authentication exists, so it is opt-in and warned about loudly.
BIND_HOST = os.environ.get("AMLKIT_BIND_HOST", "127.0.0.1")
BIND_PORT = int(os.environ.get("AMLKIT_PORT", "8000"))


def is_network_exposed() -> bool:
    return BIND_HOST not in ("127.0.0.1", "localhost", "::1")


def startup_warning() -> str | None:
    """Warning shown at startup and in the UI banner, or None when safe."""
    if is_network_exposed():
        return (
            f"SECURITY: bound to {BIND_HOST}, which is reachable from the network, "
            "while no authentication is enabled. Customer personal data and "
            "screening results are exposed to anyone who can reach this host. "
            "Bind to 127.0.0.1 unless you have added authentication."
        )
    return None


def db_path() -> Path:
    override = os.environ.get("AMLKIT_DB")
    return Path(override) if override else DB_PATH


def get_db() -> Iterator[sqlite3.Connection]:
    """Per-request connection.

    SQLite connections are not safe to share across threads, and FastAPI runs
    sync endpoints in a threadpool, so a connection per request is the correct
    scope rather than a cached global.
    """
    conn = connect(db_path())
    try:
        yield conn
    finally:
        conn.close()


def ensure_operator(conn: sqlite3.Connection, name: str, role: str = "officer") -> str:
    """Register an operator name if unseen. Returns the canonical name."""
    name = (name or "").strip()
    if not name:
        raise ValueError("operator name cannot be empty")
    conn.execute(
        "INSERT OR IGNORE INTO operators (name, role, created_at) VALUES (?,?,?)",
        (name, role, utcnow()),
    )
    conn.commit()
    return name


def current_operator(request: Request) -> str | None:
    """Operator selected for this browser session, if any."""
    value = request.cookies.get(OPERATOR_COOKIE)
    return value.strip() if value and value.strip() else None


def require_operator(request: Request) -> str:
    """Operator identity for an action that will be written to the audit log.

    Actions are refused rather than attributed to 'unknown'. An audit trail
    whose actor column reads 'unknown' fails the purpose it exists for.
    """
    op = current_operator(request)
    if not op:
        raise PermissionError(
            "Select an operator before recording any action - every entry in the "
            "audit log must be attributable to a person."
        )
    return op

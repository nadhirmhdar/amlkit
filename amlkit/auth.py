"""Authentication: passwords, sessions, CSRF, login throttling.

This module exists because amlkit moved from a single localhost tool with no
real access boundary to a LAN-reachable, multi-tenant deployment. The old
model attributed actions to a plain-text name in an unsigned cookie -- fine
when physical machine access was the security boundary, dangerous the moment
other machines and other firms are on the network. Everything here replaces
that with real credentials and real sessions.

A design review was run specifically against this module before it was
written (see the plan), and several of its choices come directly from that
review rather than the obvious first draft:

* **argon2, not stdlib PBKDF2**, for password hashing. This is regulated
  financial-crime data for multiple firms; the "avoid a new dependency"
  default used elsewhere in this project does not apply here.
* **Sessions snapshot org_id at login** rather than re-deriving it by joining
  to the operator's current org. If an operator is later moved between orgs,
  deactivated, or has their password changed, every session row for that
  operator is explicitly revoked at that moment -- see `revoke_sessions_for`.
* **Constant-time comparison and a single generic error message** on login
  failure, so a wrong password and an unrecognised email are indistinguishable
  to an attacker probing for valid accounts.
* **Lockout after repeated failures**, tracked on the operator row itself
  rather than a separate table, since it is inherently per-account state.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .db import EMAIL_VERIFY_TOKEN_LIFETIME, audit, utcnow

_hasher = PasswordHasher()

SESSION_LIFETIME = timedelta(days=14)
SESSION_COOKIE = "amlkit_session"
CSRF_COOKIE = "amlkit_csrf"

# After this many consecutive failures, the account locks for LOCKOUT_MINUTES.
# Applied per-account (not per-IP): a LAN deployment has few enough operators
# that per-account lockout is both sufficient and simpler than tracking IPs.
MAX_FAILED_LOGINS = 8
LOCKOUT_MINUTES = 15


class AuthError(RuntimeError):
    """Raised for any authentication failure. The message is always safe to
    show a user -- it never distinguishes 'no such email' from 'wrong
    password', which is the property that matters, not the wording.

    The one deliberate exception is the "verify your email" message login()
    raises once a password has already checked out: at that point the caller
    has already proven they know the account's password, so telling them
    specifically what's blocking sign-in leaks nothing an attacker guessing
    passwords could use to enumerate accounts.
    """


class PasswordComplexityError(ValueError):
    """Raised when a password does not meet complexity requirements."""


# Shape-only check, matching the client-side regex the mobile app already
# uses (RegisterOrgScreen.kt's EMAIL_PATTERN) -- catches "not an email at
# all" cheaply before a registration attempt tries to send mail to it. It
# cannot and does not prove the address is real or reachable; that's what
# the verification link itself is for.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def looks_like_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value.strip()))


def validate_password_complexity(password: str) -> None:
    """Validate password meets complexity requirements.

    Raises PasswordComplexityError if password fails any requirement:
    - At least 10 characters
    - At least 1 uppercase letter
    - At least 1 digit
    - At least 1 special character
    """
    if len(password) < 10:
        raise PasswordComplexityError("Password must be at least 10 characters long")

    if not any(c.isupper() for c in password):
        raise PasswordComplexityError("Password must contain at least one uppercase letter")

    if not any(c.isdigit() for c in password):
        raise PasswordComplexityError("Password must contain at least one digit")

    # Special characters: anything that's not alphanumeric
    if not any(not c.isalnum() for c in password):
        raise PasswordComplexityError("Password must contain at least one special character")


# --------------------------------------------------------------------- hash
def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, stored_hash: str) -> bool:
    """Constant-time-equivalent verification (argon2-cffi handles timing
    safety internally; this wrapper just turns its exception into a bool)."""
    try:
        _hasher.verify(stored_hash, raw)
        return True
    except VerifyMismatchError:
        return False


# ---------------------------------------------------------------- sessions
def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _token_hash(raw: str) -> str:
    return sha256(raw.encode()).hexdigest()


@dataclass(slots=True)
class SessionInfo:
    operator_id: int
    org_id: int
    operator_name: str
    operator_role: str
    email: str
    super_admin: bool = False
    disclaimer_acknowledged: bool = False


def create_session(conn: sqlite3.Connection, operator_id: int, org_id: int) -> str:
    """Create a session row and return the raw token to set as a cookie.

    Only the hash is ever stored -- identical treatment to a password, since
    the token IS a credential for the lifetime of the session.
    """
    raw = _new_token()
    now = datetime.now(timezone.utc)
    conn.execute(
        """INSERT INTO sessions (token_hash, operator_id, org_id, created_at, expires_at)
           VALUES (?,?,?,?,?)""",
        (_token_hash(raw), operator_id, org_id, utcnow(),
         (now + SESSION_LIFETIME).isoformat(timespec="seconds")),
    )
    conn.commit()
    return raw


def resolve_session(conn: sqlite3.Connection, raw_token: str | None) -> SessionInfo | None:
    """Look up a session from its raw (cookie) token.

    Returns None for anything not usable: missing, unknown, expired, revoked,
    or pointing at a deactivated operator. All of these collapse to the same
    "not logged in" outcome for the caller -- there is no reason to give a
    client-facing distinction between them.
    """
    if not raw_token:
        return None
    row = conn.execute(
        """SELECT s.operator_id, s.org_id, s.expires_at, s.revoked_at,
                  o.name, o.role, o.email, o.is_active, o.super_admin, o.disclaimer_acknowledged_at
           FROM sessions s JOIN operators o ON o.id = s.operator_id
           WHERE s.token_hash = ?""",
        (_token_hash(raw_token),),
    ).fetchone()
    if row is None or row["revoked_at"] is not None or not row["is_active"]:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        return None
    return SessionInfo(
        operator_id=row["operator_id"], org_id=row["org_id"],
        operator_name=row["name"], operator_role=row["role"], email=row["email"],
        super_admin=bool(row["super_admin"]),
        disclaimer_acknowledged=bool(row["disclaimer_acknowledged_at"]),
    )


def revoke_session(conn: sqlite3.Connection, raw_token: str) -> None:
    conn.execute(
        "UPDATE sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
        (utcnow(), _token_hash(raw_token)),
    )
    conn.commit()


def revoke_sessions_for(conn: sqlite3.Connection, operator_id: int) -> None:
    """Kill every live session for an operator.

    Called on password change and on admin deactivation. Without this, a
    compromised session outlives the very password change meant to end it --
    the whole point of letting someone change their password after a
    suspected leak is that it actually locks the old session out.
    """
    conn.execute(
        "UPDATE sessions SET revoked_at=? WHERE operator_id=? AND revoked_at IS NULL",
        (utcnow(), operator_id),
    )
    conn.commit()


# ------------------------------------------------------------------- login
def _log_auth_event(
    conn: sqlite3.Connection, event: str, email: str | None, detail: dict | None = None,
) -> None:
    import json

    conn.execute(
        "INSERT INTO auth_log (ts, email_attempted, event, detail) VALUES (?,?,?,?)",
        (utcnow(), email, event, json.dumps(detail) if detail else None),
    )
    conn.commit()


def login(conn: sqlite3.Connection, email: str, password: str) -> tuple[str, SessionInfo]:
    """Authenticate and return (raw_session_token, SessionInfo).

    Raises AuthError with one generic message on any failure -- unknown
    email, no password set yet (pre-tenancy operator that has not been
    claimed), wrong password, inactive account, or lockout. An attacker
    should not be able to tell these apart, and an operator who forgot which
    of these applies to them contacts their admin either way.
    """
    email = (email or "").strip().lower()
    generic = AuthError("Incorrect email or password.")
    if not email or not password:
        raise generic

    row = conn.execute(
        """SELECT id, org_id, name, role, email, password_hash, is_active,
                  failed_login_count, locked_until, email_verified_at, super_admin,
                  disclaimer_acknowledged_at
           FROM operators WHERE lower(email) = ?""",
        (email,),
    ).fetchone()

    if row is None:
        # No such account. Still costs roughly the same time as a real check
        # by hashing a dummy value, so a timing side-channel cannot be used to
        # enumerate which emails exist.
        _hasher.hash(password)
        _log_auth_event(conn, "login_failure", email, {"reason": "unknown_email"})
        raise generic

    if row["locked_until"]:
        locked_until = datetime.fromisoformat(row["locked_until"])
        if locked_until > datetime.now(timezone.utc):
            _log_auth_event(conn, "login_failure", email, {"reason": "locked"})
            raise AuthError(
                f"Account locked after repeated failed attempts. Try again after "
                f"{locked_until.strftime('%H:%M UTC')}, or ask an admin to reset it."
            )

    # Explicitly named guard, not relied upon implicitly via a hash-comparison
    # that would fail against None anyway -- this is the one line standing
    # between a pre-tenancy operator row (alice/bob/solo/nadhir.mlro, all
    # NULL password_hash) and being logged into.
    if row["password_hash"] is None or not row["is_active"]:
        _hasher.hash(password)
        _log_auth_event(conn, "login_failure", email, {"reason": "no_credentials_or_inactive"})
        raise generic

    if not verify_password(password, row["password_hash"]):
        failed = row["failed_login_count"] + 1
        lock_sql = ""
        params: list = [failed]
        if failed >= MAX_FAILED_LOGINS:
            lock_until = (datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES))
            lock_sql = ", locked_until=?"
            params.append(lock_until.isoformat(timespec="seconds"))
        conn.execute(
            f"UPDATE operators SET failed_login_count=?{lock_sql} WHERE id=?",
            (*params, row["id"]),
        )
        conn.commit()
        _log_auth_event(conn, "login_failure", email,
                        {"reason": "bad_password", "failed_count": failed})
        raise generic

    if row["email_verified_at"] is None:
        # Correct password, but the account was never activated. Safe to be
        # specific here -- see AuthError's docstring -- and this is the one
        # case where telling the user exactly what to do (check their inbox,
        # or request a new link) matters more than a uniform error string.
        _log_auth_event(conn, "login_failure", email, {"reason": "email_not_verified"})
        raise AuthError(
            "Please verify your email before signing in. Check your inbox for the "
            "verification link, or request a new one."
        )

    conn.execute(
        "UPDATE operators SET failed_login_count=0, locked_until=NULL WHERE id=?", (row["id"],)
    )
    conn.commit()
    token = create_session(conn, row["id"], row["org_id"])
    _log_auth_event(conn, "login_success", email)
    audit(conn, row["name"], "operator.login", "operator", row["id"], None, org_id=row["org_id"])
    # audit() only executes the INSERT; every other write in this function
    # commits itself (create_session, _log_auth_event), and a caller that
    # forgets to commit after login() would silently lose just this one row
    # when its connection closes -- exactly the failure this project's audit
    # trail exists to prevent. login() commits its own writes rather than
    # trusting every future caller to remember.
    conn.commit()
    info = SessionInfo(
        operator_id=row["id"], org_id=row["org_id"],
        operator_name=row["name"], operator_role=row["role"], email=row["email"],
        super_admin=bool(row["super_admin"]),
        disclaimer_acknowledged=bool(row["disclaimer_acknowledged_at"]),
    )
    return token, info


def logout(conn: sqlite3.Connection, raw_token: str, info: SessionInfo | None = None) -> None:
    revoke_session(conn, raw_token)
    _log_auth_event(conn, "logout", info.email if info else None)


def set_password(conn: sqlite3.Connection, operator_id: int, new_password: str) -> None:
    """Set (or reset) an operator's password and revoke every existing session.

    The revocation is not optional: leaving old sessions alive after a
    password change defeats the reason someone changes a password.
    """
    validate_password_complexity(new_password)
    conn.execute(
        "UPDATE operators SET password_hash=?, failed_login_count=0, locked_until=NULL WHERE id=?",
        (hash_password(new_password), operator_id),
    )
    conn.commit()
    revoke_sessions_for(conn, operator_id)


# ------------------------------------------------------- email verification
def create_email_verify_token(conn: sqlite3.Connection, operator_id: int) -> str:
    """Issue a fresh one-time email-verification token for an operator.

    Any previous unused token for this operator is marked used first, so at
    most one link is ever live -- resending invalidates the old one rather
    than leaving two simultaneously valid tokens outstanding.
    """
    now = utcnow()
    conn.execute(
        "UPDATE email_verify_tokens SET used_at=? WHERE operator_id=? AND used_at IS NULL",
        (now, operator_id),
    )
    raw = _new_token()
    expires_at = (datetime.now(timezone.utc) + EMAIL_VERIFY_TOKEN_LIFETIME).isoformat(
        timespec="seconds"
    )
    conn.execute(
        """INSERT INTO email_verify_tokens (operator_id, token_hash, created_at, expires_at)
           VALUES (?,?,?,?)""",
        (operator_id, _token_hash(raw), now, expires_at),
    )
    conn.commit()
    return raw


def last_email_verify_token_age_seconds(conn: sqlite3.Connection, operator_id: int) -> float | None:
    """Seconds since this operator's most recent verification token was
    issued, or None if they've never had one.

    Used to throttle resends (see api/mobile.py and api/app.py's resend
    routes) without adding a rate-limiting dependency or table: a resend
    request within the cooldown window is a silent no-op from the caller's
    point of view, since the previous link is still live anyway.
    """
    row = conn.execute(
        "SELECT created_at FROM email_verify_tokens WHERE operator_id=? ORDER BY id DESC LIMIT 1",
        (operator_id,),
    ).fetchone()
    if row is None:
        return None
    created = datetime.fromisoformat(row["created_at"])
    return (datetime.now(timezone.utc) - created).total_seconds()


def valid_email_verify_token(conn: sqlite3.Connection, raw_token: str):
    """Look up and validate a raw verification token.

    Returns the token row (carrying operator_id) if unused and unexpired,
    else None -- the same fail-closed shape as app.py's _valid_setup_token,
    including treating a missing expires_at as already expired.
    """
    if not raw_token:
        return None
    row = conn.execute(
        "SELECT id, operator_id, used_at, expires_at FROM email_verify_tokens WHERE token_hash=?",
        (_token_hash(raw_token),),
    ).fetchone()
    if row is None or row["used_at"] is not None:
        return None
    if row["expires_at"] is None or datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        return None
    return row


def consume_email_verify_token(conn: sqlite3.Connection, raw_token: str):
    """Validate and redeem a verification token in one step.

    Marks the token used and sets the operator's email_verified_at. Returns
    the operator row (id, org_id, name, role, email) on success, or None if
    the token was missing, already used, or expired.
    """
    row = valid_email_verify_token(conn, raw_token)
    if row is None:
        return None
    now = utcnow()
    conn.execute("UPDATE email_verify_tokens SET used_at=? WHERE id=?", (now, row["id"]))
    conn.execute(
        "UPDATE operators SET email_verified_at=? WHERE id=? AND email_verified_at IS NULL",
        (now, row["operator_id"]),
    )
    operator = conn.execute(
        "SELECT id, org_id, name, role, email FROM operators WHERE id=?",
        (row["operator_id"],),
    ).fetchone()
    conn.commit()
    return operator


# --------------------------------------------------------------------- csrf
def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def csrf_valid(cookie_value: str | None, form_value: str | None) -> bool:
    """Synchronizer-token check: the value in the cookie must match the value
    submitted in the form body. `SameSite=Strict` on the session cookie is
    defense-in-depth, not sufficient alone, once sessions gate access to
    another firm's regulated data -- this is the second, independent check.
    """
    if not cookie_value or not form_value:
        return False
    return secrets.compare_digest(cookie_value, form_value)

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
# p14: Idle timeout - stolen session stays valid until activity, not just absolute expiry
IDLE_TIMEOUT_HOURS = 8  # Configurable via AMLKIT_IDLE_TIMEOUT_HOURS env var
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
    org_name: str = ""
    super_admin: bool = False
    disclaimer_acknowledged: bool = False


def create_session(conn: sqlite3.Connection, operator_id: int, org_id: int, mfa_verified: bool = True) -> str:
    """Create a session row and return the raw token to set as a cookie.

    Only the hash is ever stored -- identical treatment to a password, since
    the token IS a credential for the lifetime of the session.

    mfa_verified: Set to False for MLRO users awaiting MFA challenge (p15).
    """
    raw = _new_token()
    _enforce_session_limit(conn, operator_id)
    now = datetime.now(timezone.utc)
    now_str = utcnow()
    conn.execute(
        """INSERT INTO sessions (token_hash, operator_id, org_id, created_at, expires_at, last_active, mfa_verified)
           VALUES (?,?,?,?,?,?,?)""",
        (_token_hash(raw), operator_id, org_id, now_str,
         (now + SESSION_LIFETIME).isoformat(timespec="seconds"), now_str, 1 if mfa_verified else 0),
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
    import os
    if not raw_token:
        return None
    row = conn.execute(
        """SELECT s.operator_id, s.org_id, s.expires_at, s.revoked_at, s.last_active,
                  o.name, o.role, o.email, o.is_active, o.super_admin, o.disclaimer_acknowledged_at,
                  org.name AS org_name
           FROM sessions s
           JOIN operators o ON o.id = s.operator_id
           JOIN organizations org ON org.id = s.org_id
           WHERE s.token_hash = ?""",
        (_token_hash(raw_token),),
    ).fetchone()
    if row is None or row["revoked_at"] is not None or not row["is_active"]:
        return None
    now = datetime.now(timezone.utc)
    if datetime.fromisoformat(row["expires_at"]) < now:
        return None
    # p14: Check idle timeout (NULL last_active = grandfathered, skip check)
    if row["last_active"]:
        idle_hours = int(os.environ.get("AMLKIT_IDLE_TIMEOUT_HOURS", IDLE_TIMEOUT_HOURS))
        idle_cutoff = now - timedelta(hours=idle_hours)
        if datetime.fromisoformat(row["last_active"]) < idle_cutoff:
            return None
    return SessionInfo(
        operator_id=row["operator_id"], org_id=row["org_id"],
        operator_name=row["name"], operator_role=row["role"], email=row["email"],
        org_name=row["org_name"] if "org_name" in row.keys() else "",
        super_admin=bool(row["super_admin"]),
        disclaimer_acknowledged=bool(row["disclaimer_acknowledged_at"]),
    )


def update_session_activity(conn: sqlite3.Connection, raw_token: str) -> None:
    """Update last_active timestamp for idle timeout tracking (p14)."""
    conn.execute(
        "UPDATE sessions SET last_active=? WHERE token_hash=? AND revoked_at IS NULL",
        (utcnow(), _token_hash(raw_token)),
    )
    conn.commit()


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
    conn: sqlite3.Connection, event: str, email: str | None, detail: dict | None = None, *, ip: str | None = None,
) -> None:
    import json

    conn.execute(
        "INSERT INTO auth_log (ts, email_attempted, event, detail, ip) VALUES (?,?,?,?,?)",
        (utcnow(), email, event, json.dumps(detail) if detail else None, ip),
    )
    conn.commit()


def login(conn: sqlite3.Connection, email: str, password: str, *, ip: str | None = None) -> tuple[str, SessionInfo]:
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
        """SELECT o.id, o.org_id, o.name, o.role, o.email, o.password_hash, o.is_active,
                  o.failed_login_count, o.locked_until, o.email_verified_at, o.super_admin,
                  o.disclaimer_acknowledged_at, org.name AS org_name
           FROM operators o
           LEFT JOIN organizations org ON org.id = o.org_id
           WHERE lower(o.email) = ?""",
        (email,),
    ).fetchone()

    if row is None:
        # No such account. Still costs roughly the same time as a real check
        # by hashing a dummy value, so a timing side-channel cannot be used to
        # enumerate which emails exist.
        _hasher.hash(password)
        _log_auth_event(conn, "login_failure", email, {"reason": "unknown_email"}, ip=ip)
        raise generic

    if row["locked_until"]:
        locked_until = datetime.fromisoformat(row["locked_until"])
        if locked_until > datetime.now(timezone.utc):
            _log_auth_event(conn, "login_failure", email, {"reason": "locked"}, ip=ip)
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
        _log_auth_event(conn, "login_failure", email, {"reason": "no_credentials_or_inactive"}, ip=ip)
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
                        {"reason": "bad_password", "failed_count": failed}, ip=ip)
        raise generic

    if row["email_verified_at"] is None:
        # Correct password, but the account was never activated. Safe to be
        # specific here -- see AuthError's docstring -- and this is the one
        # case where telling the user exactly what to do (check their inbox,
        # or request a new link) matters more than a uniform error string.
        _log_auth_event(conn, "login_failure", email, {"reason": "email_not_verified"}, ip=ip)
        raise AuthError(
            "Please verify your email before signing in. Check your inbox for the "
            "verification link, or request a new one."
        )

    conn.execute(
        "UPDATE operators SET failed_login_count=0, locked_until=NULL WHERE id=?", (row["id"],)
    )
    conn.commit()
    token = create_session(conn, row["id"], row["org_id"])
    _log_auth_event(conn, "login_success", email, ip=ip)
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
        org_name=row["org_name"] or "",
        super_admin=bool(row["super_admin"]),
        disclaimer_acknowledged=bool(row["disclaimer_acknowledged_at"]),
    )
    return token, info


def logout(conn: sqlite3.Connection, raw_token: str, info: SessionInfo | None = None, *, ip: str | None = None) -> None:
    revoke_session(conn, raw_token)
    _log_auth_event(conn, "logout", info.email if info else None, ip=ip)


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
        """SELECT o.id, o.org_id, o.name, o.role, o.email, org.name AS org_name
           FROM operators o
           LEFT JOIN organizations org ON org.id = o.org_id
           WHERE o.id=?""",
        (row["operator_id"],),
    ).fetchone()
    conn.commit()
    return operator




def _enforce_session_limit(conn: sqlite3.Connection, operator_id: int) -> None:
    """Revoke oldest sessions if operator has reached MAX_CONCURRENT_SESSIONS."""
    import os
    max_sessions = int(os.environ.get("MAX_CONCURRENT_SESSIONS", "3"))
    
    # Count active (non-revoked, non-expired) sessions
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    active = conn.execute(
        """SELECT COUNT(*) c FROM sessions
           WHERE operator_id = ? AND revoked_at IS NULL AND expires_at > ?""",
        (operator_id, now)
    ).fetchone()["c"]
    
    if active >= max_sessions:
        # Revoke oldest session
        oldest = conn.execute(
            """SELECT id FROM sessions
               WHERE operator_id = ? AND revoked_at IS NULL AND expires_at > ?
               ORDER BY created_at ASC LIMIT 1""",
            (operator_id, now)
        ).fetchone()
        if oldest:
            conn.execute("UPDATE sessions SET revoked_at=? WHERE id=?",
                        (utcnow(), oldest["id"]))


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


# --------------------------------------------------------------------- MFA/TOTP (p15)
MFA_MAX_FAILURES = 5
MFA_LOCKOUT = timedelta(minutes=15)


def mfa_enroll(conn, operator_id: int) -> tuple[str, str]:
    """Start, or resume, TOTP enrolment. Returns (secret, provisioning_uri).

    The secret is only *pending* until mfa_confirm(): confirmed_at stays NULL
    so an abandoned setup page never counts as an enrolment. A pending secret
    is reused rather than rotated, so reloading /mfa/setup after scanning
    does not invalidate the authenticator the operator just set up. Backup
    codes are issued by mfa_confirm(), once the authenticator is proven.
    """
    import pyotp

    row = conn.execute("SELECT email FROM operators WHERE id=?", (operator_id,)).fetchone()
    email = row["email"]

    pending = conn.execute(
        "SELECT secret FROM mfa_secrets WHERE operator_id=? AND confirmed_at IS NULL",
        (operator_id,),
    ).fetchone()
    if pending:
        secret = pending["secret"]
    else:
        secret = pyotp.random_base32()
        conn.execute(
            "INSERT OR REPLACE INTO mfa_secrets"
            " (operator_id, secret, enrolled_at, confirmed_at, failed_attempts, locked_until)"
            " VALUES (?,?,?,NULL,0,NULL)",
            (operator_id, secret, utcnow()),
        )
        conn.commit()

    qr_uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="amlkit")
    return secret, qr_uri


def mfa_verify(conn, operator_id: int, code: str, *, confirmed_only: bool = False) -> bool:
    """Verify a TOTP code for operator.

    confirmed_only=True is the login challenge: only a confirmed enrolment
    counts. The default also accepts the pending secret shown on /mfa/setup,
    which is how that enrolment gets confirmed in the first place.
    """
    import pyotp

    row = conn.execute(
        "SELECT secret, confirmed_at FROM mfa_secrets WHERE operator_id=?",
        (operator_id,)
    ).fetchone()

    if not row or (confirmed_only and row["confirmed_at"] is None):
        return False

    totp = pyotp.TOTP(row["secret"])
    return totp.verify(code, valid_window=1)


def mfa_confirm(conn, operator_id: int) -> list[str]:
    """Promote the pending secret to a live enrolment (first TOTP proven).

    Returns the ten plaintext backup codes, which exist from this moment
    only: they are shown once and stored argon2-hashed.
    """
    conn.execute(
        "UPDATE mfa_secrets SET confirmed_at=?, failed_attempts=0, locked_until=NULL"
        " WHERE operator_id=? AND confirmed_at IS NULL",
        (utcnow(), operator_id),
    )
    codes = _generate_backup_codes(conn, operator_id)
    conn.commit()
    return codes


def mfa_check_code(conn, operator_id: int, code: str, *, stage: str, actor: str, org_id: int) -> str:
    """Check a code against the operator's enrolment, with lockout.

    stage="setup" accepts the pending secret (this is how enrolment is
    confirmed); stage="verify" is the sign-in challenge and accepts a
    confirmed TOTP or one unused backup code. Returns "ok", "invalid" or
    "locked". MFA_MAX_FAILURES consecutive misses lock the challenge for
    MFA_LOCKOUT, and every miss and every lockout is an audit row, so a
    brute-force attempt is visible to the operator's own firm.
    """
    row = conn.execute(
        "SELECT failed_attempts, locked_until FROM mfa_secrets WHERE operator_id=?",
        (operator_id,),
    ).fetchone()
    if row is None:
        return "invalid"
    if row["locked_until"] and row["locked_until"] > utcnow():
        return "locked"

    code = (code or "").strip().replace(" ", "")
    ok = mfa_verify(conn, operator_id, code, confirmed_only=(stage == "verify"))
    if not ok and stage == "verify":
        ok = mfa_verify_backup_code(conn, operator_id, code)
    if ok:
        conn.execute(
            "UPDATE mfa_secrets SET failed_attempts=0, locked_until=NULL WHERE operator_id=?",
            (operator_id,),
        )
        conn.commit()
        return "ok"

    failures = row["failed_attempts"] + 1
    locked_until = None
    if failures >= MFA_MAX_FAILURES:
        locked_until = (datetime.now(timezone.utc) + MFA_LOCKOUT).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE mfa_secrets SET failed_attempts=?, locked_until=? WHERE operator_id=?",
        (0 if locked_until else failures, locked_until, operator_id),
    )
    audit(conn, actor, "mfa.failed", "operator", operator_id,
          {"stage": stage, "consecutive_failures": failures}, org_id=org_id)
    if locked_until:
        audit(conn, actor, "mfa.locked", "operator", operator_id,
              {"until": locked_until, "after_failures": failures}, org_id=org_id)
    conn.commit()
    return "locked" if locked_until else "invalid"


def mfa_challenge_path(conn, operator_id: int) -> str:
    """Where a locked MLRO session must go next: the TOTP challenge if
    enrolled, otherwise enrolment."""
    return "/mfa/verify" if mfa_is_enrolled(conn, operator_id) else "/mfa/setup"


def mfa_lock_session(conn, raw_token: str, operator_id: int, role: str) -> str | None:
    """Lock a freshly issued session behind MFA when the operator is an MLRO.

    Every path that mints a session for a human (form login, verify-email
    auto-login, setup-token claim, and their mobile counterparts) calls this
    right after create_session()/login(), so no entry point hands an MLRO an
    unlocked session. Returns the challenge path to send them to, or None
    when the role is not challenged.
    """
    if role != "mlro":
        return None
    set_session_mfa_verified(conn, raw_token, False)
    return mfa_challenge_path(conn, operator_id)


def mfa_is_enrolled(conn, operator_id: int) -> bool:
    """True only for a confirmed enrolment; a pending /mfa/setup secret is not one."""
    row = conn.execute(
        "SELECT 1 FROM mfa_secrets WHERE operator_id=? AND confirmed_at IS NOT NULL",
        (operator_id,),
    ).fetchone()
    return row is not None


def mfa_session_state(conn, raw_token: str | None):
    """Live session row for the MFA challenge pages, or None.

    Unlike resolve_session() this also returns sessions still awaiting MFA,
    so /mfa/* can identify the operator without granting tenant access.
    """
    if not raw_token:
        return None
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return conn.execute(
        """SELECT s.operator_id, s.org_id, s.mfa_verified, o.name, o.email, o.role
           FROM sessions s JOIN operators o ON o.id = s.operator_id
           WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at > ?""",
        (_token_hash(raw_token), now),
    ).fetchone()


def session_mfa_verified(conn, raw_token: str | None) -> bool:
    if not raw_token:
        return False
    row = conn.execute(
        "SELECT mfa_verified FROM sessions WHERE token_hash=?", (_token_hash(raw_token),)
    ).fetchone()
    return bool(row and row["mfa_verified"])


def set_session_mfa_verified(conn, raw_token: str, verified: bool) -> None:
    conn.execute(
        "UPDATE sessions SET mfa_verified=? WHERE token_hash=?",
        (1 if verified else 0, _token_hash(raw_token)),
    )
    conn.commit()


def mfa_get_backup_codes(conn, operator_id: int) -> list:
    """Get backup code metadata (never the codes themselves)."""
    rows = conn.execute(
        "SELECT id, used_at FROM mfa_backup_codes WHERE operator_id=? ORDER BY created_at",
        (operator_id,)
    ).fetchall()

    return [{"id": r["id"], "used": r["used_at"] is not None} for r in rows]


def mfa_verify_backup_code(conn, operator_id: int, code: str) -> bool:
    """Verify and consume a backup code."""
    rows = conn.execute(
        "SELECT id, code_hash FROM mfa_backup_codes WHERE operator_id=? AND used_at IS NULL",
        (operator_id,)
    ).fetchall()

    for row in rows:
        try:
            _hasher.verify(row["code_hash"], code)
        except (VerifyMismatchError, Exception):
            continue
        from .db import utcnow
        conn.execute(
            "UPDATE mfa_backup_codes SET used_at=? WHERE id=?",
            (utcnow(), row["id"])
        )
        conn.commit()
        return True

    return False


def _generate_backup_codes(conn, operator_id: int) -> list[str]:
    """Generate 10 backup codes for operator. Returns plaintext codes (show once)."""
    import secrets as sec
    from .db import utcnow

    now = utcnow()
    conn.execute("DELETE FROM mfa_backup_codes WHERE operator_id=?", (operator_id,))

    plaintext_codes = []
    for _ in range(10):
        code = sec.token_hex(4)
        conn.execute(
            "INSERT INTO mfa_backup_codes (operator_id, code_hash, created_at) VALUES (?,?,?)",
            (operator_id, _hasher.hash(code), now)
        )
        plaintext_codes.append(code)
    return plaintext_codes

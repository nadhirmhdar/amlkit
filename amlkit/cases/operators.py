"""Operator provisioning and registration operations.

Extracted from api/app.py to keep routes thin. These functions handle the
business logic for creating operators and organizations, separate from HTTP
concerns like form rendering and cookie management.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
import unicodedata
from typing import Any

from .. import auth, mail
from ..db import audit, utcnow


def operator_name_taken(
    conn: sqlite3.Connection, org_id: int, name: str, exclude_id: int | None = None
) -> bool:
    """True when another operator in the org has this name, ignoring case,
    width/compatibility forms (NFKC) and whitespace runs. The UNIQUE (org_id,
    name) constraint only catches byte-identical names, so "Bob" and "bob"
    would otherwise coexist and read as one person in the audit trail."""
    key = auth.normalise_name_key(name)
    for row in conn.execute("SELECT id, name FROM operators WHERE org_id=?", (org_id,)):
        if row["id"] != exclude_id and auth.normalise_name_key(row["name"]) == key:
            return True
    return False


def make_org_slug(conn: sqlite3.Connection, org_name: str) -> str:
    """Return a unique slug for a new organisation, or raise ValueError.

    A display name that matches an existing organisation (case/NFKC-folded) is
    refused. Latin names slugify as before (and a slug already in use is
    refused as "similar name"). A name with nothing slug-able in it (Arabic,
    CJK, ...) gets "org-" plus a short random suffix so distinct firms never
    collide on the UNIQUE slug.
    """
    key = auth.normalise_name_key(org_name)
    for row in conn.execute("SELECT name FROM organizations"):
        if auth.normalise_name_key(row["name"]) == key:
            raise ValueError("An organization with a similar name already exists.")
    # NFKD + ASCII fold keeps accented Latin names readable ("Societe" for "Société").
    ascii_name = unicodedata.normalize("NFKD", org_name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", ascii_name.strip().lower()).strip("-")
    if base:
        if conn.execute("SELECT 1 FROM organizations WHERE slug=?", (base,)).fetchone():
            raise ValueError("An organization with a similar name already exists.")
        return base
    while True:
        slug = f"org-{secrets.token_hex(3)}"
        if not conn.execute("SELECT 1 FROM organizations WHERE slug=?", (slug,)).fetchone():
            return slug


def register_organization(
    conn: sqlite3.Connection,
    org_name: str,
    operator_name: str,
    email: str,
    password: str,
) -> dict[str, Any]:
    """Register a new organization with its first MLRO operator.

    Raises:
        ValueError: Invalid input (password too short, bad email, etc.)
        sqlite3.IntegrityError: Duplicate org name or email
    """
    # Validate inputs (PasswordComplexityError and IdentityError are ValueErrors)
    auth.check_new_password(password)
    clean_name, clean_email = auth.check_operator_identity(operator_name, email)
    org_name = auth.check_org_name(org_name)
    slug = make_org_slug(conn, org_name)
    now = utcnow()

    # Create organization
    try:
        cur = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
            (org_name, slug, "active", now),
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError("An organization with a similar name already exists.") from exc
    org_id = cur.lastrowid

    # Create operator (MLRO role)
    try:
        cur2 = conn.execute(
            """INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at)
               VALUES (?,?,?,?,?,1,?)""",
            (org_id, clean_name, clean_email, auth.hash_password(password), "mlro", now),
        )
    except sqlite3.IntegrityError:
        # operators.email is UNIQUE across the whole app, not just this org
        # Roll back the organization insert too
        conn.rollback()
        raise ValueError("An account with that email already exists. Try signing in instead.")
    operator_id = cur2.lastrowid
    conn.commit()

    # Audit organization creation
    audit(conn, clean_name, "organization.register", "organization", org_id,
          {"org_name": org_name}, org_id=org_id)
    conn.commit()

    # Create email verification token and send email
    raw_token = auth.create_email_verify_token(conn, operator_id)
    delivery = mail.send_verification_email(clean_email, clean_name, raw_token)

    # Audit email send attempt (including failure outcomes)
    audit(conn, clean_name, "operator.verification_sent", "operator", operator_id,
          {"email": clean_email, "delivery": delivery}, org_id=org_id)
    conn.commit()

    return {
        "org_id": org_id,
        "operator_id": operator_id,
        "email": clean_email,
        "verification_token": raw_token,
        "delivery": delivery,
    }


def complete_initial_setup(
    conn: sqlite3.Connection,
    setup_token: str,
    name: str,
    email: str,
    password: str,
) -> dict[str, Any]:
    """Complete initial setup by creating the first operator for an org.

    Validates the setup token, creates an operator with email_verified_at set
    (token claim proves channel control), and marks the token as used.

    Raises:
        ValueError: Invalid token, used token, expired token, or short password
    """
    from datetime import datetime, timezone
    from hashlib import sha256

    if not setup_token:
        raise ValueError("Setup token is required.")
    auth.check_new_password(password)
    clean_name, clean_email = auth.check_operator_identity(name, email)

    # Validate setup token
    token_hash = sha256(setup_token.encode()).hexdigest()
    row = conn.execute(
        "SELECT id, org_id, used_at, expires_at FROM setup_tokens WHERE token_hash=?",
        (token_hash,),
    ).fetchone()

    if not row:
        raise ValueError("This setup link is invalid, expired, or already used.")
    if row["used_at"] is not None:
        raise ValueError("This setup link has already been used.")

    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at < datetime.now(timezone.utc):
        raise ValueError("This setup link has expired.")

    # Refuse a taken email / name BEFORE the token is consumed, so the link
    # stays usable for a corrected retry.
    if conn.execute("SELECT 1 FROM operators WHERE lower(email)=?", (clean_email,)).fetchone():
        raise ValueError("An account with that email already exists.")
    if operator_name_taken(conn, row["org_id"], clean_name):
        raise ValueError("An operator with that name already exists in this organisation.")

    # Create operator with email already verified
    now = utcnow()
    cur = conn.execute(
        """INSERT INTO operators
               (org_id, name, email, password_hash, role, is_active, email_verified_at, created_at)
           VALUES (?,?,?,?,?,1,?,?)""",
        (row["org_id"], clean_name, clean_email, auth.hash_password(password), "mlro", now, now),
    )
    operator_id = cur.lastrowid

    # Mark token as used
    conn.execute("UPDATE setup_tokens SET used_at=? WHERE id=?", (now, row["id"]))
    conn.commit()

    # Audit setup completion
    audit(conn, clean_name, "operator.setup_claimed", "operator", operator_id,
          {"email": clean_email}, org_id=row["org_id"])
    conn.commit()

    return {
        "operator_id": operator_id,
        "org_id": row["org_id"],
        "email": clean_email,
    }


def provision_operator(
    conn: sqlite3.Connection,
    name: str,
    email: str,
    password: str,
    role: str,
    org_slug: str | None = None,
    actor: str = "system",
) -> dict[str, Any]:
    """Provision an operator without a browser session (for system/API use).

    Finds the target organization (by slug or first active), creates the
    operator with email_verified_at set (API caller is trusted), and audits.

    Raises:
        ValueError: Invalid inputs (short password, invalid role, missing fields)
        sqlite3.IntegrityError: Duplicate email
    """
    # Validate inputs
    if not name or not email:
        raise ValueError("name and email are required")
    auth.check_new_password(password)
    if role not in auth.OPERATOR_ROLES:
        raise ValueError("role must be 'officer' or 'mlro'")

    clean_name, clean_email = auth.check_operator_identity(name, email)

    # Find target organization
    if org_slug:
        org = conn.execute(
            "SELECT id, name FROM organizations WHERE slug=? AND status='active'",
            (org_slug,),
        ).fetchone()
    else:
        org = conn.execute(
            "SELECT id, name FROM organizations WHERE status='active' ORDER BY id LIMIT 1"
        ).fetchone()

    if org is None:
        raise ValueError("no matching active organization")

    if operator_name_taken(conn, org["id"], clean_name):
        raise ValueError("an operator with that name or email already exists")

    # Create operator with email already verified
    now = utcnow()
    try:
        cur = conn.execute(
            """INSERT INTO operators
                   (org_id, name, email, password_hash, role, is_active, email_verified_at, created_at)
               VALUES (?,?,?,?,?,1,?,?)""",
            (org["id"], clean_name, clean_email, auth.hash_password(password), role, now, now),
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError("an operator with that name or email already exists") from exc

    operator_id = cur.lastrowid

    # Audit creation
    audit(conn, actor, "operator.create", "operator", operator_id,
          {"email": clean_email, "role": role, "via": "provision_operator"}, org_id=org["id"])
    conn.commit()

    return {
        "operator_id": operator_id,
        "organization": org["name"],
        "org_id": org["id"],
        "email": clean_email,
        "role": role,
    }


OPERATOR_NAME_MAX = auth.OPERATOR_NAME_MAX


def rename_operator(
    conn: sqlite3.Connection,
    operator_id: int,
    org_id: int,
    new_name: str,
    actor: str = "system",
) -> dict[str, Any]:
    """Change an operator's display name, within one organisation.

    Only `operators.name` changes. Names already written into past records
    (audit entries, case notes, review history) stay as they were recorded:
    rewriting history would make the audit trail say something that was not
    true at the time. The rename itself is audited with the old and new name.

    Names are unique per organisation (UNIQUE (org_id, name)), so a name
    another operator in the same org already uses is refused.

    Raises:
        ValueError: blank or over-long name, operator not in this org, or the
            name is already taken by another operator in the org.
    """
    clean, _ = auth.check_operator_identity(new_name)

    row = conn.execute(
        "SELECT id, name FROM operators WHERE id=? AND org_id=?", (operator_id, org_id)
    ).fetchone()
    if row is None:
        raise ValueError("Operator not found.")

    result = {"operator_id": row["id"], "old_name": row["name"], "new_name": clean}
    if row["name"] == clean:
        return {**result, "changed": False}

    # Case-/NFKC-insensitive: UNIQUE (org_id, name) only catches identical bytes.
    if operator_name_taken(conn, org_id, clean, exclude_id=operator_id):
        raise ValueError("Another operator in this organisation already has that name.")
    try:
        conn.execute(
            "UPDATE operators SET name=? WHERE id=? AND org_id=?", (clean, operator_id, org_id)
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError("Another operator in this organisation already has that name.") from exc
    audit(
        conn, actor, "operator.rename", "operator", operator_id,
        {"from": row["name"], "to": clean}, org_id=org_id,
    )
    conn.commit()
    return {**result, "changed": True}


def set_super_admin(
    conn: sqlite3.Connection,
    email: str,
    grant: bool,
    actor: str = "system",
) -> dict[str, Any]:
    """Grant or revoke the super_admin flag on an existing operator.

    Out-of-band only: this is called from /system/super-admin (gated behind
    ADMIN_API_SECRET), never from any authenticated in-app route -- no MLRO
    or officer can reach this through their own session, by design. The
    resulting flag is not hidden, though: queries.operators() selects it and
    admin.html renders a badge for it to every operator in the org.

    Raises:
        ValueError: No operator with that email.
    """
    clean_email = (email or "").strip().lower()
    row = conn.execute(
        "SELECT id, org_id, name, role FROM operators WHERE lower(email)=?",
        (clean_email,),
    ).fetchone()
    if row is None:
        raise ValueError("no matching operator")

    conn.execute(
        "UPDATE operators SET super_admin=? WHERE id=?",
        (1 if grant else 0, row["id"]),
    )
    audit(
        conn, actor,
        "operator.super_admin_granted" if grant else "operator.super_admin_revoked",
        "operator", row["id"], {"email": clean_email}, org_id=row["org_id"],
    )
    conn.commit()

    return {
        "operator_id": row["id"],
        "organization": conn.execute(
            "SELECT name FROM organizations WHERE id=?", (row["org_id"],)
        ).fetchone()["name"],
        "email": clean_email,
        "role": row["role"],
        "super_admin": bool(grant),
    }

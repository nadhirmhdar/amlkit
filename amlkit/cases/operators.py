"""Operator provisioning and registration operations.

Extracted from api/app.py to keep routes thin. These functions handle the
business logic for creating operators and organizations, separate from HTTP
concerns like form rendering and cookie management.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from .. import auth, mail
from ..db import audit, utcnow


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
    # Validate inputs
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters.")
    if not auth.looks_like_email(email):
        raise ValueError("Enter a valid email address.")

    # Generate slug from org name
    slug = re.sub(r"[^a-z0-9]+", "-", org_name.strip().lower()).strip("-") or "org"
    clean_email = email.strip().lower()
    clean_name = operator_name.strip()
    now = utcnow()

    # Create organization
    try:
        cur = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
            (org_name.strip(), slug, "active", now),
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
          {"org_name": org_name.strip()}, org_id=org_id)
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
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters.")

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

    # Create operator with email already verified
    now = utcnow()
    clean_email = email.strip().lower()
    clean_name = name.strip()
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
    if len(password) < 10:
        raise ValueError("password must be at least 10 characters")
    if role not in ("officer", "mlro"):
        raise ValueError("role must be 'officer' or 'mlro'")

    clean_email = email.strip().lower()
    clean_name = name.strip()

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

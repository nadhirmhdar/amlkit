"""Tests for password complexity validation at auth.py layer.

Issue #71 p19: Password complexity was only enforced in web form client-side.
This centralizes enforcement in auth.py so all password-setting paths validate.
"""
import pytest

from amlkit.auth import PasswordComplexityError, set_password
from amlkit.db import utcnow


def test_password_too_short_rejected(conn, org_id):
    """Passwords under 10 characters are rejected."""
    now = utcnow()
    conn.execute(
        "INSERT INTO operators (name, email, org_id, role, is_active, email_verified_at, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        ("Test User", "test@example.com", org_id, "officer", 1, now, now)
    )
    conn.commit()
    op_id = conn.execute("SELECT id FROM operators WHERE email=?", ("test@example.com",)).fetchone()["id"]

    with pytest.raises(PasswordComplexityError, match="at least 10 characters"):
        set_password(conn, op_id, "Short1!")


def test_password_missing_uppercase_rejected(conn, org_id):
    """Passwords without uppercase letter are rejected."""
    now = utcnow()
    conn.execute(
        "INSERT INTO operators (name, email, org_id, role, is_active, email_verified_at, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        ("Test User", "test2@example.com", org_id, "officer", 1, now, now)
    )
    conn.commit()
    op_id = conn.execute("SELECT id FROM operators WHERE email=?", ("test2@example.com",)).fetchone()["id"]

    with pytest.raises(PasswordComplexityError, match="uppercase letter"):
        set_password(conn, op_id, "nocapital123!")


def test_password_missing_digit_rejected(conn, org_id):
    """Passwords without digit are rejected."""
    now = utcnow()
    conn.execute(
        "INSERT INTO operators (name, email, org_id, role, is_active, email_verified_at, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        ("Test User", "test3@example.com", org_id, "officer", 1, now, now)
    )
    conn.commit()
    op_id = conn.execute("SELECT id FROM operators WHERE email=?", ("test3@example.com",)).fetchone()["id"]

    with pytest.raises(PasswordComplexityError, match="digit"):
        set_password(conn, op_id, "NoDigitsHere!")


def test_password_missing_special_char_rejected(conn, org_id):
    """Passwords without special character are rejected."""
    now = utcnow()
    conn.execute(
        "INSERT INTO operators (name, email, org_id, role, is_active, email_verified_at, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        ("Test User", "test4@example.com", org_id, "officer", 1, now, now)
    )
    conn.commit()
    op_id = conn.execute("SELECT id FROM operators WHERE email=?", ("test4@example.com",)).fetchone()["id"]

    with pytest.raises(PasswordComplexityError, match="special character"):
        set_password(conn, op_id, "NoSpecial123")


def test_strong_password_accepted(conn, org_id):
    """Passwords meeting all requirements are accepted."""
    now = utcnow()
    conn.execute(
        "INSERT INTO operators (name, email, org_id, role, is_active, email_verified_at, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        ("Test User", "test5@example.com", org_id, "officer", 1, now, now)
    )
    conn.commit()
    op_id = conn.execute("SELECT id FROM operators WHERE email=?", ("test5@example.com",)).fetchone()["id"]

    # Should not raise
    set_password(conn, op_id, "StrongPass123!")

    # Verify password was actually set
    row = conn.execute("SELECT password_hash FROM operators WHERE id=?", (op_id,)).fetchone()
    assert row["password_hash"] is not None
    assert len(row["password_hash"]) > 0


def test_multiple_strong_passwords_accepted(conn, org_id):
    """Various strong password formats are accepted."""
    strong_passwords = [
        "ValidPass1!",
        "Another$ecure2",
        "Complex#Pass99",
        "@MyPassword123",
    ]

    for idx, pwd in enumerate(strong_passwords):
        email = f"strong{idx}@example.com"
        now = utcnow()
        conn.execute(
            "INSERT INTO operators (name, email, org_id, role, is_active, email_verified_at, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (f"User {idx}", email, org_id, "officer", 1, now, now)
        )
        conn.commit()
        op_id = conn.execute("SELECT id FROM operators WHERE email=?", (email,)).fetchone()["id"]

        # Should not raise
        set_password(conn, op_id, pwd)

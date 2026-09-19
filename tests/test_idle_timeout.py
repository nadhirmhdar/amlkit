"""Tests for p14: idle session timeout via last_active column."""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_idle_session_beyond_timeout_is_rejected(tmp_path, monkeypatch):
    """Session with last_active > 8 hours ago should be rejected."""
    from amlkit.db import connect, utcnow
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(str(db_file))
    # Create org and operator
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES ('Test', 'test', 'active', ?)", (utcnow(),))
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO operators (org_id, email, name, role, password_hash, is_active, email_verified_at, created_at) VALUES (?,?,?,?,?,1,?,?)",
        (org_id, "test@example.com", "Test User", "mlro", auth.hash_password("password"), utcnow(), utcnow())
    )
    op_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()

    # Create session with last_active 9 hours ago
    token = auth.create_session(conn, op_id, org_id)
    nine_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
    conn.execute("UPDATE sessions SET last_active=? WHERE token_hash=?", (nine_hours_ago, auth._token_hash(token)))
    conn.commit()

    # Should be rejected due to idle timeout
    session_info = auth.resolve_session(conn, token)
    assert session_info is None, "Session idle for 9 hours should be rejected (8 hour timeout)"


def test_idle_session_within_timeout_is_valid(tmp_path, monkeypatch):
    """Session with last_active < 8 hours ago should be valid."""
    from amlkit.db import connect, utcnow
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(str(db_file))
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES ('Test', 'test', 'active', ?)", (utcnow(),))
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO operators (org_id, email, name, role, password_hash, is_active, email_verified_at, created_at) VALUES (?,?,?,?,?,1,?,?)",
        (org_id, "test@example.com", "Test User", "mlro", auth.hash_password("password"), utcnow(), utcnow())
    )
    op_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()

    # Create session with last_active 7 hours ago
    token = auth.create_session(conn, op_id, org_id)
    seven_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    conn.execute("UPDATE sessions SET last_active=? WHERE token_hash=?", (seven_hours_ago, auth._token_hash(token)))
    conn.commit()

    # Should be valid (within 8 hour window)
    session_info = auth.resolve_session(conn, token)
    assert session_info is not None, "Session idle for 7 hours should still be valid"
    assert session_info.email == "test@example.com"


def test_null_last_active_is_grandfathered(tmp_path, monkeypatch):
    """Existing sessions with NULL last_active should remain valid (grandfathered)."""
    from amlkit.db import connect, utcnow
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(str(db_file))
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES ('Test', 'test', 'active', ?)", (utcnow(),))
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO operators (org_id, email, name, role, password_hash, is_active, email_verified_at, created_at) VALUES (?,?,?,?,?,1,?,?)",
        (org_id, "test@example.com", "Test User", "mlro", auth.hash_password("password"), utcnow(), utcnow())
    )
    op_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()

    # Create session then set last_active to NULL (simulating pre-migration session)
    token = auth.create_session(conn, op_id, org_id)
    conn.execute("UPDATE sessions SET last_active=NULL WHERE token_hash=?", (auth._token_hash(token),))
    conn.commit()

    # Should be valid (grandfathered)
    session_info = auth.resolve_session(conn, token)
    assert session_info is not None, "Sessions with NULL last_active should be grandfathered"


def test_configurable_idle_timeout(tmp_path, monkeypatch):
    """AMLKIT_IDLE_TIMEOUT_HOURS env var should configure timeout duration."""
    from amlkit.db import connect, utcnow
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.setenv("AMLKIT_IDLE_TIMEOUT_HOURS", "4")  # 4 hour timeout

    conn = connect(str(db_file))
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES ('Test', 'test', 'active', ?)", (utcnow(),))
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO operators (org_id, email, name, role, password_hash, is_active, email_verified_at, created_at) VALUES (?,?,?,?,?,1,?,?)",
        (org_id, "test@example.com", "Test User", "mlro", auth.hash_password("password"), utcnow(), utcnow())
    )
    op_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()

    # Session 5 hours old should be rejected with 4 hour timeout
    token = auth.create_session(conn, op_id, org_id)
    five_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    conn.execute("UPDATE sessions SET last_active=? WHERE token_hash=?", (five_hours_ago, auth._token_hash(token)))
    conn.commit()

    session_info = auth.resolve_session(conn, token)
    assert session_info is None, "Session idle for 5 hours should be rejected with 4 hour timeout"

"""Test t12: Concurrent session limit."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_max_concurrent_sessions_enforced(tmp_path, monkeypatch):
    """Creating MAX+1 sessions → oldest is expired."""
    from amlkit.db import connect, utcnow
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test", "test", "active", utcnow()))
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
        (1, "Test", "test@example.ae", auth.hash_password("password"), "mlro", 1, utcnow(), utcnow()))
    conn.commit()

    # Create 3 sessions (default MAX)
    tokens = []
    for i in range(3):
        token = auth.create_session(conn, operator_id=1, org_id=1)
        tokens.append(token)
        conn.commit()

    # All 3 should be valid
    for token in tokens:
        session = auth.resolve_session(conn, token)
        assert session is not None, "Session should be valid"

    # Create 4th session → oldest should be expired
    token4 = auth.create_session(conn, operator_id=1, org_id=1)
    conn.commit()

    # First (oldest) session should now be invalid
    session = auth.resolve_session(conn, tokens[0])
    assert session is None, "Oldest session should be expired after creating MAX+1"

    # Newer sessions should still be valid
    for token in tokens[1:] + [token4]:
        session = auth.resolve_session(conn, token)
        assert session is not None, "Newer sessions should remain valid"


def test_exactly_max_sessions_all_valid(tmp_path, monkeypatch):
    """Creating exactly MAX sessions → all work."""
    from amlkit.db import connect, utcnow
    from amlkit import auth

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test", "test", "active", utcnow()))
    conn.execute(
        "INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
        (1, "Test", "test@example.ae", auth.hash_password("password"), "mlro", 1, utcnow(), utcnow()))
    conn.commit()

    # Create exactly 3 sessions
    tokens = []
    for i in range(3):
        token = auth.create_session(conn, operator_id=1, org_id=1)
        tokens.append(token)
        conn.commit()

    # All should be valid
    for token in tokens:
        session = auth.resolve_session(conn, token)
        assert session is not None, "All MAX sessions should be valid"

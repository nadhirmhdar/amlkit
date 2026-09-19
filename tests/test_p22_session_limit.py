"""Concurrent session limiting tests (p22)."""
import os
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.auth import create_session, resolve_session
from amlkit.db import connect, utcnow

@pytest.fixture()
def conn():
    c = connect(":memory:")
    now = utcnow()
    # Create org
    c.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
              ("Test Org", "test-org", "active", now))
    # Create operator
    c.execute("INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at) VALUES (?,?,?,?,?,?,?,?)",
              (1, "Alice", "alice@test.ae", "hash", "mlro", 1, now, now))
    c.commit()
    yield c
    c.close()

def test_session_limit_not_enforced_when_under_max(conn):
    """Can create up to MAX sessions without expiring any."""
    os.environ["MAX_CONCURRENT_SESSIONS"] = "3"
    tokens = []
    for _ in range(3):
        token = create_session(conn, operator_id=1, org_id=1)
        tokens.append(token)
    
    # All 3 should still be valid
    for tok in tokens:
        assert resolve_session(conn, tok) is not None

def test_session_limit_expires_oldest_when_at_max(conn):
    """Creating N+1 sessions expires the oldest."""
    os.environ["MAX_CONCURRENT_SESSIONS"] = "3"
    tokens = []
    for _ in range(3):
        token = create_session(conn, operator_id=1, org_id=1)
        tokens.append(token)
    
    # Create 4th session — should expire tokens[0]
    token4 = create_session(conn, operator_id=1, org_id=1)
    
    # First session should be expired/revoked
    assert resolve_session(conn, tokens[0]) is None
    # Others should still work
    assert resolve_session(conn, tokens[1]) is not None
    assert resolve_session(conn, tokens[2]) is not None
    assert resolve_session(conn, token4) is not None

def test_session_limit_defaults_to_3(conn):
    """MAX_CONCURRENT_SESSIONS defaults to 3 if not set."""
    os.environ.pop("MAX_CONCURRENT_SESSIONS", None)
    tokens = []
    for _ in range(4):
        token = create_session(conn, operator_id=1, org_id=1)
        tokens.append(token)
    
    # First should be expired
    assert resolve_session(conn, tokens[0]) is None
    # Last 3 should work
    for tok in tokens[1:]:
        assert resolve_session(conn, tok) is not None

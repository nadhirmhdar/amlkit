"""Shared test fixtures and utilities."""

import pytest
from amlkit.db import connect, upsert_dataset, utcnow
from amlkit.names.arabic import blocking_keys, canonical_key

INVITE_CODE = "test-invite"


def register_org(client, org_name, name, email, password="a-strong-password-1", invite_code="test-invite"):
    """Register an organization and verify email to get a logged-in session.

    Used by test files that need a working organization fixture but don't use
    the main `client` fixture (e.g., files with their own setUp).
    """
    import re
    client.get("/register-organization")
    csrf = client.cookies.get("amlkit_csrf")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": csrf, "invite_code": invite_code,
    }, follow_redirects=True)
    assert "Check your email" in r.text or "Welcome" in r.text, f"registration failed: {r.text[:300]}"
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    if m:
        client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    return client


@pytest.fixture(autouse=True)
def _invite_code_and_limiter_reset(monkeypatch):
    """Every test gets AMLKIT_REGISTRATION_INVITE_CODE set and a fresh rate-limiter."""
    monkeypatch.setenv("AMLKIT_REGISTRATION_INVITE_CODE", INVITE_CODE)
    from amlkit.api.app import limiter
    limiter.reset()
    yield
    limiter.reset()


LISTED = "AHMED ABD AL-JALEEL AL-HASNAWI"


def seed_fresh_dataset(conn, key="test_list", title="Synthetic Test List"):
    """Seed a fresh mandatory dataset with one test entity.

    Required for onboard() to pass the staleness guard introduced in Phase 3.
    """
    ds = upsert_dataset(conn, key, title, is_mandatory=True)
    now = utcnow()
    # Make dataset fresh
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    cur = conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           countries, birth_date, gender, topics, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "TEST-001", "Person", LISTED, '["ly"]', "1975-03-12", "male",
         '["sanction"]', "{}", now, now)
    )
    eid = cur.lastrowid
    conn.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
        " VALUES (?,?,?,?,?)",
        (eid, LISTED, "primary", canonical_key(LISTED), "latin")
    )
    for tok in blocking_keys(LISTED):
        conn.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)", (tok, eid))
    conn.commit()
    return ds


@pytest.fixture(autouse=True, scope="session")
def _disable_rate_limiter():
    """Prevent slowapi from throttling test clients (e.g. the 10/min login limit)."""
    from amlkit.api.app import app
    app.state.limiter.enabled = False  # slowapi uses .enabled, not ._enabled


@pytest.fixture(autouse=True)
def _reset_rate_limiter_storage():
    """Reset rate limiter in-memory counters before every test.

    All TestClient instances share the same "testclient" IP, so counters from
    one test bleed into the next. Clearing storage here ensures each test
    starts with a clean slate regardless of order.
    """
    from amlkit.api.app import app
    try:
        app.state.limiter._storage.reset()
    except Exception:
        pass
    app.state.limiter.enabled = False
    yield
    app.state.limiter.enabled = False


@pytest.fixture()
def conn():
    """In-memory database with fresh mandatory dataset."""
    c = connect(":memory:")
    seed_fresh_dataset(c)
    yield c
    c.close()


@pytest.fixture()
def org_id(conn) -> int:
    """Test organization."""
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
        " RETURNING id",
        ("Test Firm", "test-firm", "active", utcnow()),
    ).fetchone()
    conn.commit()
    return row["id"]

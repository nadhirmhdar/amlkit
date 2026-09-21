"""Shared test fixtures and utilities."""

import pytest
from amlkit.db import connect, upsert_dataset, utcnow
from amlkit.names.arabic import blocking_keys, canonical_key


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


@pytest.fixture()
def complete_mfa():
    """Enrol the MLRO whose freshly issued session is parked at /mfa/setup (p15).

    An MLRO session created by POST /login is locked until TOTP enrolment (or
    verification) completes; fixtures that log an MLRO in through the form and
    then expect tenant access call this right after the login POST.
    """
    import re
    import pyotp

    def _run(client) -> str:
        page = client.get("/mfa/setup", follow_redirects=False)
        assert page.status_code == 200, f"expected the MFA setup page, got {page.status_code}"
        secret = re.search(r"\b([A-Z2-7]{32})\b", page.text).group(1)
        r = client.post("/mfa/setup", data={
            "code": pyotp.TOTP(secret).now(),
            "csrf_token": client.cookies.get("amlkit_csrf"),
        }, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/", r.headers.get("location")
        return secret

    return _run


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

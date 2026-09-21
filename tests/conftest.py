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


def settle_mfa(client) -> None:
    """Get a freshly minted MLRO session past the MFA gate (p15).

    Every session minted for an MLRO -- verify-email auto-login, setup-token
    claim, the login form -- starts locked, so test helpers call this right
    after those steps. On first sight it enrols (and remembers the TOTP secret
    on the client); on a later form login by the same client it answers the
    challenge with a remembered secret. A no-op when nothing is locked
    (officers, already-verified sessions, failed logins).
    """
    import re
    import pyotp

    page = client.get("/mfa/setup", follow_redirects=False)
    if page.status_code == 200:
        secret = re.search(r"\b([A-Z2-7]{32})\b", page.text).group(1)
        r = client.post("/mfa/setup", data={
            "code": pyotp.TOTP(secret).now(),
            "csrf_token": client.cookies.get("amlkit_csrf"),
        }, follow_redirects=False)
        assert r.status_code == 200 and "backup codes" in r.text.lower(), \
            (r.status_code, r.headers.get("location"))
        known = getattr(client, "_amlkit_mfa_secrets", [])
        client._amlkit_mfa_secrets = [secret] + [k for k in known if k != secret]
        return
    if page.headers.get("location") != "/mfa/verify":
        return  # nothing locked
    known = getattr(client, "_amlkit_mfa_secrets", [])
    assert known, "session is locked at /mfa/verify but this client never enrolled"
    for secret in known:
        r = client.post("/mfa/verify", data={
            "code": pyotp.TOTP(secret).now(),
            "csrf_token": client.cookies.get("amlkit_csrf"),
        }, follow_redirects=False)
        if r.headers.get("location") == "/":
            return
    raise AssertionError("no remembered TOTP secret unlocked this session")


complete_mfa_enrolment = settle_mfa  # older name, same behaviour


def unlock_mobile_mfa(client, token: str) -> None:
    """Enrol + unlock a locked MLRO bearer token (p15).

    A bearer token and a session cookie are the same sessions row, so the
    web enrolment page can be driven with the token as the cookie; the
    client's own cookie (if any) is put back afterwards.
    """
    previous = client.cookies.get("amlkit_session")
    client.cookies.set("amlkit_session", token)
    client.get("/login")  # a locked session is sent on to /mfa/setup, which issues the CSRF cookie
    settle_mfa(client)
    client.cookies.delete("amlkit_session")
    if previous:
        client.cookies.set("amlkit_session", previous)


@pytest.fixture()
def complete_mfa():
    """Fixture form of settle_mfa() for fixtures that log in through the form."""
    return settle_mfa


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

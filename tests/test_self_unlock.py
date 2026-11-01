"""L-101: break-glass self-unlock for password lockouts (single-MLRO firms).

Before: 8 wrong guesses from anyone locked an account for 15 minutes and the
only way out was a second MLRO (`POST /admin/operators/{id}/unlock`), so a
single-MLRO firm could be kept out by an anonymous attacker.

After: the login that trips the lock mails the operator's verified address one
single-use link (30 min); `GET /unlock/{token}` clears the password lock only.

Lead repro A1r (repro/2026-11-01-lead__checks_2026_11_01.py), expected output
after this change -- the owner recovers via the link:
  A1r  8 unauthenticated wrong guesses -> count=8 locked_until=<+15 min>;
       owner's correct pw -> 'Incorrect email or password.';
       after GET /unlock/<emailed token> -> owner's correct pw -> 'OK'
       -> reproduces=False
(`test_owner_recovers_via_link` below is that scenario.)

/login keeps its existing per-IP ceiling (10/minute, stricter than the 20/minute
the work package suggested) and per-account 3/minute limit; the throttling test
pins the per-IP one.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from amlkit import auth, db as dbm, mail
from test_api import client  # noqa: F401  (fixture)

PW = "Correct-Horse-9x"


@pytest.fixture()
def sent(monkeypatch):
    """Capture every unlock email instead of sending it."""
    box = []

    def fake(to, name, raw):
        box.append((to, name, raw))
        return mail.SENT

    monkeypatch.setattr(mail, "send_unlock_email", fake)
    return box


def _add_operator(c, email, *, org_id=1, role="mlro", active=1, verified=True):
    now = dbm.utcnow()
    cur = c.execute(
        "INSERT INTO operators (org_id,email,password_hash,name,role,is_active,email_verified_at,created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (org_id, email, auth.hash_password(PW), email.split("@")[0], role, active,
         now if verified else None, now))
    c.commit()
    return cur.lastrowid


@pytest.fixture()
def c():
    conn = dbm.connect(":memory:")
    now = dbm.utcnow()
    for slug in ("one", "two"):
        conn.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES (?,?, 'active', ?)",
                     (slug, slug, now))
    conn.commit()
    return conn


def _guess(c, email, pw="wrong-guess"):
    try:
        auth.login(c, email, pw)
        return "OK"
    except auth.AuthError as e:
        return str(e)


def _lock(c, email):
    for _ in range(auth.MAX_FAILED_LOGINS):
        _guess(c, email)


def _state(c, op):
    r = c.execute("SELECT failed_login_count, locked_until FROM operators WHERE id=?", (op,)).fetchone()
    return r[0], r[1]


def test_lock_sends_exactly_one_email(c, sent):
    op = _add_operator(c, "owner@one.test")
    for _ in range(auth.MAX_FAILED_LOGINS - 1):
        _guess(c, "owner@one.test")
    assert sent == []  # not locked yet
    _lock_tail = _guess(c, "owner@one.test")
    assert _state(c, op)[1] is not None
    # Further attempts while locked (right or wrong) never mail again.
    _guess(c, "owner@one.test"); _guess(c, "owner@one.test", PW)
    assert len(sent) == 1
    assert sent[0][0] == "owner@one.test"
    rows = c.execute("SELECT detail FROM audit_log WHERE action='operator.unlock_mailed'").fetchall()
    assert len(rows) == 1
    assert sent[0][2] not in (rows[0][0] or "")  # no token in the audit
    assert "token" not in (rows[0][0] or "").lower()
    # Stored hashed, never raw.
    assert c.execute("SELECT count(*) FROM unlock_tokens WHERE token_hash=?", (sent[0][2],)).fetchone()[0] == 0


def test_unverified_or_unknown_address_gets_no_email(c, sent):
    _add_operator(c, "new@one.test", verified=False)
    _lock(c, "new@one.test")
    _lock(c, "nobody@one.test")
    assert sent == []


def test_owner_recovers_via_link(c, sent):
    """A1r after the fix."""
    op = _add_operator(c, "owner@one.test")
    _lock(c, "owner@one.test")
    count, locked = _state(c, op)
    assert count == auth.MAX_FAILED_LOGINS and locked is not None
    assert _guess(c, "owner@one.test", PW) == "Incorrect email or password."  # still locked
    assert auth.consume_unlock_token(c, sent[0][2]) is not None
    assert _state(c, op) == (0, None)
    assert _guess(c, "owner@one.test", PW) == "OK"


def test_second_use_expired_unknown_refused(c, sent):
    op = _add_operator(c, "owner@one.test")
    _lock(c, "owner@one.test")
    raw = sent[0][2]
    assert auth.consume_unlock_token(c, raw) is not None
    assert auth.consume_unlock_token(c, raw) is None  # single use
    assert auth.consume_unlock_token(c, "not-a-token") is None
    assert auth.consume_unlock_token(c, "") is None
    # Expired.
    _lock(c, "owner@one.test")
    raw2 = sent[1][2]
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
    c.execute("UPDATE unlock_tokens SET expires_at=? WHERE operator_id=? AND used_at IS NULL", (past, op))
    c.commit()
    assert auth.consume_unlock_token(c, raw2) is None
    assert _state(c, op)[1] is not None  # still locked


def test_deactivated_operator_token_refused(c, sent):
    op = _add_operator(c, "owner@one.test")
    _lock(c, "owner@one.test")
    c.execute("UPDATE operators SET is_active=0 WHERE id=?", (op,)); c.commit()
    assert auth.consume_unlock_token(c, sent[0][2]) is None
    assert _state(c, op)[1] is not None


def test_token_of_another_operator_does_nothing_to_caller(c, sent):
    a = _add_operator(c, "a@one.test", org_id=1)
    b = _add_operator(c, "b@two.test", org_id=2)
    _lock(c, "a@one.test"); _lock(c, "b@two.test")
    tok_a = next(t for to, _, t in sent if to == "a@one.test")
    assert auth.consume_unlock_token(c, tok_a)["id"] == a
    assert _state(c, a) == (0, None)
    assert _state(c, b)[1] is not None  # B still locked


def test_new_lock_window_voids_older_link(c, sent):
    op = _add_operator(c, "owner@one.test")
    _lock(c, "owner@one.test")
    c.execute("UPDATE operators SET locked_until=?, failed_login_count=0 WHERE id=?",
              ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds"), op))
    c.commit()
    _lock(c, "owner@one.test")
    assert len(sent) == 2
    assert auth.consume_unlock_token(c, sent[0][2]) is None
    assert auth.consume_unlock_token(c, sent[1][2]) is not None


def test_mfa_lock_untouched(c, sent):
    op = _add_operator(c, "owner@one.test")
    until = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(timespec="seconds")
    c.execute("INSERT INTO mfa_secrets (operator_id,secret,enrolled_at,confirmed_at,failed_attempts,locked_until)"
              " VALUES (?,?,?,?,5,?)", (op, "JBSWY3DPEHPK3PXP", dbm.utcnow(), dbm.utcnow(), until))
    c.commit()
    _lock(c, "owner@one.test")
    assert auth.consume_unlock_token(c, sent[0][2]) is not None
    m = c.execute("SELECT failed_attempts, locked_until FROM mfa_secrets WHERE operator_id=?", (op,)).fetchone()
    assert (m[0], m[1]) == (5, until)


def test_dev_mode_prints_link(monkeypatch, capsys):
    monkeypatch.delenv("AMLKIT_SMTP_HOST", raising=False)
    assert mail.send_unlock_email("o@x.test", "O", "RAWTOKEN") == mail.NOT_CONFIGURED
    assert "/unlock/RAWTOKEN" in capsys.readouterr().out


# ------------------------------------------------------------------ HTTP
def _http_db():
    import os
    return dbm.connect(os.environ["AMLKIT_DB"])


def test_route_unlocks_audits_and_redirects(client, sent):
    d = _http_db()
    op = d.execute("SELECT id, org_id FROM operators WHERE email='alice@testfirm.ae'").fetchone()
    for _ in range(auth.MAX_FAILED_LOGINS):
        _guess(d, "alice@testfirm.ae")
    assert _state(d, op["id"])[1] is not None
    anon = TestClient(client.app)
    r = anon.get(f"/unlock/{sent[0][2]}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert "unlocked" in anon.get("/login").text
    assert _state(d, op["id"]) == (0, None)
    ev = d.execute("SELECT org_id FROM audit_log WHERE action='operator.self_unlock'").fetchall()
    assert [e[0] for e in ev] == [op["org_id"]]
    # Replay and garbage show the same generic page, 200, no unlock.
    for tok in (sent[0][2], "garbage"):
        g = anon.get(f"/unlock/{tok}")
        assert g.status_code == 200 and "invalid, expired, or already used" in g.text


def test_login_post_is_throttled_per_ip(client):
    """Per-IP ceiling on /login (10/minute): the 11th attempt from one IP is 429,
    even when every attempt names a different account."""
    anon = TestClient(client.app)
    anon.get("/login")
    csrf = anon.cookies.get("amlkit_csrf")
    client.app.state.limiter.enabled = True
    try:
        codes = [anon.post("/login", data={"email": f"x{i}@nowhere.test", "password": "nope-nope-1",
                                           "csrf_token": csrf}).status_code for i in range(12)]
    finally:
        client.app.state.limiter.enabled = False
    assert codes[:10] == [200] * 10
    assert codes[10] == 429

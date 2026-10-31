"""Login lockout (L-46), lockout/unknown-email message (L-86), empty password
(L-87) and admin unlock for MFA/login locks (L-74)."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from amlkit import auth, db as dbm  # noqa: E402
from amlkit.auth import MAX_FAILED_LOGINS  # noqa: E402

GENERIC = "Incorrect email or password."
PW = "A-strong-password-1"
PW2 = "A-strong-password-2"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from test_api import _register

    db_file = str(tmp_path / "lockout.db")
    monkeypatch.setenv("AMLKIT_DB", db_file)
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    dbm.connect(db_file).close()
    client = TestClient(app, raise_server_exceptions=False)
    _register(client, "Firm A", "Alice", "alice@a.test")
    return client, db_file


def _conn(db_file):
    return dbm.connect(db_file)


def _bad_logins(db_file, email, n):
    msg = None
    for _ in range(n):
        c = _conn(db_file)
        try:
            auth.login(c, email, "wrong-password-xx")
        except auth.AuthError as exc:
            msg = str(exc)
        finally:
            c.close()
    return msg


def _login_ok(db_file, email, password=PW):
    c = _conn(db_file)
    try:
        return auth.login(c, email, password)
    finally:
        c.close()


def _add_officer(client, name, email):
    from test_api import _csrf
    r = client.post("/admin/operators", data={
        "name": name, "email": email, "password": PW2, "role": "officer",
        "csrf_token": _csrf(client)}, follow_redirects=True)
    assert r.status_code == 200


def test_expired_lock_does_not_relock_on_one_wrong_password(env):
    _, db_file = env
    _bad_logins(db_file, "alice@a.test", MAX_FAILED_LOGINS)
    c = _conn(db_file)
    row = c.execute("SELECT failed_login_count, locked_until FROM operators WHERE email='alice@a.test'").fetchone()
    assert row["locked_until"] is not None
    # Locked: even the right password is refused.
    with pytest.raises(auth.AuthError):
        _login_ok(db_file, "alice@a.test")
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
    c.execute("UPDATE operators SET locked_until=? WHERE email='alice@a.test'", (past,))
    c.commit()
    c.close()

    _bad_logins(db_file, "alice@a.test", 1)  # one wrong password after expiry
    c = _conn(db_file)
    row = c.execute("SELECT failed_login_count, locked_until FROM operators WHERE email='alice@a.test'").fetchone()
    c.close()
    assert row["failed_login_count"] == 1 and row["locked_until"] is None
    token, info = _login_ok(db_file, "alice@a.test")
    assert token and info.email == "alice@a.test"


def test_expired_lock_cleared_on_correct_password(env):
    _, db_file = env
    _bad_logins(db_file, "alice@a.test", MAX_FAILED_LOGINS)
    c = _conn(db_file)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
    c.execute("UPDATE operators SET locked_until=? WHERE email='alice@a.test'", (past,))
    c.commit()
    c.close()
    _login_ok(db_file, "alice@a.test")
    c = _conn(db_file)
    row = c.execute("SELECT failed_login_count, locked_until FROM operators WHERE email='alice@a.test'").fetchone()
    c.close()
    assert row["failed_login_count"] == 0 and row["locked_until"] is None


def test_locked_and_unknown_email_messages_identical(env):
    _, db_file = env
    real = _bad_logins(db_file, "alice@a.test", MAX_FAILED_LOGINS + 1)
    unknown = _bad_logins(db_file, "nobody@a.test", MAX_FAILED_LOGINS + 1)
    c = _conn(db_file)
    assert c.execute("SELECT locked_until FROM operators WHERE email='alice@a.test'").fetchone()[0]
    reason = c.execute(
        "SELECT detail FROM auth_log WHERE email_attempted='alice@a.test' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    c.close()
    assert real == unknown == GENERIC
    assert "Try again after" not in real and "UTC" not in real
    assert '"locked"' in reason  # admins can still see the cause in auth_log


def test_empty_password_returns_login_form(env):
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from test_api import _csrf

    c = TestClient(app, raise_server_exceptions=False)
    c.get("/login")
    for data in ({"email": "x@a.test", "password": ""}, {"email": "x@a.test"}, {"email": "", "password": "x"}):
        r = c.post("/login", data={**data, "csrf_token": _csrf(c)})
        assert r.status_code == 200, data
        assert r.headers["content-type"].startswith("text/html")
        assert "Enter your email and password." in r.text


def _lock_everything(db_file, email):
    c = _conn(db_file)
    future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(timespec="seconds")
    op = c.execute("SELECT id FROM operators WHERE email=?", (email,)).fetchone()["id"]
    c.execute("UPDATE operators SET failed_login_count=9, locked_until=? WHERE id=?", (future, op))
    c.execute(
        "INSERT OR REPLACE INTO mfa_secrets (operator_id, secret, enrolled_at, confirmed_at,"
        " failed_attempts, locked_until) VALUES (?,?,?,?,3,?)",
        (op, "JBSWY3DPEHPK3PXP", dbm.utcnow(), dbm.utcnow(), future))
    c.commit()
    c.close()
    return op


def test_admin_unlock_clears_mfa_and_login_locks(env):
    from test_api import _csrf
    client, db_file = env
    _add_officer(client, "Bob", "bob@a.test")
    bob = _lock_everything(db_file, "bob@a.test")
    page = client.get("/admin")
    assert f"/admin/operators/{bob}/unlock" in page.text

    r = client.post(f"/admin/operators/{bob}/unlock", data={"csrf_token": _csrf(client)},
                    follow_redirects=False)
    assert r.status_code == 303
    c = _conn(db_file)
    op = c.execute("SELECT failed_login_count, locked_until FROM operators WHERE id=?", (bob,)).fetchone()
    mfa = c.execute("SELECT failed_attempts, locked_until FROM mfa_secrets WHERE operator_id=?", (bob,)).fetchone()
    aud = c.execute("SELECT actor, org_id FROM audit_log WHERE action='operator.unlock' AND object_id=?",
                    (str(bob),)).fetchone()
    c.close()
    assert op["failed_login_count"] == 0 and op["locked_until"] is None
    assert mfa["failed_attempts"] == 0 and mfa["locked_until"] is None
    assert aud is not None and aud["actor"] == "Alice"
    assert f"/admin/operators/{bob}/unlock" not in client.get("/admin").text
    _login_ok(db_file, "bob@a.test", PW2)


def test_admin_unlock_refused_for_other_org(env):
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from test_api import _register, _csrf
    client, db_file = env
    other = TestClient(app, raise_server_exceptions=False)
    _register(other, "Firm B", "Bella", "bella@b.test")
    c = _conn(db_file)
    bella = c.execute("SELECT id FROM operators WHERE email='bella@b.test'").fetchone()["id"]
    c.close()
    _lock_everything(db_file, "bella@b.test")

    r = client.post(f"/admin/operators/{bella}/unlock", data={"csrf_token": _csrf(client)},
                    follow_redirects=False)
    assert r.status_code == 303
    c = _conn(db_file)
    op = c.execute("SELECT failed_login_count, locked_until FROM operators WHERE id=?", (bella,)).fetchone()
    mfa = c.execute("SELECT failed_attempts, locked_until FROM mfa_secrets WHERE operator_id=?", (bella,)).fetchone()
    n = c.execute("SELECT COUNT(*) FROM audit_log WHERE action='operator.unlock'").fetchone()[0]
    c.close()
    assert op["locked_until"] is not None and op["failed_login_count"] == 9
    assert mfa["locked_until"] is not None and mfa["failed_attempts"] == 3
    assert n == 0


def test_admin_unlock_refused_for_non_admin_and_without_csrf(env):
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from test_api import _csrf
    client, db_file = env
    _add_officer(client, "Bob", "bob@a.test")
    _add_officer(client, "Cara", "cara@a.test")
    c = _conn(db_file)
    cara = c.execute("SELECT id FROM operators WHERE email='cara@a.test'").fetchone()["id"]
    c.close()
    _lock_everything(db_file, "cara@a.test")

    # CSRF is enforced for the MLRO.
    r = client.post(f"/admin/operators/{cara}/unlock", data={"csrf_token": "bad"}, follow_redirects=False)
    assert r.status_code == 403

    officer = TestClient(app, raise_server_exceptions=False)
    officer.get("/login")
    r = officer.post("/login", data={"email": "bob@a.test", "password": PW2,
                                      "csrf_token": _csrf(officer)}, follow_redirects=False)
    assert r.status_code == 303
    r = officer.post(f"/admin/operators/{cara}/unlock", data={"csrf_token": _csrf(officer)},
                     follow_redirects=False)
    assert r.status_code == 403
    c = _conn(db_file)
    assert c.execute("SELECT locked_until FROM operators WHERE id=?", (cara,)).fetchone()[0] is not None
    c.close()

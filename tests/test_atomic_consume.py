"""One-time secrets are consumed atomically (L-66, L-69, L-76, L-77) and a TOTP
code is accepted once (L-40). Real SQLite files, one connection per thread."""
import os
import sqlite3
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pyotp
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from amlkit import auth, db as dbm  # noqa: E402
from amlkit.cases.operators import complete_initial_setup  # noqa: E402

N = 10


@pytest.fixture
def dbp():
    path = os.path.join(tempfile.mkdtemp(), "consume.db")
    w = dbm.connect(path)
    now = dbm.utcnow()
    w.execute("INSERT INTO organizations (name, slug, created_at) VALUES ('O', 'o', ?)", (now,))
    w.execute("INSERT INTO operators (org_id, name, email, role, password_hash, created_at)"
              " VALUES (1, 'Mona', 'm@t.test', 'mlro', 'x', ?)", (now,))
    w.commit()
    w.close()
    return path


def _race(path, fn, n=N):
    res, barrier = [], threading.Barrier(n)

    def run():
        k = dbm.connect(path)
        k.row_factory = sqlite3.Row
        barrier.wait()
        try:
            res.append(fn(k))
        except Exception as e:  # noqa: BLE001
            res.append(e)
        finally:
            k.close()

    th = [threading.Thread(target=run) for _ in range(n)]
    [t.start() for t in th]
    [t.join() for t in th]
    return res


def _mk_setup_token(path, raw):
    exp = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec="seconds")
    k = sqlite3.connect(path)
    k.execute("INSERT INTO setup_tokens (org_id, token_hash, created_at, expires_at) VALUES (1,?,?,?)",
              (sha256(raw.encode()).hexdigest(), exp, exp))
    k.commit()
    k.close()


def _count(path, sql, *a):
    k = sqlite3.connect(path)
    try:
        return k.execute(sql, a).fetchone()[0]
    finally:
        k.close()


def test_setup_token_web_claim_creates_one_operator(dbp):
    _mk_setup_token(dbp, "tok-w")
    idx = iter(range(100))
    lock = threading.Lock()

    def claim(k):
        with lock:
            i = next(idx)
        return complete_initial_setup(k, "tok-w", f"W{i}", f"w{i}@t.test", "Str0ng!Passw0rd")

    res = _race(dbp, claim)
    assert sum(1 for r in res if isinstance(r, dict)) == 1
    assert _count(dbp, "SELECT COUNT(*) FROM operators WHERE email LIKE 'w%@t.test'") == 1
    assert _count(dbp, "SELECT used_at IS NOT NULL FROM setup_tokens") == 1


def test_setup_token_failed_insert_does_not_burn_token(dbp):
    _mk_setup_token(dbp, "tok-dup")
    k = dbm.connect(dbp)
    k.row_factory = sqlite3.Row
    # The identity pre-check (WP-7) refuses the taken email with a ValueError
    # before the claim; a race that slips past it still hits the UNIQUE index.
    # Either way the token must stay unused.
    with pytest.raises((sqlite3.IntegrityError, ValueError)):
        complete_initial_setup(k, "tok-dup", "D", "m@t.test", "Str0ng!Passw0rd")  # email exists
    k.close()
    assert _count(dbp, "SELECT used_at IS NULL FROM setup_tokens") == 1


def test_setup_token_mobile_claim_creates_one_operator(dbp, monkeypatch):
    monkeypatch.setenv("AMLKIT_DB", dbp)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    _mk_setup_token(dbp, "tok-m")
    codes = []

    def mob(i):
        codes.append(TestClient(app, raise_server_exceptions=False).post("/api/v1/auth/setup", json={
            "token": "tok-m", "name": f"M{i}", "email": f"mob{i}@t.test", "password": "Str0ng!Passw0rd"}).status_code)

    barrier = threading.Barrier(N)

    def go(i):
        barrier.wait()
        mob(i)

    th = [threading.Thread(target=go, args=(i,)) for i in range(N)]
    [t.start() for t in th]
    [t.join() for t in th]
    assert _count(dbp, "SELECT COUNT(*) FROM operators WHERE email LIKE 'mob%@t.test'") == 1
    assert codes.count(200) == 1


def test_backup_code_single_use_under_concurrency(dbp):
    w = dbm.connect(dbp)
    code = auth._generate_backup_codes(w, 1)[0]
    w.commit()
    w.close()
    res = _race(dbp, lambda k: auth.mfa_verify_backup_code(k, 1, code), n=2)
    assert res.count(True) == 1, res


def test_email_verify_token_single_use_under_concurrency(dbp):
    w = dbm.connect(dbp)
    raw = auth.create_email_verify_token(w, 1)
    w.commit()
    w.close()
    res = _race(dbp, lambda k: auth.consume_email_verify_token(k, raw) is not None)
    assert res.count(True) == 1, res


def test_uaepass_state_single_use_under_concurrency(dbp):
    w = dbm.connect(dbp)
    st = auth.create_uaepass_state(w, purpose="operator_sso", redirect_uri="http://localhost/cb")
    w.commit()
    w.close()
    res = _race(dbp, lambda k: auth.consume_uaepass_state(k, st, purpose="operator_sso") is not None)
    assert res.count(True) == 1, res


def test_email_verify_token_twice_sequential(dbp):
    w = dbm.connect(dbp)
    raw = auth.create_email_verify_token(w, 1)
    w.commit()
    assert auth.consume_email_verify_token(w, raw) is not None
    assert auth.consume_email_verify_token(w, raw) is None


# ------------------------------------------------------------------ TOTP replay
def _enrol(path):
    w = dbm.connect(path)
    w.row_factory = sqlite3.Row
    secret = pyotp.random_base32()
    w.execute("INSERT INTO mfa_secrets (operator_id, secret, enrolled_at, confirmed_at, failed_attempts)"
              " VALUES (1, ?, ?, ?, 0)", (secret, dbm.utcnow(), dbm.utcnow()))
    w.commit()
    return w, secret


def test_totp_code_accepted_once(dbp):
    w, secret = _enrol(dbp)
    code = pyotp.TOTP(secret).at(datetime.now(timezone.utc))
    assert auth.mfa_verify(w, 1, code, confirmed_only=True) is True
    assert auth.mfa_verify(w, 1, code, confirmed_only=True) is False


def test_totp_next_step_code_still_works_and_older_refused(dbp):
    w, secret = _enrol(dbp)
    totp = pyotp.TOTP(secret)
    now = datetime.now(timezone.utc)
    prev = totp.at(now - timedelta(seconds=30))
    cur = totp.at(now)
    assert auth.mfa_verify(w, 1, cur, confirmed_only=True) is True
    assert auth.mfa_verify(w, 1, prev, confirmed_only=True) is False  # older step than the stored one
    assert auth.mfa_verify(w, 1, "000000", confirmed_only=True) is False


def test_totp_same_code_concurrently_one_success(dbp):
    w, secret = _enrol(dbp)
    w.close()
    code = pyotp.TOTP(secret).at(datetime.now(timezone.utc))
    res = _race(dbp, lambda k: auth.mfa_verify(k, 1, code, confirmed_only=True), n=2)
    assert res.count(True) == 1, res

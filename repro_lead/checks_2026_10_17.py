"""Lead 2026-10-17 checks. Local temp DB and synthetic data only; no network.

Exit 0 when ALL of these reproduce on the checked-out SHA:
  T1m - mobile POST /api/v1/auth/setup (mobile.py:446-479) reads the token,
        inserts the operator, then runs an unconditional
        UPDATE setup_tokens SET used_at=? WHERE id=?. 10 concurrent claims of
        one token create more than one MLRO operator.
  T1w - web path cases/operators.py:complete_initial_setup (lines 91-143) has
        the same read / insert / unconditional update shape. 10 threads, each
        on its own connection, claim one token: more than one operator.
  T2  - mobile setup: an email already in use returns HTTP 500 and leaves the
        token unused; 'not-an-email' is accepted and creates an MLRO.
  BC  - (skeptic's 'what the team missed' #1) auth.mfa_verify_backup_code
        (auth.py:839-859) reads unused codes, verifies, then updates used_at
        with no 'AND used_at IS NULL'. Two concurrent uses of ONE backup code
        both return True.
Exit 1 when any is fixed (re-read the printed lines).
"""
import os, sys, tempfile, threading, sqlite3
from hashlib import sha256
from datetime import datetime, timezone, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
DBP = os.path.join(tempfile.mkdtemp(), "web.db")
os.environ["AMLKIT_DB"] = DBP
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = "test-invite"
os.environ.pop("AMLKIT_SMTP_HOST", None)
import logging; logging.disable(logging.CRITICAL)

from fastapi.testclient import TestClient
from amlkit import db as dbm, auth
from amlkit.api.app import app
from amlkit.cases.operators import complete_initial_setup
from test_api import _register

c = TestClient(app, raise_server_exceptions=False)
_register(c, "Org T", "Tia Lead", "tia@t.test")
w = dbm.connect(DBP)
org_id, op_id = w.execute("SELECT org_id, id FROM operators WHERE email='tia@t.test'").fetchone()


def q(sql, *a):
    k = sqlite3.connect(DBP, timeout=30); r = k.execute(sql, a).fetchall(); k.commit(); k.close(); return r


def mk_token(raw):
    exp = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec="seconds")
    q("INSERT INTO setup_tokens (org_id, token_hash, created_at, expires_at) VALUES (?,?,?,?)",
      org_id, sha256(raw.encode()).hexdigest(), exp, exp)


ok = 0
N = 10

mk_token("tok-m")
codes = []
def mob(i):
    codes.append(TestClient(app, raise_server_exceptions=False).post("/api/v1/auth/setup", json={
        "token": "tok-m", "name": f"M{i}", "email": f"m{i}@t.test", "password": "Str0ng!Passw0rd"}).status_code)
th = [threading.Thread(target=mob, args=(i,)) for i in range(N)]; [t.start() for t in th]; [t.join() for t in th]
n_m = q("SELECT COUNT(*) FROM operators WHERE email LIKE 'm%@t.test'")[0][0]
t1m = n_m > 1
print(f"T1m {N} concurrent mobile claims of one token: statuses={sorted(codes)} operators={n_m} -> reproduces={t1m}")
ok += t1m

mk_token("tok-w")
res = []
def web(i):
    k = dbm.connect(DBP)
    try:
        complete_initial_setup(k, "tok-w", f"W{i}", f"w{i}@t.test", "Str0ng!Passw0rd"); res.append("ok")
    except Exception as e:  # noqa: BLE001
        res.append(type(e).__name__)
    finally:
        k.close()
th = [threading.Thread(target=web, args=(i,)) for i in range(N)]; [t.start() for t in th]; [t.join() for t in th]
n_w = q("SELECT COUNT(*) FROM operators WHERE email LIKE 'w%@t.test'")[0][0]
t1w = n_w > 1
print(f"T1w {N} concurrent complete_initial_setup calls on one token: results={sorted(res)} operators={n_w} -> reproduces={t1w}")
ok += t1w

mk_token("tok-dup")
r = c.post("/api/v1/auth/setup", json={"token": "tok-dup", "name": "D", "email": "tia@t.test", "password": "Str0ng!Passw0rd"})
unused = q("SELECT used_at IS NULL FROM setup_tokens WHERE token_hash=?", sha256(b"tok-dup").hexdigest())[0][0]
mk_token("tok-bad")
r2 = c.post("/api/v1/auth/setup", json={"token": "tok-bad", "name": "B", "email": "not-an-email", "password": "Str0ng!Passw0rd"})
made = bool(q("SELECT 1 FROM operators WHERE email='not-an-email'"))
t2 = r.status_code == 500 and unused == 1 and r2.status_code == 200 and made
print(f"T2  existing email -> {r.status_code}, token still unused={bool(unused)}; 'not-an-email' -> {r2.status_code}, "
      f"created={made} -> reproduces={t2}")
ok += t2

plain = auth._generate_backup_codes(w, op_id); w.commit()
code = plain[0]
bres = []
barrier = threading.Barrier(2)
def use():
    k = dbm.connect(DBP)
    barrier.wait()
    try:
        bres.append(auth.mfa_verify_backup_code(k, op_id, code))
    finally:
        k.close()
th = [threading.Thread(target=use) for _ in range(2)]; [t.start() for t in th]; [t.join() for t in th]
bc = bres.count(True) > 1
print(f"BC  same backup code used twice concurrently: results={bres} -> reproduces={bc}")
ok += bc

sys.exit(0 if ok == 4 else 1)

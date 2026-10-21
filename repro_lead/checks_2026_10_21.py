"""Lead repro, 2026-10-21. Exits 0 when every defect below reproduces.

New findings from today's role reports:
  LG2 - account enumeration via the lockout message: 9 wrong passwords on a
        real email give "Account locked ... Try again after HH:MM UTC";
        9 on an unknown email keep "Incorrect email or password."
        (auth.py:376-383 vs the docstring promise at auth.py:347-351).
  LG3 - POST /login with an empty password -> raw 422 JSON, not the login page.
Refutation check (printed, not counted towards the exit code):
  LG4 - with the limiter enabled (the suite and the mlro driver switch it
        off), repeated POST /login from one client does return 429.

Local scratch DB only, no network. Run from the repo root:
  PYTHONPATH=.:tests python repro_lead/checks_2026_10_21.py
"""
import os, sqlite3, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
tmp = tempfile.mkdtemp()
os.environ["AMLKIT_DB"] = os.path.join(tmp, "web.db")
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = "test-invite"
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)
import logging; logging.disable(logging.CRITICAL)

from amlkit import auth, db as dbm
from test_api import _seed_sanctions_data, _register, _csrf
from fastapi.testclient import TestClient
from amlkit.api.app import app, limiter

_seed_sanctions_data(os.environ["AMLKIT_DB"])
dbm._reset_init_cache(); limiter.reset(); limiter.enabled = False
ok, need = 0, 0

cl = TestClient(app, raise_server_exceptions=False)
_register(cl, "Lead Firm", "Lena", "lena@lead.test")

# ---- LG2 --------------------------------------------------------------------
def last_msg(email):
    msg = None
    for _ in range(9):
        k = dbm.connect(os.environ["AMLKIT_DB"])
        try:
            auth.login(k, email, "wrong-password-xx")
        except auth.AuthError as e:
            msg = str(e)
        finally:
            k.commit(); k.close()
    return msg
real, unknown = last_msg("lena@lead.test"), last_msg("nobody@lead.test")
lg2 = real.startswith("Account locked") and unknown == "Incorrect email or password."
print(f"LG2 9 bad logins: real email -> {real[:40]!r}...; unknown email -> {unknown!r} -> reproduces={lg2}")
ok += lg2; need += 1

# ---- LG3 --------------------------------------------------------------------
c2 = TestClient(app, raise_server_exceptions=False)
c2.get("/login")
r = c2.post("/login", data={"email": "x@lead.test", "password": "", "csrf_token": _csrf(c2)})
lg3 = r.status_code == 422 and r.headers.get("content-type", "").startswith("application/json")
print(f"LG3 empty password -> {r.status_code} {r.headers.get('content-type')} -> reproduces={lg3}")
ok += lg3; need += 1

# ---- LG4 (refutation only) --------------------------------------------------
limiter.reset(); limiter.enabled = True
try:
    c3 = TestClient(app, raise_server_exceptions=False)
    c3.get("/login")
    codes = [c3.post("/login", data={"email": f"u{i}@lead.test", "password": "bad-password-xx",
                                     "csrf_token": _csrf(c3)}).status_code for i in range(12)]
finally:
    limiter.enabled = False
print(f"LG4 limiter ON, 12 POST /login one client, distinct emails -> {codes} -> 429 seen={429 in codes} (finding refuted if True)")

print(f"{ok}/{need} reproduce")
sys.exit(0 if ok == need else 1)

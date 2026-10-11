"""Lead 2026-10-11 checks. Local temp DBs and synthetic data only; no network
(every sanctions adapter is replaced by one that raises AdapterError).

Exit 0 when ALL of these reproduce on the checked-out SHA:
  A1   - login lockout never resets failed_login_count when the lock expires,
         so ONE wrong password after expiry re-locks the account
         (auth.py:376-404; reset only on success/set_password).
  OP1  - admin reset-password with a 10+ char password that fails the
         complexity rule raises PasswordComplexityError (HTTP 500)
         (app.py:3475-3478 checks length only; auth.set_password validates).
  OP2  - admin "Add operator" accepts a password that fails the complexity
         rule (app.py:3533 length only, app.py:3552 hashes directly).
  GR   - any org's MLRO pressing /admin/refresh re-screens EVERY active org
         and the other org's screening.run audit rows carry that MLRO's name
         (scheduler.py:96-100 passes actor through to rescreen_all).
Informational (not in the exit code):
  SSO  - resolve_uaepass_operator() ignores locked_until, so a UAE-PASS-linked
         operator can still sign in while password-locked (mitigates A1 only
         where real UAE PASS linking exists).
Exit 1 when any of A1/OP1/OP2/GR is fixed (re-read the printed lines).
"""
import os, sys, tempfile
from datetime import datetime, timedelta, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
tmp = tempfile.mkdtemp()
os.environ["AMLKIT_DB"] = os.path.join(tmp, "web.db")
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = "test-invite"
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)

from amlkit import auth, db as dbm

# ---- A1 + SSO: auth layer on :memory: ------------------------------------
c = dbm.connect(":memory:"); now = dbm.utcnow()
c.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)", (now,))
c.execute("INSERT INTO operators (org_id,email,password_hash,name,role,is_active,email_verified_at,created_at,uaepass_uuid)"
          " VALUES (1,'mlro@t.test',?,'M','mlro',1,?,?,'uuid-lead-1')",
          (auth.hash_password("Correct#Horse9"), now, now)); c.commit()

def attempt(pw):
    try:
        auth.login(c, "mlro@t.test", pw); return "OK"
    except auth.AuthError as e:
        return str(e)[:60]

row = lambda: tuple(c.execute("SELECT failed_login_count, locked_until FROM operators").fetchone())
for _ in range(auth.MAX_FAILED_LOGINS):
    attempt("wrong")
c.execute("UPDATE operators SET locked_until=? WHERE id=1",
          ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds"),)); c.commit()
expired = row()
attempt("wrong")
relocked = row()
correct = attempt("Correct#Horse9")
a1 = relocked[0] > auth.MAX_FAILED_LOGINS and correct != "OK"
print(f"A1   expired={expired} after ONE wrong={relocked} correct pw -> {correct!r} -> reproduces={a1}")

from amlkit.uaepass import UaePassProfile
import dataclasses
fields = {f.name: None for f in dataclasses.fields(UaePassProfile)}
fields.update(uuid="uuid-lead-1", raw={})
op, _ = auth.resolve_uaepass_operator(c, UaePassProfile(**fields))
print(f"SSO  password-locked operator resolved by UAE PASS uuid: {op is not None} (informational)")

# ---- OP1 / OP2 / GR: HTTP ------------------------------------------------
from fastapi.testclient import TestClient
from amlkit.api.app import app
from test_api import _register, _csrf

a = TestClient(app, raise_server_exceptions=False)
_register(a, "Org A", "Alice Lead", "alice@a.test")
r = a.post("/admin/operators", data={"name": "Weak Pw", "email": "weak@a.test", "password": "aaaaaaaaaa",
                                    "role": "officer", "csrf_token": _csrf(a)}, follow_redirects=True)
w = dbm.connect(os.environ["AMLKIT_DB"])
weak = w.execute("SELECT id FROM operators WHERE email='weak@a.test'").fetchone()
op2 = weak is not None
print(f"OP2  admin create with 'aaaaaaaaaa': status={r.status_code} account_created={op2} -> reproduces={op2}")

r = a.post(f"/admin/operators/{weak[0] if weak else 0}/reset-password",
           data={"new_password": "1234567890", "csrf_token": _csrf(a)}, follow_redirects=True)
op1 = r.status_code == 500
print(f"OP1  admin reset to '1234567890': status={r.status_code} -> reproduces={op1}")

b = TestClient(app, raise_server_exceptions=False)
_register(b, "Org B", "Bob Other", "bob@b.test")
from conftest import seed_fresh_dataset
_s = dbm.connect(os.environ["AMLKIT_DB"]); seed_fresh_dataset(_s); _s.commit(); _s.close()
b.get("/customers/new")
rc = b.post("/customers", data={"reference": "B-1", "full_name": "Bravo Customer",
                           "csrf_token": _csrf(b)}, follow_redirects=True)

from amlkit.ingest import loader
from amlkit.ingest.base import AdapterError
def _no_network(conn, adapter, actor="system"):
    raise AdapterError("network disabled in lead repro")
loader.load = _no_network
r = a.post("/admin/refresh", data={"csrf_token": _csrf(a)}, follow_redirects=True)
w = dbm.connect(os.environ["AMLKIT_DB"])
org_b = w.execute("SELECT id FROM organizations WHERE name='Org B'").fetchone()[0]
b_actors = sorted({r_[0] for r_ in w.execute(
    "SELECT actor FROM audit_log WHERE org_id=? AND action='screening.run'", (org_b,))})
gr = "Alice Lead" in b_actors
print(f"GR   Org A MLRO /admin/refresh -> Org B screening.run actors={b_actors} -> reproduces={gr}")

sys.exit(0 if (a1 and op1 and op2 and gr) else 1)

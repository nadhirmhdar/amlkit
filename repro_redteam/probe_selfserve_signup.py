"""Red-team 2026-11-04: PR #457/#458 self-serve sign-up (STRIPE_SECRET_KEY set => no invite code, orgs start pending_payment).
What can an UNPAID org still do? Account enumeration via the open registration form; mail to third-party addresses; rate limit. LOCAL ONLY; Stripe never contacted."""
import os, re, sqlite3, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
db = Path(tempfile.mkdtemp())/"s.db"
os.environ.update({"AMLKIT_DB": str(db), "STRIPE_SECRET_KEY": "sk_test_x", "STRIPE_WEBHOOK_SECRET": "whsec_x", "STRIPE_PRICE_STARTER": "price_s", "AMLKIT_REGISTRATION_INVITE_CODE": "not-needed"})
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth, mail
from amlkit.api.app import app, limiter
limiter.reset(); sent = []
mail.send_verification_email = lambda to, name, tok: (sent.append((to, name, tok)), mail.SENT)[1]
cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False)
def q(sql, *a):
    c = sqlite3.connect(db); r = c.execute(sql, a).fetchall(); c.commit(); c.close(); return r
def csrf(c=None): (c or cl).get("/register-organization"); return (c or cl).cookies.get(auth.CSRF_COOKIE)
def reg(email, org, name="Eve", pw="Str0ng!Passw0rd", c=None):
    c = c or cl; limiter.reset(); return c.post("/register-organization", data={"org_name": org, "name": name, "email": email, "password": pw, "invite_code": "", "csrf_token": csrf(c)})
print("== 1. open registration (no invite code) ==")
print(" GET form mentions invite field:", "invite" in cl.get("/register-organization").text.lower())
r = reg("eve@evil.test", "Evil Co"); print(" register without invite ->", r.status_code, "| org:", q("select name, plan, plan_status from organizations where name='Evil Co'"), "| verify mail queued to:", [s[0] for s in sent])
print("== 2. account enumeration through the public form ==")
r1 = reg("eve@evil.test", "Evil Co 2"); r2 = reg("nobody-here@evil.test", "Evil Co 3")
print(" existing email  ->", r1.status_code, "| says exists:", "already exists" in r1.text)
print(" unknown email   ->", r2.status_code, "| says exists:", "already exists" in r2.text, "(difference = enumeration oracle)")
print("== 3. mail to a third party (victim) ==")
n = len(sent); reg("victim@bank.test", "Victim Squat"); print(" verification mail queued to victim@bank.test:", len(sent) > n, "| carries attacker-chosen name:", sent[-1][1:2])
print("== 4. what can an unpaid (pending_payment) org still do? ==")
tok = [s[2] for s in sent if s[0] == "eve@evil.test"][0]
r = cl.get(f"/verify-email?token={tok}"); print(" verify email ->", r.status_code, r.headers.get("location"), "| session cookie:", bool(cl.cookies.get(auth.SESSION_COOKIE)))
sess = cl.cookies.get(auth.SESSION_COOKIE); 
op = q("select o.id, o.org_id, o.role from operators o where lower(email)='eve@evil.test'")[0]
print(" operator:", op, "| org plan:", q("select plan, plan_status from organizations where id=?", op[1]))
mc = TestClient(app, follow_redirects=False, raise_server_exceptions=False)
c = sqlite3.connect(db); from amlkit.db import connect; cc = connect(db); mtok = auth.create_session(cc, op[0], op[1], mfa_verified=True); cc.close()
mc.cookies.set(auth.SESSION_COOKIE, mtok); H = {"Authorization": f"Bearer {mtok}"}; mc.get("/dashboard"); limiter.reset()
def show(label, r): print(f" {label:44s} -> {r.status_code} {r.text[:80]!r}")
show("mobile POST /screen (ad-hoc screening)", mc.post("/api/v1/screen", json={"name": "Mohammed Al Testlisted"}, headers=H))
show("mobile POST /customers (onboard)", mc.post("/api/v1/customers", json={"reference": "R-1", "full_name": "Ann Test", "customer_type": "natural", "nationality": "AE", "country": "AE"}, headers=H))
show("mobile POST /admin/operators", mc.post("/api/v1/admin/operators", json={"name": "B", "email": "b@evil.test", "password": "Str0ng!Passw0rd", "role": "officer"}, headers=H))
show("mobile GET /customers", mc.get("/api/v1/customers", headers=H))
tk = mc.cookies.get(auth.CSRF_COOKIE)
show("web POST /screen (ad-hoc)", mc.post("/screen", data={"name": "Mohammed Al Testlisted", "csrf_token": tk}))
n0 = q("select count(*) from screenings where org_id=?", op[1])[0][0]
for i in range(30): limiter.reset(); mc.post("/api/v1/screen", json={"name": f"Name Number{i}"}, headers=H)
print(" ad-hoc screenings stored for the unpaid org after 30 calls:", q("select count(*) from screenings where org_id=?", op[1])[0][0] - n0)
print(" screenings + audit rows are written under the unpaid org: yes" if q("select count(*) from audit_log where org_id=?", op[1])[0][0] else "")
print("== 5. registration rate limit (per IP) ==")
codes = []
limiter.reset()
for i in range(8):
    c2 = TestClient(app, follow_redirects=False, raise_server_exceptions=False); tk2 = csrf(c2)
    codes.append(c2.post("/register-organization", data={"org_name": f"Bulk {i}", "name": "Bot", "email": f"bot{i}@x.test", "password": "Str0ng!Passw0rd", "csrf_token": tk2}).status_code)
print(" 8 rapid registrations:", codes, "| orgs now:", q("select count(*) from organizations")[0][0])

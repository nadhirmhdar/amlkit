"""Red-team 2026-11-01: PR #434 Stripe billing (amlkit/api/billing.py, amlkit/billing/*). Inert-when-unconfigured, webhook signature edge cases, authz/CSRF on
/billing*, replay. LOCAL ONLY; no network to Stripe (checkout/portal creation is not exercised). Needs fixtures/ from PR #412 make_seed."""
import json, os, shutil, sqlite3, sys, tempfile, time, hmac, hashlib
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); B = ids["B"]
db = Path(tempfile.mkdtemp())/"s.db"; os.environ["AMLKIT_DB"] = str(db); shutil.copy(ROOT/"fixtures"/"seed.db", db)
for k in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"): os.environ.pop(k, None)
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.db import connect, _reset_init_cache
_reset_init_cache(); limiter.reset()
c = connect(db); tm = auth.create_session(c, B["mlro_id"], B["org_id"], mfa_verified=True)
op = c.execute("select id from operators where org_id=? and role!='mlro' limit 1", (B["org_id"],)).fetchone(); to = auth.create_session(c, op[0], B["org_id"]) if op else None; c.close()
def client(tok): cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False); cl.cookies.set(auth.SESSION_COOKIE, tok) if tok else None; cl.get("/dashboard"); return cl
anon, mlro, off = client(None), client(tm), client(to) if to else None
def sig(payload, secret, ts=None, extra=""):
    ts = int(time.time()) if ts is None else ts; s = hmac.new(secret.encode(), f"{ts}.".encode()+payload, hashlib.sha256).hexdigest(); return f"t={ts},v1={s}{extra}"
print("== 1. inert when STRIPE_SECRET_KEY is unset ==")
for m, p in [("get", "/pricing"), ("get", "/billing"), ("post", "/billing/webhook"), ("post", "/billing/checkout"), ("get", "/billing/success")]:
    r = getattr(mlro, m)(p); print(f" {m.upper():4s} {p:20s} -> {r.status_code}")
os.environ.update({"STRIPE_SECRET_KEY": "sk_test_x", "STRIPE_WEBHOOK_SECRET": "whsec_test", "STRIPE_PRICE_STARTER": "price_s"})
print("== 2. webhook signature edge cases (configured) ==")
body = json.dumps({"id": "evt_1", "type": "ping", "data": {"object": {}}}).encode(); S = "whsec_test"
cases = {"no header": None, "garbage header": "abc", "wrong secret": sig(body, "whsec_other"), "stale timestamp (1h)": sig(body, S, ts=int(time.time())-3600),
         "future timestamp (+1h)": sig(body, S, ts=int(time.time())+3600), "valid": sig(body, S), "valid + junk v1": sig(body, S, extra=",v1=00"),
         "empty v1 only": f"t={int(time.time())},v1=", "t missing": "v1=" + hmac.new(S.encode(), b".", hashlib.sha256).hexdigest(), "body tampered": sig(body, S)}
for label, h in cases.items():
    limiter.reset(); b = body + b" " if label == "body tampered" else body
    r = anon.post("/billing/webhook", content=b, headers={"Stripe-Signature": h} if h else {}); print(f" {label:24s} -> {r.status_code} {r.text[:60]}")
limiter.reset(); r = anon.post("/billing/webhook", content=body, headers={"Stripe-Signature": sig(body, S)}); print(" replay of the valid event ->", r.status_code, r.text[:50])
os.environ["STRIPE_WEBHOOK_SECRET"] = ""; limiter.reset(); r = anon.post("/billing/webhook", content=body, headers={"Stripe-Signature": sig(body, "")}); print(" webhook secret unset but key set; signed with empty secret ->", r.status_code); os.environ["STRIPE_WEBHOOK_SECRET"] = S
print("== 3. authz / CSRF on /billing* ==")
print(" anon GET /billing ->", anon.get("/billing").status_code, anon.get("/billing").headers.get("location"))
if off: print(" officer GET /billing ->", off.get("/billing").status_code, off.get("/billing").headers.get("location"), "| officer POST checkout (no csrf) ->", off.post("/billing/checkout", data={"tier": "starter"}).status_code)
print(" MLRO POST checkout, no csrf ->", mlro.post("/billing/checkout", data={"tier": "starter", "csrf_token": ""}).status_code, "| portal no csrf ->", mlro.post("/billing/portal", data={"csrf_token": ""}).status_code)
print(" MLRO checkout bogus tier + valid csrf ->", mlro.post("/billing/checkout", data={"tier": "../../x", "csrf_token": mlro.cookies.get(auth.CSRF_COOKIE)}).status_code)

"""Red-team 2026-11-07: Stripe webhook state machine (billing/service.py) driven with LOCALLY signed events (test secret): pending_payment -> trialing on
checkout, out-of-order and superseded-subscription events, deletion + grace, unknown org/price/tier, junk shapes, replay, oversized body. LOCAL ONLY; Stripe never contacted."""
import hashlib, hmac, json, os, sqlite3, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
db = Path(tempfile.mkdtemp())/"s.db"; S = "whsec_probe"
os.environ.update({"AMLKIT_DB": str(db), "STRIPE_SECRET_KEY": "sk_test_x", "STRIPE_WEBHOOK_SECRET": S, "STRIPE_PRICE_STARTER": "price_s", "STRIPE_PRICE_PROFESSIONAL": "price_p"})
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth, mail
from amlkit.api.app import app, limiter
from amlkit.billing import limits
from amlkit.db import connect
mail.send_verification_email = lambda *a: mail.SENT
cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False); cl.get("/register-organization"); limiter.reset()
for n, e in (("A", "a@x.test"), ("B", "b@x.test")):
    limiter.reset(); cl.post("/register-organization", data={"org_name": f"Org {n}", "name": n, "email": e, "password": "Str0ng!Passw0rd", "csrf_token": cl.cookies.get(auth.CSRF_COOKIE)})
def q(sql, *a):
    c = sqlite3.connect(db); r = c.execute(sql, a).fetchall(); c.commit(); c.close(); return r
A, B = [r[0] for r in q("select id from organizations order by id")]
def post(ev, secret=S, ts=None):
    body = json.dumps(ev).encode(); ts = int(time.time()) if ts is None else ts
    sig = hmac.new(secret.encode(), f"{ts}.".encode()+body, hashlib.sha256).hexdigest(); limiter.reset()
    r = cl.post("/billing/webhook", content=body, headers={"Stripe-Signature": f"t={ts},v1={sig}"}); return r.status_code, r.text.strip()[:40]
def st(o): return q("select plan, plan_status, billing_subscription_id, billing_customer_id from organizations where id=?", o)[0]
now = int(time.time()); n = [0]
def ev(t, obj, created=None): n[0] += 1; return {"id": f"evt_{n[0]}", "type": t, "created": created or now, "data": {"object": obj}}
sub = lambda sid, status="trialing", price="price_s", cust="cus_A", org=A, **k: {"id": sid, "status": status, "customer": cust, "metadata": {"org_id": str(org)}, "items": {"data": [{"price": {"id": price}, "current_period_end": now + 86400*365}]}, "trial_end": now + 86400*14, **k}
print("start: A", st(A), "| B", st(B))
print("1 checkout.session.completed ->", post(ev("checkout.session.completed", {"client_reference_id": str(A), "customer": "cus_A", "subscription": "sub_1", "metadata": {"tier": "starter", "org_id": str(A)}})), "A:", st(A))
print("2 subscription.updated -> professional ->", post(ev("customer.subscription.updated", sub("sub_1", "active", "price_p"), created=now+10)), "A:", st(A))
print("3 OLDER update (created < last) is ignored ->", post(ev("customer.subscription.updated", sub("sub_1", "past_due", "price_s"), created=now+5)), "A:", st(A))
print("4 superseded sub_old update cannot overwrite live sub ->", post(ev("customer.subscription.updated", sub("sub_old", "canceled", "price_s"), created=now+20)), "A:", st(A))
print("5 attacker-style: sub event for customer cus_A but metadata org_id=B ->", post(ev("customer.subscription.updated", sub("sub_1", "active", "price_p", org=B), created=now+30)), "A:", st(A), "| B:", st(B))
print("6 brand-new customer cus_X with metadata org_id=B (only Stripe can send this) ->", post(ev("customer.subscription.created", sub("sub_x", "active", "price_p", cust="cus_X", org=B), created=now+40)), "| B:", st(B))
print("7 unknown price + unknown tier keeps plan ->", post(ev("customer.subscription.updated", sub("sub_1", "active", "price_zzz", metadata={"org_id": str(A), "tier": "enterprise-free"}), created=now+50)), "A:", st(A))
print("8 deleted ->", post(ev("customer.subscription.deleted", sub("sub_1", "active"), created=now+60)), "A:", st(A))
for label, e in [("string created", ev("customer.subscription.updated", sub("sub_1"), created="x")), ("data=None", {"id": "evt_n", "type": "invoice.paid", "data": None}), ("object is list", ev("invoice.paid", [])),
                 ("status unknown", ev("customer.subscription.updated", sub("sub_1", "zzz"), created=now+70)), ("huge trial_end", ev("customer.subscription.updated", sub("sub_1", trial_end=10**30), created=now+80)),
                 ("items not list", ev("customer.subscription.updated", {**sub("sub_1"), "items": {"data": "x"}}, created=now+90)), ("type unhandled", ev("ping.pong", {}))]:
    try: print(f"junk: {label:16s} ->", post(e))
    except Exception as x: print(f"junk: {label:16s} -> EXC {type(x).__name__}")
print("replay of evt_1 ->", post(ev("checkout.session.completed", {})) if False else post({**ev("x", {}), "id": "evt_1"}))
print("body 2 MB ->", post({"id": "evt_big", "type": "ping.pong", "data": {"object": {"x": "A"*2_000_000}}}))
c = connect(db)
q("update organizations set plan_status='canceled', current_period_end=? where id=?", __import__("datetime").datetime.fromtimestamp(now-86400*9, __import__("datetime").timezone.utc).isoformat(), A)
try: limits.check_limit(c, A, "operators"); print("9 canceled > 7 days ago: creation allowed (!)")
except limits.BillingLimitError as e_: print("9 canceled > 7 days ago: creation refused ->", str(e_)[:60])
print("billing_events stored:", q("select count(*) from billing_events")[0][0], "| 500s above would show as 'processing failed'")

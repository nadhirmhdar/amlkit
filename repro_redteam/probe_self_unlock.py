"""Red-team 2026-11-02: PR #443 email-link self-unlock (GET /unlock/{token}, auth.create_unlock_token/consume_unlock_token). Token lifecycle, concurrency,
scope (password lock only), re-lock loop (A1 residual), enumeration, tenant. LOCAL ONLY (needs fixtures/ from PR #412 make_seed)."""
import json, os, shutil, sqlite3, sys, tempfile, threading, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); A, B = ids["A"], ids["B"]
db = Path(tempfile.mkdtemp())/"s.db"; os.environ["AMLKIT_DB"] = str(db); shutil.copy(ROOT/"fixtures"/"seed.db", db)
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth, mail
from amlkit.api.app import app, limiter
from amlkit.db import connect, _reset_init_cache
_reset_init_cache(); limiter.reset()
sent = []
mail.send_unlock_email = lambda to, name, raw: (sent.append((to, raw)), mail.SENT)[1]
def q(sql, *a):
    c = sqlite3.connect(db); r = c.execute(sql, a).fetchall(); c.commit(); c.close(); return r
cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False)
mlro_email = q("select email from operators where id=?", B["mlro_id"])[0][0]; PW = "a-strong-password-1"
def csrf(): cl.get("/login"); return cl.cookies.get(auth.CSRF_COOKIE)
def login(email, pw): limiter.reset(); return cl.post("/login", data={"email": email, "password": pw, "csrf_token": csrf()})
def lock(email=mlro_email, n=8):
    for _ in range(n): login(email, "wrong-password-xyz")
print("== 1. lock -> one mail per lock window ==")
lock(); print(" mails after 8 failures:", len(sent), "| to:", {s[0] for s in sent}); lock(n=5); print(" mails after 5 more failures while locked:", len(sent))
print(" correct password while locked ->", login(mlro_email, PW).status_code, "(303 = signed in; 200 = refused)")
tok = sent[0][1] if sent else "x"
print("== 2. redeem ==")
r = cl.get(f"/unlock/{tok}"); print(" first GET /unlock/<token> ->", r.status_code, r.headers.get("location"), "| locked_until now:", q("select failed_login_count, locked_until from operators where id=?", B["mlro_id"]))
r = cl.get(f"/unlock/{tok}"); print(" reuse ->", r.status_code, "generic page:", "invalid, expired, or already used" in r.text)
print(" correct password now ->", login(mlro_email, PW).status_code)
print("== 3. enumeration / garbage ==")
for t in ["", "x", "A"*5000, "%00", "../etc/passwd", "ü"]:
    limiter.reset(); r = cl.get(f"/unlock/{t}" if t else "/unlock/"); print(f" token {t[:12]!r:16s} -> {r.status_code} generic={'invalid, expired, or already used' in r.text}")
print("== 4. expiry / deactivated / scope ==")
lock(); tok2 = sent[-1][1]; q("update unlock_tokens set expires_at=? where token_hash is not null and used_at is null", (datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(timespec="seconds"))
print(" expired token ->", "ok" if "invalid, expired" in cl.get(f"/unlock/{tok2}").text else "REDEEMED")
c = connect(db); t3 = auth.create_unlock_token(c, B["mlro_id"]); c.close(); q("update operators set is_active=0 where id=?", B["mlro_id"])
print(" deactivated operator ->", "refused" if "invalid, expired" in cl.get(f"/unlock/{t3}").text else "REDEEMED"); q("update operators set is_active=1 where id=?", B["mlro_id"])
c = connect(db); auth.mfa_enroll(c, B["mlro_id"]); auth.mfa_confirm(c, B["mlro_id"]) if False else None; t4 = auth.create_unlock_token(c, B["mlro_id"]); c.close(); q("update mfa_secrets set failed_attempts=5, locked_until=? where operator_id=?", (datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat(timespec="seconds"), B["mlro_id"])
cl.get(f"/unlock/{t4}"); print(" MFA lock after unlock link:", q("select failed_attempts, locked_until is not null from mfa_secrets where operator_id=?", B["mlro_id"]), "(must stay locked)")
print("== 5. concurrency: 20 threads redeem one token ==")
c = connect(db); t5 = auth.create_unlock_token(c, B["mlro_id"]); c.close(); out = []
def go(): out.append("ok" if "Your account is unlocked" in TestClient(app, follow_redirects=True).get(f"/unlock/{t5}").text or True else "")
res = []
def go():
    r = TestClient(app, follow_redirects=False, raise_server_exceptions=False).get(f"/unlock/{t5}"); res.append(r.status_code)
th = [threading.Thread(target=go) for _ in range(20)]; [t.start() for t in th]; [t.join() for t in th]; limiter.reset()
print(" statuses:", {k: res.count(k) for k in set(res)}, "| audit self_unlock rows for this operator:", q("select count(*) from audit_log where action='operator.self_unlock'")[0][0])
print("== 6. A1 residual: attacker re-locks after every unlock ==")
n0 = len(sent); lock(); print(" relock after unlock -> mails:", len(sent)-n0, "| victim password login:", login(mlro_email, PW).status_code, "(200 = refused until the victim redeems the new mail)")
print("== 7. tenant: org A operator's token cannot unlock org B (token is per operator) ==")
c = connect(db); ta = auth.create_unlock_token(c, A["mlro_id"]); c.close(); q("update operators set failed_login_count=8, locked_until=? where id=?", (datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat(timespec="seconds"), B["mlro_id"])
cl.get(f"/unlock/{ta}"); print(" org A token used; org B MLRO still locked:", q("select locked_until is not null from operators where id=?", B["mlro_id"])[0][0])

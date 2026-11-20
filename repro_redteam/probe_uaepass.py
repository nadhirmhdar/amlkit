"""Red-team 2026-10-12: UAE PASS flows (operator SSO + customer CDD verification), LOCAL ONLY.
UAE PASS's token and userinfo endpoints are STUBBED (no network); the routes, state/cookie logic and DB are real.
Needs fixtures/seed.db from PR #412's make_seed.py."""
import json, os, re, shutil, sqlite3, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); A, B = ids["A"], ids["B"]
tmp = Path(tempfile.mkdtemp()); db = tmp/"s.db"
os.environ.update({"AMLKIT_DB": str(db), "AMLKIT_REGISTRATION_INVITE_CODE": "test-invite", "UAEPASS_CLIENT_ID": "x", "UAEPASS_CLIENT_SECRET": "y", "AMLKIT_APP_BASE_URL": "http://testserver"})
from fastapi.testclient import TestClient
from amlkit import auth, uaepass
from amlkit.api.app import app, limiter
from amlkit.db import connect, _reset_init_cache
from amlkit.uaepass import UaePassProfile
PROFILE = {}
uaepass.exchange_code = lambda config, code, redirect_uri: {"access_token": "stub"}
uaepass.fetch_userinfo = lambda config, tok: PROFILE["p"]
def prof(uuid="U-1", idn="784199012345678", name="Zed Unrelated", email=None, ut="SOP3", nat="IRN"):
    return UaePassProfile(sub=uuid, uuid=uuid, idn=idn, fullname_en=name, fullname_ar=None, firstname_en=name.split()[0], lastname_en=name.split()[-1],
        gender="Male", mobile="971500000000", email=email, nationality_en=nat, nationality_ar=None, user_type=ut, raw={"stub": True})
def reset():
    for s in ("","-wal","-shm"): Path(str(db)+s).unlink(missing_ok=True)
    shutil.copy(ROOT/"fixtures"/"seed.db", db); _reset_init_cache(); limiter.reset()
def q(sql, *a): c = sqlite3.connect(db); r = c.execute(sql, a).fetchall(); c.close(); return r
def session_client(org, who):
    c = connect(db); t = auth.create_session(c, org[f"{who}_id"], org["org_id"], mfa_verified=True); c.close()
    cl = TestClient(app, follow_redirects=False); cl.cookies.set(auth.SESSION_COOKIE, t); cl.get("/"); return cl
def state_from(r): return re.search(r"state=([^&]+)", r.headers["location"]).group(1)
def msg(r): return (r.headers.get("location") or "")[:60]
def flash(cl): return cl.cookies.get("amlkit_flash") or ""

print("== 1. operator SSO callback: state and cookie binding ==")
reset(); cl = TestClient(app, follow_redirects=False)
r = cl.get("/auth/uaepass/callback", params={"code": "c", "state": "forged"}); print(" forged state, no cookie ->", r.status_code, msg(r), "|", re.sub(r"\s+", " ", flash(cl))[:0])
r0 = cl.get("/auth/uaepass/start"); st = state_from(r0); print(" start ->", r0.status_code, "state cookie set:", "amlkit_uaepass_state" in r0.headers.get("set-cookie", ""))
other = TestClient(app, follow_redirects=False); r = other.get("/auth/uaepass/callback", params={"code": "c", "state": st}); print(" victim browser (no state cookie) presents attacker's callback ->", r.status_code, msg(r), "| session cookie issued:", "amlkit_session" in r.headers.get("set-cookie", ""))
PROFILE["p"] = prof(uuid="NEW-UUID", email=None); r = cl.get("/auth/uaepass/callback", params={"code": "c", "state": st}); print(" matching cookie, unlinked identity ->", r.status_code, msg(r), "| session issued:", "amlkit_session" in r.headers.get("set-cookie", ""))
r = cl.get("/auth/uaepass/callback", params={"code": "c", "state": st}); print(" replay of the same state ->", r.status_code, "| session issued:", "amlkit_session" in r.headers.get("set-cookie", ""))
print("== 2. customer state reuse across purpose / customer / org ==")
reset(); b = session_client(B, "mlro"); r = b.get(f"/customers/{B['customer_id']}/uaepass/start"); cst = state_from(r)
op = TestClient(app, follow_redirects=False); op.cookies.set("amlkit_uaepass_state", cst)
PROFILE["p"] = prof(uuid="U-X"); r = op.get("/auth/uaepass/callback", params={"code": "c", "state": cst}); print(" customer state at the operator-SSO callback -> session issued:", "amlkit_session" in r.headers.get("set-cookie", ""))
reset(); b = session_client(B, "mlro"); cst = state_from(b.get(f"/customers/{B['customer_id']}/uaepass/start"))
r = b.get(f"/customers/{B['hit_customer_id']}/uaepass/callback", params={"code": "c", "state": cst}); print(" state for customer", B["customer_id"], "used on customer", B["hit_customer_id"], "->", q("select count(*) from uaepass_verifications")[0][0], "verifications recorded")
reset(); b = session_client(B, "mlro"); cst = state_from(b.get(f"/customers/{B['customer_id']}/uaepass/start")); a = session_client(A, "mlro"); a.cookies.set("amlkit_uaepass_state", cst)
r = a.get(f"/customers/{B['customer_id']}/uaepass/callback", params={"code": "c", "state": cst}); print(" org A session redeems org B's state on B's customer ->", q("select count(*) from uaepass_verifications")[0][0], "verifications recorded")
reset(); b = session_client(B, "mlro"); cst = state_from(b.get(f"/customers/{B['customer_id']}/uaepass/start")); sqlite3.connect(db).execute("update uaepass_states set expires_at=?", ((datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),)).connection.commit()
r = b.get(f"/customers/{B['customer_id']}/uaepass/callback", params={"code": "c", "state": cst}); print(" expired state ->", q("select count(*) from uaepass_verifications")[0][0], "verifications recorded")
print("== 3. customer verification is not bound to the customer's own identity ==")
reset(); b = session_client(B, "mlro")
print(" customers:", q("select id, full_name, nationality, id_number, id_type from customers where org_id=? and id in (?,?)", B["org_id"], B["customer_id"], B["hit_customer_id"]))
PROFILE["p"] = prof(uuid="OPERATOR-OWN-UUID", idn="784199012345678", name="Zed Unrelated", nat="IRN")
for cid in (B["customer_id"], B["hit_customer_id"]):
    cst = state_from(b.get(f"/customers/{cid}/uaepass/start")); r = b.get(f"/customers/{cid}/uaepass/callback", params={"code": "c", "state": cst})
print(" one UAE PASS identity (name 'Zed Unrelated', IRN) verified for BOTH customers -> verifications:", q("select customer_id, uaepass_uuid, fullname_en from uaepass_verifications"))
print(" customer rows after backfill:", q("select id, full_name, nationality, id_number, id_type from customers where id in (?,?)", B["customer_id"], B["hit_customer_id"]))
print("== 4. SSO vs password lockout, deactivation, assurance gate ==")
reset(); future = (datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat(timespec="seconds")
sqlite3.connect(db).execute("update operators set uaepass_uuid='OFF-UUID', failed_login_count=8, locked_until=? where id=?", (future, B["officer_id"])).connection.commit()
cl = TestClient(app, follow_redirects=False); st = state_from(cl.get("/auth/uaepass/start")); PROFILE["p"] = prof(uuid="OFF-UUID")
r = cl.get("/auth/uaepass/callback", params={"code": "c", "state": st}); print(" officer account password-LOCKED (8 failures): SSO login ->", r.status_code, r.headers.get("location"), "| session issued:", "amlkit_session" in r.headers.get("set-cookie", ""))
reset(); sqlite3.connect(db).execute("update operators set uaepass_uuid='OFF-UUID', is_active=0 where id=?", (B["officer_id"],)).connection.commit()
cl = TestClient(app, follow_redirects=False); st = state_from(cl.get("/auth/uaepass/start")); r = cl.get("/auth/uaepass/callback", params={"code": "c", "state": st}); print(" deactivated operator: session issued:", "amlkit_session" in r.headers.get("set-cookie", ""))
for ut in ("SOP1", "SOP2"):
    reset(); cl = TestClient(app, follow_redirects=False); st = state_from(cl.get("/auth/uaepass/start")); PROFILE["p"] = prof(uuid=f"NEW-{ut}", email=B["officer_email"], ut=ut)
    r = cl.get("/auth/uaepass/callback", params={"code": "c", "state": st}); print(f" email-link by userType {ut}: session issued:", "amlkit_session" in r.headers.get("set-cookie", ""), "| uuid linked:", q("select uaepass_uuid from operators where id=?", B["officer_id"])[0][0])
reset(); sqlite3.connect(db).execute("update operators set uaepass_uuid='MLRO-UUID' where id=?", (B["mlro_id"],)).connection.commit()
cl = TestClient(app, follow_redirects=False); st = state_from(cl.get("/auth/uaepass/start")); PROFILE["p"] = prof(uuid="MLRO-UUID")
r = cl.get("/auth/uaepass/callback", params={"code": "c", "state": st}); print(" linked MLRO via SSO ->", r.status_code, r.headers.get("location"), "(MFA lock still applies if redirected to /mfa/*)")

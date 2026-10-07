"""Red-team 2026-10-07: MFA (TOTP) probes: re-enrolment of an enrolled operator from a locked session, TOTP replay,
backup-code reuse, lockout, trusted-device scoping. LOCAL ONLY (needs fixtures/seed.db from PR #412's make_seed.py)."""
import json, os, re, shutil, sqlite3, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); A, B = ids["A"], ids["B"]
tmp = Path(tempfile.mkdtemp()); db = tmp/"s.db"; os.environ["AMLKIT_DB"] = str(db); os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE","test-invite")
import pyotp
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.db import connect, _reset_init_cache
def reset():
    for s in ("","-wal","-shm"): Path(str(db)+s).unlink(missing_ok=True)
    shutil.copy(ROOT/"fixtures"/"seed.db", db); _reset_init_cache(); limiter.reset()
    c = connect(db); secret, _ = auth.mfa_enroll(c, B["mlro_id"]); codes = auth.mfa_confirm(c, B["mlro_id"]); c.close(); return secret, codes
def locked_client(org=B, who="mlro"):
    c = connect(db); t = auth.create_session(c, org[f"{who}_id"], org["org_id"], mfa_verified=False); c.close()
    cl = TestClient(app, follow_redirects=False); cl.cookies.set(auth.SESSION_COOKIE, t); cl.get("/mfa/verify"); return cl, t
def csrf(cl): return cl.cookies.get(auth.CSRF_COOKIE)
def state(t): c = sqlite3.connect(db); r = c.execute("select mfa_verified from sessions where token_hash is not null and mfa_verified is not null order by rowid desc limit 1").fetchone(); c.close(); return r
def verified(t): c = connect(db); v = auth.session_mfa_verified(c, t); c.close(); return v
def secret_now(): return sqlite3.connect(db).execute("select secret, confirmed_at is not null from mfa_secrets where operator_id=?", (B["mlro_id"],)).fetchone()

print("== 1. re-enrolment of an ENROLLED operator from a locked (password-only) session ==")
secret, codes = reset(); cl, t = locked_client()
r = cl.get("/mfa/setup"); print(" GET /mfa/setup ->", r.status_code, r.headers.get("location"), "| secret unchanged:", secret_now()[0] == secret)
r = cl.post("/mfa/setup", data={"csrf_token": csrf(cl), "code": "000000"}); print(" POST /mfa/setup bogus code ->", r.status_code, r.headers.get("location"), "| session verified:", verified(t), "| secret unchanged:", secret_now()[0] == secret)
print("== 2. TOTP replay: same code on two different locked sessions ==")
secret, codes = reset(); code = pyotp.TOTP(secret).now()
cl1, t1 = locked_client(); r1 = cl1.post("/mfa/verify", data={"csrf_token": csrf(cl1), "code": code}); print(" first use  ->", r1.status_code, r1.headers.get("location"), "verified:", verified(t1))
cl2, t2 = locked_client(); r2 = cl2.post("/mfa/verify", data={"csrf_token": csrf(cl2), "code": code}); print(" replay     ->", r2.status_code, r2.headers.get("location"), "verified:", verified(t2))
print("== 3. backup code single-use ==")
secret, codes = reset(); bc = codes[0]
cl1, t1 = locked_client(); cl1.post("/mfa/verify", data={"csrf_token": csrf(cl1), "code": bc}); print(" first use  -> verified:", verified(t1))
cl2, t2 = locked_client(); cl2.post("/mfa/verify", data={"csrf_token": csrf(cl2), "code": bc}); print(" reuse      -> verified:", verified(t2))
print("== 4. lockout ==")
secret, codes = reset(); cl, t = locked_client()
for i in range(5): r = cl.post("/mfa/verify", data={"csrf_token": csrf(cl), "code": "000000"})
print(" after 5 misses ->", r.status_code, r.headers.get("location"))
r = cl.post("/mfa/verify", data={"csrf_token": csrf(cl), "code": pyotp.TOTP(secret).now()}); print(" correct code while locked -> verified:", verified(t))
cl2, t2 = locked_client(); cl2.post("/mfa/verify", data={"csrf_token": csrf(cl2), "code": pyotp.TOTP(secret).now()}); print(" correct code, NEW session, while locked -> verified:", verified(t2), "(lockout is per operator, so a password-holder can lock the real MLRO out)")
print("== 5. trusted-device cookie scoping ==")
secret, codes = reset(); c = connect(db)
tok = auth.create_trusted_device(c, B["mlro_id"])
print(" valid for same operator:", auth.is_trusted_device_valid(c, B["mlro_id"], tok), "| for other operator in same org:", auth.is_trusted_device_valid(c, B["officer_id"], tok), "| for org A MLRO:", auth.is_trusted_device_valid(c, A["mlro_id"], tok))
print(" wrong token:", auth.is_trusted_device_valid(c, B["mlro_id"], tok[:-1] + ("A" if tok[-1] != "A" else "B")), "| None:", auth.is_trusted_device_valid(c, B["mlro_id"], None))
auth.revoke_trusted_devices_for(c, B["mlro_id"]); print(" after revoke_trusted_devices_for:", auth.is_trusted_device_valid(c, B["mlro_id"], tok))

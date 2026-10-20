"""Red-team 2026-10-17: unauthenticated mobile routes without limiters (/auth/verify-email, /auth/resend-verification, /auth/setup):
brute-force headroom, setup-token claim edge cases (duplicate/invalid email, double-claim race). LOCAL ONLY (needs fixtures/ from PR #412 make_seed)."""
import json, os, shutil, sqlite3, sys, tempfile, threading
from hashlib import sha256
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); B = ids["B"]
db = Path(tempfile.mkdtemp())/"s.db"; os.environ["AMLKIT_DB"] = str(db); shutil.copy(ROOT/"fixtures"/"seed.db", db)
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit.api.app import app, limiter
from amlkit.db import _reset_init_cache
_reset_init_cache(); limiter.reset()
cl = TestClient(app, raise_server_exceptions=False)
def q(sql, *a):
    c = sqlite3.connect(db); r = c.execute(sql, a).fetchall(); c.commit(); c.close(); return r
def mk_token(raw):
    exp = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat(timespec="seconds")
    q("insert into setup_tokens (org_id, token_hash, created_at, expires_at) values (?,?,?,?)", B["org_id"], sha256(raw.encode()).hexdigest(), exp, exp)
print("== 1. limiter headroom on unauthenticated mobile routes ==")
for path, body in [("/api/v1/auth/verify-email", {"token": "x"}), ("/api/v1/auth/resend-verification", {"email": "nobody@x.ae"})]:
    codes = {cl.post(path, json=body).status_code for _ in range(120)}; print(f" 120 x {path} -> {sorted(codes)}")
print(" 120 x GET /auth/setup bad token ->", sorted({cl.get("/api/v1/auth/setup", params={"token": "x"}).status_code for _ in range(120)}))
print("== 2. setup claim edge cases ==")
existing = q("select email from operators where org_id=?", B["org_id"])[0][0]
mk_token("tok-dup"); r = cl.post("/api/v1/auth/setup", json={"token": "tok-dup", "name": "X", "email": existing, "password": "Str0ng!Passw0rd"}); print(" existing email ->", r.status_code, r.text[:90], "| token still unused:", q("select used_at is null from setup_tokens where token_hash=?", sha256(b"tok-dup").hexdigest())[0][0])
mk_token("tok-bad"); r = cl.post("/api/v1/auth/setup", json={"token": "tok-bad", "name": "X", "email": "not-an-email", "password": "Str0ng!Passw0rd"}); print(" invalid email string ->", r.status_code, "| operator created:", bool(q("select 1 from operators where email='not-an-email'")))
mk_token("tok-weak"); r = cl.post("/api/v1/auth/setup", json={"token": "tok-weak", "name": "  ", "email": "weak@x.ae", "password": "alllowercase12"}); print(" weak pw + blank name ->", r.status_code, "| created:", bool(q("select 1 from operators where email='weak@x.ae'")))
print("== 3. double-claim race on one setup token (20 threads) ==")
mk_token("tok-race"); res = []
def go(i): res.append(TestClient(app, raise_server_exceptions=False).post("/api/v1/auth/setup", json={"token": "tok-race", "name": f"R{i}", "email": f"race{i}@x.ae", "password": "Str0ng!Passw0rd"}).status_code)
th = [threading.Thread(target=go, args=(i,)) for i in range(20)]; [t.start() for t in th]; [t.join() for t in th]
print(" status codes:", sorted(res), "| operators created from one token:", q("select count(*) from operators where email like 'race%@x.ae'")[0][0])

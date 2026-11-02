"""Red-team 2026-10-19: cost of authenticated POST /api/v1/screen (no limiter, no name-length cap) -- latency vs name length, burst of requests,
and rows written. LOCAL ONLY (needs fixtures/ from PR #412 make_seed). Seed list is tiny, so real latency on a full sanctions list is higher."""
import json, os, shutil, sqlite3, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); B = ids["B"]
db = Path(tempfile.mkdtemp())/"s.db"; os.environ["AMLKIT_DB"] = str(db); shutil.copy(ROOT/"fixtures"/"seed.db", db)
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.db import connect, _reset_init_cache
_reset_init_cache(); limiter.reset()
c = connect(db); t = auth.create_session(c, B["mlro_id"], B["org_id"], mfa_verified=True); c.close()
cl = TestClient(app, raise_server_exceptions=False); H = {"Authorization": f"Bearer {t}"}
n_ent = sqlite3.connect(db).execute("select count(*) from entities").fetchone()[0] if sqlite3.connect(db).execute("select name from sqlite_master where name='entities'").fetchone() else "?"
print("listed entities in seed:", n_ent)
def scr(name): t0 = time.time(); r = cl.post("/api/v1/screen", json={"name": name}, headers=H); return r.status_code, round(time.time()-t0, 2), len(r.content)
print("== 1. latency vs name length ==")
for label, nm in [("3 tokens", "Mohammed Al Testlisted"), ("200 tokens", " ".join(["Mohammed"]*200)), ("2,000 tokens", " ".join(["Mohammed"]*2000)), ("10,000 tokens", " ".join(["Al"]*10000)), ("one 500k-char token", "A"*500_000)]:
    print(f" {label:22s} -> status/secs/bytes {scr(nm)}")
print("== 2. burst of 100 screenings (no limiter) ==")
t0 = time.time(); codes = {scr("Mohammed Al Testlisted")[0] for _ in range(100)}; print(f" codes {codes} in {time.time()-t0:.1f}s")
print(" screenings rows:", sqlite3.connect(db).execute("select count(*) from screenings").fetchone()[0] if sqlite3.connect(db).execute("select name from sqlite_master where name='screenings'").fetchone() else "?")

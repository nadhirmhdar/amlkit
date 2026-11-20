"""Red-team 2026-11-12: from the static SQL triage -- the web route refuses to deactivate the last active MLRO, the mobile route
(POST /api/v1/admin/operators/{id}/deactivate) has no such check. Can an org be left with no active MLRO? LOCAL ONLY (needs fixtures/ from PR #412 make_seed)."""
import json, os, shutil, sqlite3, sys, tempfile
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
q = lambda s, *a: sqlite3.connect(db).execute(s, a).fetchall()
print("active MLROs in org B:", q("select id, is_active from operators where org_id=? and role='mlro'", B["org_id"]))
c = connect(db); tok = auth.create_session(c, B["mlro_id"], B["org_id"], mfa_verified=True); c.close()
cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False); H = {"Authorization": f"Bearer {tok}"}; cl.cookies.set(auth.SESSION_COOKIE, tok); cl.get("/dashboard"); csrf = cl.cookies.get(auth.CSRF_COOKIE)
r = cl.post(f"/admin/operators/{B['mlro_id']}/deactivate", data={"csrf_token": csrf}); print("web   deactivate the last MLRO (self) ->", r.status_code, r.headers.get("location"), "| still active:", q("select is_active from operators where id=?", B["mlro_id"]))
r = cl.post(f"/api/v1/admin/operators/{B['mlro_id']}/deactivate", headers=H); print("mobile deactivate the last MLRO (self) ->", r.status_code, r.text[:80], "| still active:", q("select is_active from operators where id=?", B["mlro_id"]))
print("active MLROs now:", q("select count(*) from operators where org_id=? and role='mlro' and is_active=1", B["org_id"])[0][0], "| sessions of that MLRO still valid:", cl.get("/api/v1/auth/me", headers=H).status_code)

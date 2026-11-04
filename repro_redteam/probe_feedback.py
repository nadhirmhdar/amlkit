"""Red-team 2026-10-16: authenticated POST /feedback (no length cap / rate limit?) and stored-markup rendering in /admin/feedback
and org name in the page chrome. LOCAL ONLY (needs fixtures/seed.db from PR #412's make_seed.py)."""
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
c = connect(db); t = auth.create_session(c, B["mlro_id"], B["org_id"], mfa_verified=True); c.execute("update organizations set name=? where id=?", ("<img src=x onerror=alert(1)>Firm", B["org_id"])); c.commit(); c.close()
cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False); cl.cookies.set(auth.SESSION_COOKIE, t); cl.get("/dashboard"); tok = cl.cookies.get(auth.CSRF_COOKIE)
def fb(**o): d = {"page": "/x", "message": "m", "csrf_token": tok}; d.update(o); return cl.post("/feedback", data=d)
n = lambda: sqlite3.connect(db).execute("select count(*), coalesce(max(length(message)),0) from feedback").fetchone()
print("== 1. size / rate ==")
r = fb(message="A"*900_000, page="P"*50_000); print(" 900KB message + 50KB page ->", r.status_code, n())
t0 = time.time(); codes = [fb(message=f"spam {i}").status_code for i in range(300)]; print(f" 300 rapid posts -> {set(codes)} in {time.time()-t0:.1f}s; rows/maxlen:", n())
print(" audit rows feedback.submit:", sqlite3.connect(db).execute("select count(*) from audit_log where action='feedback.submit'").fetchone()[0])
print("== 2. stored markup rendering ==")
fb(message="<script>alert(1)</script>", page="<b>pg</b>")
for path in ["/admin/feedback", "/dashboard"]:
    h = cl.get(path).text; print(f" {path}: status ok={len(h)>0} raw <script>alert in html: {'<script>alert(1)' in h} | raw <img src=x onerror in html: {'<img src=x onerror' in h} | raw <b>pg: {'<b>pg</b>' in h}")
print("== 3. CSRF / unauth ==")
print(" no csrf ->", fb(csrf_token="").status_code); print(" unauth ->", TestClient(app).post("/feedback", data={"page":"x","message":"m","csrf_token":""}).status_code)

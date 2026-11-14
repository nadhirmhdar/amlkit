"""Red-team 2026-11-13: four-eyes parity across the web and mobile alert routes. An officer who proposes a dismissal must not be able to confirm it themselves
(web or mobile), a different operator can; single-operator mode off. Also: confirm on an alert that was never proposed, double confirm, agree=false override.
LOCAL ONLY (needs fixtures/ from PR #412 make_seed)."""
import json, os, shutil, sqlite3, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); B = ids["B"]
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.db import connect, _reset_init_cache
NARR = "Reviewed the match against the listing: different date of birth and nationality, documented in the file."
def fresh():
    db = Path(tempfile.mkdtemp())/"s.db"; os.environ["AMLKIT_DB"] = str(db); shutil.copy(ROOT/"fixtures"/"seed.db", db); _reset_init_cache(); limiter.reset(); return db
def sess(db, op):
    c = connect(db); t = auth.create_session(c, op, B["org_id"], mfa_verified=True); c.close(); return t
def state(db): return sqlite3.connect(db).execute("select status from alerts where id=?", (B["alert_id"],)).fetchone()[0]
def run(label, via_confirm):
    db = fresh(); cl = TestClient(app, raise_server_exceptions=False); to, tm = sess(db, B["officer_id"]), sess(db, B["mlro_id"]); H = lambda t: {"Authorization": f"Bearer {t}"}
    a = B["alert_id"]
    r = cl.post(f"/api/v1/alerts/{a}/disposition", headers=H(to), json={"status": "false_positive", "reason_code": "different_dob", "narrative": NARR, "note": NARR}); print(f"[{label}] officer proposes ->", r.status_code, "alert:", state(db))
    r = via_confirm(cl, a, to, H, "officer(self)"); print(f"[{label}] SAME officer confirms ->", r, "alert:", state(db), "(pending_review = refused)")
    r = via_confirm(cl, a, tm, H, "mlro"); print(f"[{label}] DIFFERENT operator (MLRO) confirms ->", r, "alert:", state(db))
    r = via_confirm(cl, a, tm, H, "mlro-again"); print(f"[{label}] confirm again after it is closed ->", r, "alert:", state(db))
def mobile_confirm(cl, a, t, H, who): r = cl.post(f"/api/v1/alerts/{a}/confirm", headers=H(t), json={"agree": True, "narrative": NARR}); return r.status_code, r.text[:70]
def web_confirm(cl, a, t, H, who):
    cl.cookies.clear(); cl.cookies.set(auth.SESSION_COOKIE, t); cl.get("/dashboard")
    r = cl.post(f"/alerts/{a}/confirm", data={"agree": "yes", "narrative": NARR, "csrf_token": cl.cookies.get(auth.CSRF_COOKIE)}); return r.status_code, r.headers.get("location", "")[:40]
run("mobile", mobile_confirm); run("web", web_confirm)
db = fresh(); cl = TestClient(app, raise_server_exceptions=False); tm = sess(db, B["mlro_id"])
r = cl.post(f"/api/v1/alerts/{B['alert_id']}/confirm", headers={"Authorization": f"Bearer {tm}"}, json={"agree": True, "narrative": NARR}); print("[mobile] confirm on an alert nobody proposed ->", r.status_code, r.text[:80], "alert:", state(db))

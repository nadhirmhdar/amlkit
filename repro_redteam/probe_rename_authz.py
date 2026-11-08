"""Red-team 2026-10-04: authz/CSRF/input probes for POST /admin/operators/{id}/rename,
plus the four-eyes self-rename bypass. LOCAL ONLY: copies fixtures/seed.db (built by
PR #412's repro/make_seed.py) to a scratch dir. Prints one line per probe.
Run from a checkout that has fixtures/seed.db:  python repro_redteam/probe_rename_authz.py"""
import json, os, shutil, sqlite3, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); A, B = ids["A"], ids["B"]
tmp = Path(tempfile.mkdtemp()); db = tmp/"s.db"; os.environ["AMLKIT_DB"] = str(db)
os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE", "test-invite")
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.db import connect, _reset_init_cache

def fresh(org, who):
    for s in ("","-wal","-shm"): Path(str(db)+s).unlink(missing_ok=True)
    shutil.copy(ROOT/"fixtures"/"seed.db", db); _reset_init_cache(); limiter.reset()
    c = connect(db); raw = auth.create_session(c, org[f"{who}_id"], org["org_id"], mfa_verified=True); c.close()
    cl = TestClient(app, follow_redirects=False); cl.cookies.set(auth.SESSION_COOKIE, raw); cl.get("/"); return cl
def q(sql, *a):
    c = sqlite3.connect(db); r = c.execute(sql, a).fetchall(); c.close(); return r
def rename(cl, op_id, name, csrf="auto"):
    t = cl.cookies.get(auth.CSRF_COOKIE) if csrf == "auto" else csrf
    return cl.post(f"/admin/operators/{op_id}/rename", data={"name": name, "csrf_token": t or ""})
def show(label, r, extra=""): print(f"{label:62s} -> {r.status_code} {r.headers.get('location','') or r.text[:70]!r} {extra}")

cl = fresh(B,"officer");  show("officer (non-MLRO) renames self", rename(cl, B["officer_id"], "x1"), q("select name from operators where id=?",B["officer_id"]))
cl = fresh(B,"mlro");     show("MLRO, no CSRF token", rename(cl, B["officer_id"], "x2", csrf=""), q("select name from operators where id=?",B["officer_id"]))
cl = fresh(B,"mlro");     show("MLRO, wrong CSRF token", rename(cl, B["officer_id"], "x3", csrf="bad"), q("select name from operators where id=?",B["officer_id"]))
cl = fresh(B,"mlro");     show("MLRO(B) renames org A officer", rename(cl, A["officer_id"], "pwned"), q("select name from operators where id=?",A["officer_id"]))
cl = fresh(B,"mlro");     show("MLRO(B) renames org A MLRO", rename(cl, A["mlro_id"], "pwned"), q("select name from operators where id=?",A["mlro_id"]))
cl = fresh(B,"mlro");     show("unauthenticated", TestClient(app, follow_redirects=False).post(f"/admin/operators/{B['officer_id']}/rename", data={"name":"x"}))
print("--- input handling (as MLRO B, target B officer) ---")
off = lambda: q("select name from operators where id=?",B["officer_id"])[0][0]
for label, nm in [("zero-width space appended to existing name", B["marker"]+"-mlro​"),
                  ("Cyrillic homoglyph copy of MLRO name", "".join({"A":"А","L":"Л"}.get(ch,ch) for ch in B["marker"])+"-mlro".replace("o","о")),
                  ("case variant of MLRO name", (B["marker"]+"-mlro").lower()),
                  ("reserved actor 'system'", "system"),
                  ("html/script", "<script>alert(1)</script>"),
                  ("newline/control chars", "a\r\nb\x00c"),
                  ("RLO bidi override", "x‮txt.exe"),
                  ("65536 chars", "a"*65536)]:
    cl = fresh(B,"mlro"); r = rename(cl, B["officer_id"], nm); show(label, r, "stored="+repr(off()[:50]))
cl = fresh(B,"mlro"); r = cl.get("/admin"); 
cl = fresh(B,"mlro"); rename(cl, B["officer_id"], "<script>alert(1)</script>"); r = cl.get("/admin")
print("raw '<script>alert(1)' in /admin HTML:", "<script>alert(1)" in r.text)
print("--- four-eyes self-rename bypass ---")
# officer B proposed pending_alert (seed). Officer cannot confirm own proposal; MLRO renames the officer, officer confirms.
cl = fresh(B,"officer"); t = cl.cookies.get(auth.CSRF_COOKIE)
r = cl.post(f"/alerts/{B['pending_alert_id']}/confirm", data={"csrf_token": t, "agree":"yes","narrative":"n"}); 
print("officer confirms own proposal, before rename:", r.status_code, r.headers.get("location"), q("select status from alerts where id=?",B["pending_alert_id"]))
c = connect(db); c.execute("UPDATE operators SET name='Someone Else' WHERE id=?",(B["officer_id"],)); c.commit(); c.close()  # == what the MLRO rename route does (verified above)
cl2 = TestClient(app, follow_redirects=False); 
c = connect(db); raw = auth.create_session(c, B["officer_id"], B["org_id"], mfa_verified=True); c.close(); cl2.cookies.set(auth.SESSION_COOKIE, raw); cl2.get("/"); t = cl2.cookies.get(auth.CSRF_COOKIE)
r = cl2.post(f"/alerts/{B['pending_alert_id']}/confirm", data={"csrf_token": t, "agree":"yes","narrative":"n"})
print("same officer confirms after being renamed:", r.status_code, r.headers.get("location"), q("select status from alerts where id=?",B["pending_alert_id"]))

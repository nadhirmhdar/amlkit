"""Red-team 2026-10-04: (1) four-eyes bypass via the real rename route, (2) CSRF sweep of every
POST route with a valid MLRO session but NO/BAD token, (3) state-changing GETs, (4) session lifecycle.
LOCAL ONLY (scratch copy of fixtures/seed.db)."""
import hashlib, json, os, re, shutil, sqlite3, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); B = ids["B"]
tmp = Path(tempfile.mkdtemp()); db = tmp/"s.db"; os.environ["AMLKIT_DB"] = str(db)
os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE", "test-invite")
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.db import connect, _reset_init_cache
def reset():
    for s in ("","-wal","-shm"): Path(str(db)+s).unlink(missing_ok=True)
    shutil.copy(ROOT/"fixtures"/"seed.db", db); _reset_init_cache(); limiter.reset()
def login(who):
    c = connect(db); raw = auth.create_session(c, B[f"{who}_id"], B["org_id"], mfa_verified=True); c.close()
    cl = TestClient(app, follow_redirects=False); cl.cookies.set(auth.SESSION_COOKIE, raw); cl.get("/"); return cl, raw
def digest():
    c = sqlite3.connect(db); h = hashlib.sha1()
    for (t,) in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' and name not in ('sessions','auth_log') order by 1"):
        h.update(repr(c.execute(f"select * from {t}").fetchall()).encode())
    c.close(); return h.hexdigest()
def q(sql,*a):
    c = sqlite3.connect(db); r = c.execute(sql,a).fetchall(); c.close(); return r

print("== 1. four-eyes bypass through the real rename route ==")
reset(); off,_ = login("officer"); t = off.cookies.get(auth.CSRF_COOKIE)
r = off.post(f"/alerts/{B['pending_alert_id']}/confirm", data={"csrf_token": t,"agree":"yes","narrative":"n"})
print(" officer confirms own proposal:", r.status_code, q("select status from alerts where id=?",B["pending_alert_id"]))
m,_ = login("mlro"); t = m.cookies.get(auth.CSRF_COOKIE)
r = m.post(f"/admin/operators/{B['officer_id']}/rename", data={"name":"Renamed Officer","csrf_token":t}); print(" MLRO renames the proposer:", r.status_code, r.headers.get("location"))
off2,_ = login("officer"); t = off2.cookies.get(auth.CSRF_COOKIE)
r = off2.post(f"/alerts/{B['pending_alert_id']}/confirm", data={"csrf_token": t,"agree":"yes","narrative":"n"})
print(" proposer now confirms own proposal:", r.status_code, "alert status =", q("select status from alerts where id=?",B["pending_alert_id"]))
print(" review rows:", q("select operator, action from alert_reviews where alert_id=?", B["pending_alert_id"]) if q("select name from sqlite_master where name='alert_reviews'") else "n/a")

print("== 2. CSRF sweep: POST with valid MLRO session, no token and bad token ==")
SKIP = ("/logout","/system","/login","/register","/forgot","/apply","/verify","/mfa","/setup","/reset","/auth","/blog","/feedback-public","/console")
routes = sorted({(r.path) for r in app.routes if getattr(r,"path",None) and "POST" in (getattr(r,"methods",None) or []) and not r.path.startswith("/api/v1")})
bad = []
for p in routes:
    if any(p.startswith(s) for s in SKIP): continue
    url = re.sub(r"\{[^}]+\}", "1", p)
    for tok in ("", "bad"):
        reset(); cl,_ = login("mlro"); before = digest()
        try: r = cl.post(url, data={"csrf_token": tok, "name":"x","body":"x","amount":"1","direction":"in","method":"cash","email":"z@x.ae","password":"a-long-password-1"})
        except Exception as e: print(" EXC", p, repr(e)[:80]); continue
        if digest() != before: bad.append((p, tok, r.status_code))
print(f" POST routes tested: {len([p for p in routes if not any(p.startswith(s) for s in SKIP)])}; state changed without valid CSRF: {bad or 'none'}")
print(" skipped prefixes:", SKIP)

print("== 3. GET routes that change state (MLRO session) ==")
gets = sorted({r.path for r in app.routes if getattr(r,"path",None) and "GET" in (getattr(r,"methods",None) or []) and not r.path.startswith(("/static","/docs","/openapi","/redoc","/blog","/system","/logout","/console"))})
chg = []
for p in gets:
    url = re.sub(r"\{[^}]+\}", "1", p)
    if "refresh" in p: continue   # would hit the network (sanctions refresh); analysed statically below
    reset(); cl,raw = login("mlro"); before = digest()
    hdr = {"Authorization": f"Bearer {raw}"}
    try: r = cl.get(url, headers=hdr)
    except Exception: continue
    if digest() != before: chg.append((p, r.status_code))
print(" GET routes tested:", len(gets), "| changed non-session state:", chg or "none")
os.system(f"grep -n 'refresh-stream' {ROOT}/amlkit/api/app.py | head -3")

print("== 4. session lifecycle ==")
reset(); cl, raw = login("mlro"); t = cl.cookies.get(auth.CSRF_COOKIE)
r = cl.post("/logout", data={"csrf_token": t}); print(" logout:", r.status_code)
old = TestClient(app, follow_redirects=False); old.cookies.set(auth.SESSION_COOKIE, raw)
print(" old cookie after logout ->", old.get("/admin").status_code, "(303 = rejected)")
reset(); cl, raw = login("mlro"); t = cl.cookies.get(auth.CSRF_COOKIE)

try: cl.post(f"/admin/operators/{B['officer_id']}/reset-password", data={"new_password":"weak-password-9","csrf_token":t}); print(" reset-password with a weak password: handled")
except Exception as e: print(" reset-password with a weak password -> UNHANDLED", type(e).__name__, "(HTTP 500)")
cl.post(f"/admin/operators/{B['mlro_id']}/reset-password", data={"new_password":"Brand-New-Password-9!","csrf_token":t})
print(" own session after self password-reset ->", cl.get("/admin").status_code)
reset()
c = TestClient(app, follow_redirects=False); c.get("/login"); t = c.cookies.get(auth.CSRF_COOKIE)
r = c.post("/login", data={"email": B["mlro_email"], "password":"a-strong-password-1","csrf_token": t})
for h in r.headers.get_list("set-cookie"): print("  Set-Cookie:", re.sub(r"=[^;]{12,}", "=<v>", h))
pre = set(c.cookies.keys())
reset(); fx = TestClient(app, follow_redirects=False); fx.cookies.set(auth.SESSION_COOKIE, "attacker-chosen-value"); fx.get("/login"); t = fx.cookies.get(auth.CSRF_COOKIE)
r = fx.post("/login", data={"email": B["mlro_email"], "password":"a-strong-password-1","csrf_token": t})
sc = [h for h in r.headers.get_list("set-cookie") if h.startswith(auth.SESSION_COOKIE+"=")]
print(" session fixation: login issued a fresh session cookie != attacker-chosen value:", bool(sc) and "attacker-chosen-value" not in sc[0], "| status", r.status_code)

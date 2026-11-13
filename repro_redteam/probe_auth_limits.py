"""Red-team 2026-10-11: login rate limits, X-Forwarded-For handling, account-lockout DoS, cookie Secure flags.
LOCAL ONLY (needs fixtures/seed.db). The limiter is ENABLED here (unlike most other probes)."""
import json, os, re, shutil, sqlite3, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
B = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text())["B"]
tmp = Path(tempfile.mkdtemp()); db = tmp/"s.db"; os.environ["AMLKIT_DB"] = str(db); os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE","test-invite")
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.db import _reset_init_cache
PW = "a-strong-password-1"
def reset():
    for s in ("","-wal","-shm"): Path(str(db)+s).unlink(missing_ok=True)
    shutil.copy(ROOT/"fixtures"/"seed.db", db); _reset_init_cache(); limiter.reset()
def attempt(cl, email, pw, xff=None):
    h = {"X-Forwarded-For": xff} if xff else {}
    t = cl.cookies.get(auth.CSRF_COOKIE) or (cl.get("/login") and cl.cookies.get(auth.CSRF_COOKIE))
    return cl.post("/login", data={"email": email, "password": pw, "csrf_token": t}, headers=h)
def locked(email): return sqlite3.connect(db).execute("select failed_login_count, locked_until from operators where lower(email)=?", (email,)).fetchone()
E = B["mlro_email"]
print("== 1. IP ceiling, no proxy trust (AMLKIT_BEHIND_PROXY unset), rotating X-Forwarded-For ==")
os.environ.pop("AMLKIT_BEHIND_PROXY", None); reset(); cl = TestClient(app, follow_redirects=False); codes = []
for i in range(14): codes.append(attempt(cl, f"nobody{i}@example.com", "x", xff=f"198.51.100.{i}").status_code)
print(" statuses:", codes, "| first 429 at attempt:", next((i+1 for i, c in enumerate(codes) if c == 429), None))
print("== 2. same, AMLKIT_BEHIND_PROXY=1, proxy appends real client at the right (spoofed hop on the left) ==")
os.environ["AMLKIT_BEHIND_PROXY"] = "1"; reset(); cl = TestClient(app, follow_redirects=False); codes = []
for i in range(14): codes.append(attempt(cl, f"nobody{i}@example.com", "x", xff=f"6.6.6.{i}, 203.0.113.9").status_code)
print(" statuses:", codes, "| first 429 at attempt:", next((i+1 for i, c in enumerate(codes) if c == 429), None))
print("== 3. BEHIND_PROXY=1 but no trusted proxy hop (direct hit with a single spoofed XFF value) ==")
reset(); cl = TestClient(app, follow_redirects=False); codes = []
for i in range(14): codes.append(attempt(cl, f"nobody{i}@example.com", "x", xff=f"6.6.6.{i}").status_code)
print(" statuses:", codes, "| 429 seen:", 429 in codes, "(a bypass here needs a path to the app that skips the Google front end)")
print("== 4. account-lockout DoS against the MLRO (limiter budget 3/min per ip+email, so time is simulated with limiter.reset()) ==")
os.environ.pop("AMLKIT_BEHIND_PROXY", None); reset(); cl = TestClient(app, follow_redirects=False); minutes = 0
while (locked(E)[1] is None) and minutes < 10:
    for _ in range(3): attempt(cl, E, "wrong-password")
    limiter.reset(); minutes += 1
print(f" attacker with NO credentials: 3 wrong guesses per simulated minute; after {minutes} minutes ->", locked(E))
limiter.reset(); r = attempt(cl, E, PW); print(" real MLRO signs in with the CORRECT password ->", r.status_code, r.headers.get("location"), "(a 200 re-render of the login form = refused; a valid login redirects 303 -- control: fresh DB, same password, gives 303)")
print("== 5. Set-Cookie flags on a successful login with AMLKIT_BEHIND_PROXY=1 ==")
os.environ["AMLKIT_BEHIND_PROXY"] = "1"; reset(); cl = TestClient(app, base_url="https://testserver", follow_redirects=False)   # https so Secure cookies are sent back
r = attempt(cl, B["officer_email"], PW)
print(" login status:", r.status_code, r.headers.get("location"))
for h in r.headers.get_list("set-cookie"): print("  ", re.sub(r"=[^;]{14,}", "=<v>", h))

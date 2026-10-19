"""Lead repro, 2026-10-19. Exits 0 when every defect below reproduces.

Owed by the 10-18 lead report:
  AM  - L-73 adverse-media path: ruling one adverse-media finding
        'not_relevant' on a customer overdue for periodic review runs
        reassess_adverse_media -> save_risk, which writes a fresh next_review,
        so the customer drops off due_for_review with no review done.
  L75 - an MLRO session still locked behind MFA that opens /admin is sent to
        "/" (app.py admin_view: current_session() is not None, require_session()
        raised), then "/" sends it to /login, and /login to /mfa/verify:
        three hops, no bypass.

New findings from today's role reports:
  S3m - mobile POST /api/v1/screen accepts a 50,000-char name and 30
        back-to-back requests all return 200 (no length cap, no limiter).
  S3w - web POST /screen accepts the same 50,000-char name (has a 10/minute
        limiter, but no length cap).
  PW1 - after a successful /account/password change the flash says "All other
        sessions have been signed out." yet the session that made the change
        is also revoked (next request goes to /login).
  PW2 - /account/password accepts the CURRENT (compliant) password as the new
        one: no "must differ" check.
  SS1 - a 4th create_session() for one operator silently revokes the oldest
        (MAX_CONCURRENT_SESSIONS default 3); informational, partly by design.

Local scratch DB only, no network. Run from the repo root:
  PYTHONPATH=.:tests python repro_lead/checks_2026_10_19.py
"""
import json, os, re, sqlite3, sys, tempfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
tmp = tempfile.mkdtemp()
os.environ["AMLKIT_DB"] = os.path.join(tmp, "web.db")
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = "test-invite"
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)
import logging; logging.disable(logging.CRITICAL)

from amlkit import auth, db as dbm
from amlkit.db import utcnow
from amlkit.cases.manager import due_for_review, disposition_adverse_media_finding

ok, need = 0, 0

# ---- AM: adverse-media disposition resets the review clock ----------------
w = dbm.connect(os.path.join(tmp, "am.db")); w.row_factory = sqlite3.Row
now = utcnow()
with w:
    org_id = w.execute("INSERT INTO organizations (name, slug, created_at) VALUES ('Org AM','org-am',?)", (now,)).lastrowid
    cid = w.execute(
        "INSERT INTO customers (org_id, reference, customer_type, full_name, canonical_key,"
        " onboarded_at, created_at, updated_at) VALUES (?, 'AM-1', 'natural',"
        " 'Overdue Media Customer', 'overdue media customer', ?, ?, ?)", (org_id, now, now, now)).lastrowid
    w.execute(
        "INSERT INTO risk_assessments (org_id, customer_id, score, rating, factors, ruleset_version,"
        " requires_edd, assessed_at, next_review) VALUES (?, ?, 10, 'low', ?, 'test', 0,"
        " '2025-01-01T00:00:00+00:00', '2026-01-01')", (org_id, cid, json.dumps({})))
    sid = w.execute(
        "INSERT INTO adverse_media_screenings (org_id, customer_id, query_name, trigger, window_months,"
        " status, findings, severity, run_at) VALUES (?, ?, 'Overdue Media Customer', 'adhoc', 24, 'ok', 1, 'low', ?)",
        (org_id, cid, now)).lastrowid
    fid = w.execute(
        "INSERT INTO adverse_media_findings (org_id, screening_id, customer_id, url, title, severity,"
        " matched_terms, created_at) VALUES (?, ?, ?, 'https://example.test/a', 'Unrelated namesake', 'low', '[]', ?)",
        (org_id, sid, cid, now)).lastrowid
before = cid in [r["id"] for r in due_for_review(w, org_id)]
disposition_adverse_media_finding(w, fid, org_id, status="not_relevant", note="different person", actor="lead")
w.commit()
after = cid in [r["id"] for r in due_for_review(w, org_id)]
nr = w.execute("SELECT next_review FROM risk_assessments WHERE customer_id=? ORDER BY id DESC LIMIT 1", (cid,)).fetchone()[0]
am = before and not after and nr > datetime.now(timezone.utc).date().isoformat()
print(f"AM  overdue before={before}; after one 'not_relevant' media ruling: overdue={after}, next_review={nr} -> reproduces={am}")
ok += am; need += 1

# ---- SS1: session cap -----------------------------------------------------
with w:
    op = w.execute("INSERT INTO operators (org_id, name, email, role, password_hash, created_at)"
                   " VALUES (?, 'Sam', 's@t.test', 'analyst', 'x', ?)", (org_id, now)).lastrowid
toks = [auth.create_session(w, op, org_id) for _ in range(4)]
w.commit()
alive = [auth.resolve_session(w, t) is not None for t in toks]
print(f"SS1 4 sessions for one operator, alive={alive} (oldest silently revoked; informational)")

# ---- web/mobile checks ------------------------------------------------------
from test_api import _seed_sanctions_data, _register, _csrf
_seed_sanctions_data(os.environ["AMLKIT_DB"])
from fastapi.testclient import TestClient
from amlkit.api.app import app, limiter
dbm._reset_init_cache(); limiter.reset()

cl = TestClient(app, raise_server_exceptions=False)
_register(cl, "Lead Firm", "Lena", "lena@lead.test")      # MLRO, MFA enrolled + verified
c = sqlite3.connect(os.environ["AMLKIT_DB"]); c.row_factory = sqlite3.Row
mlro = c.execute("SELECT id, org_id FROM operators WHERE email='lena@lead.test'").fetchone()

# S3w: web form, 50k name
big = "A" * 50_000
r = cl.post("/screen", data={"name": big, "csrf_token": _csrf(cl)})
rows_w = c.execute("SELECT length(query_name) FROM screenings ORDER BY id DESC LIMIT 1").fetchone()
s3w = r.status_code == 200 and rows_w is not None and rows_w[0] >= 50_000
print(f"S3w web /screen 50,000-char name -> status={r.status_code}, stored length={rows_w[0] if rows_w else None} -> reproduces={s3w}")
ok += s3w; need += 1

# S3m: mobile bearer (MFA-verified session, as the red-team probe did)
k = dbm.connect(os.environ["AMLKIT_DB"]); bt = auth.create_session(k, mlro["id"], mlro["org_id"], mfa_verified=True); k.close()
H = {"Authorization": f"Bearer {bt}"}
r1 = cl.post("/api/v1/screen", json={"name": big}, headers=H)
codes = [cl.post("/api/v1/screen", json={"name": "Probe Person"}, headers=H).status_code for _ in range(30)]
s3m = r1.status_code == 200 and set(codes) == {200}
print(f"S3m mobile /api/v1/screen 50,000-char name -> {r1.status_code}; 30 rapid requests -> {sorted(set(codes))} -> reproduces={s3m}")
ok += s3m; need += 1

# L75: fresh login of the enrolled MLRO -> locked session -> /admin
cl2 = TestClient(app, raise_server_exceptions=False)
cl2.get("/login")
cl2.post("/login", data={"email": "lena@lead.test", "password": "a-strong-password-1", "csrf_token": _csrf(cl2)})
ra = cl2.get("/admin", follow_redirects=False)
loc = ra.headers.get("location")
nxt = cl2.get(loc or "/", follow_redirects=False).headers.get("location") if loc else None
l75 = ra.status_code == 303 and loc == "/"
print(f"L75 MFA-locked MLRO GET /admin -> {ra.status_code} location={loc!r}; '/' then -> {nxt!r} (then /login -> /mfa/verify) -> reproduces={l75}")
ok += l75; need += 1

# PW1 on the verified web session (cl). The test password lacks an uppercase
# letter, so PW1 also moves the account to a compliant password for PW2.
from conftest import settle_mfa
import base64
cur = "a-strong-password-1"
new = "Another-Strong-Pass-2"
cl.get("/account/password")
r = cl.post("/account/password", data={"current_password": cur, "new_password": new,
                                       "confirm_password": new, "csrf_token": _csrf(cl)}, follow_redirects=False)
says_other = False
for part in re.findall(r"amlkit_flash=\"?([A-Za-z0-9+/=]+)", r.headers.get("set-cookie", "")):
    try:
        says_other = says_other or "All other sessions" in base64.b64decode(part).decode()
    except Exception:
        pass
after_pw = cl.get("/", follow_redirects=False)
dead = after_pw.status_code == 303 and after_pw.headers.get("location") == "/login"
pw1 = r.status_code == 303 and says_other and dead
print(f"PW1 change -> {r.status_code}, flash says 'All other sessions'={says_other}; next GET / -> "
      f"{after_pw.status_code} {after_pw.headers.get('location')!r} -> reproduces={pw1}")
ok += pw1; need += 1

# PW2: sign in again with the compliant password, then "change" it to itself.
cl.get("/login")
cl.post("/login", data={"email": "lena@lead.test", "password": new, "csrf_token": _csrf(cl)})
settle_mfa(cl)
cl.get("/account/password")
r = cl.post("/account/password", data={"current_password": new, "new_password": new,
                                       "confirm_password": new, "csrf_token": _csrf(cl)}, follow_redirects=False)
pw2 = r.status_code == 303 and r.headers.get("location") == "/"
print(f"PW2 change to the SAME compliant password -> {r.status_code} location={r.headers.get('location')!r} -> reproduces={pw2}")
ok += pw2; need += 1

print(f"exit={0 if ok == need else 1}")
sys.exit(0 if ok == need else 1)

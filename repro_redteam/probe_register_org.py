"""Red-team 2026-10-15: unauthenticated POST /register-organization (web) and /api/v1/auth/register-organization (mobile).
Invite gating, password policy parity, duplicate email/org handling, orphan rows, name/CRLF into verification mail, rate limit.
LOCAL ONLY. SMTP sink on 127.0.0.1:$SINK_PORT (default 2526): python3.11 -m smtpd -c DebuggingServer -n 127.0.0.1:2526"""
import os, sqlite3, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
db = Path(tempfile.mkdtemp())/"s.db"
INV = "test-invite-123"
os.environ.update({"AMLKIT_DB": str(db), "AMLKIT_SMTP_HOST": "127.0.0.1", "AMLKIT_SMTP_PORT": os.environ.get("SINK_PORT", "2526"),
                   "AMLKIT_SMTP_USE_TLS": "0", "AMLKIT_REGISTRATION_INVITE_CODE": INV})
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
limiter.reset(); cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False); cl.get("/register-organization")
def q(sql, *a):
    c = sqlite3.connect(db); r = c.execute(sql, a).fetchall(); c.close(); return r
def web(**over):
    cl.get("/register-organization"); f = {"org_name": "Org One", "name": "Ann", "email": "ann@one.ae", "password": "Str0ng!Passw0rd", "invite_code": INV}
    f.update(over); f["csrf_token"] = cl.cookies.get(auth.CSRF_COOKIE); return cl.post("/register-organization", data=f)
def api(**over):
    b = {"org_name": "Org Api", "name": "Bob", "email": "bob@api.ae", "password": "Str0ng!Passw0rd", "invite_code": INV}; b.update(over)
    return cl.post("/api/v1/auth/register-organization", json=b)
def counts(): return q("select (select count(*) from organizations),(select count(*) from operators)")[0]
print("== 1. invite gating ==")
for label, inv in [("wrong", "nope"), ("empty", ""), ("non-ASCII", "тест✓"), ("prefix", INV[:-1]), ("padded", f"  {INV}  ")]:
    limiter.reset(); n = counts(); r = web(invite_code=inv, org_name=f"G {label}", email=f"{abs(hash(label))}@g.ae"); print(f" web {label:10s} -> {r.status_code} created={counts()!=n}")
    limiter.reset(); n = counts(); r = api(invite_code=inv, org_name=f"GA {label}", email=f"a{abs(hash(label))}@g.ae"); print(f" api {label:10s} -> {r.status_code} created={counts()!=n}")
print("== 2. password policy parity (web/api) ==")
for pw in ["alllowercase12", "Short1!", "NOUPPERCASE", "10charsnodigit!A", "x"*10, "Str0ng!Passw0rd"]:
    limiter.reset(); r1 = web(password=pw, org_name=f"P {pw}", email=f"w{abs(hash(pw))}@p.ae"); limiter.reset(); r2 = api(password=pw, org_name=f"PA {pw}", email=f"a{abs(hash(pw))}@p.ae")
    print(f" {pw!r:20s} web={r1.status_code} api={r2.status_code}")
print(" operators with weak passwords registered (rows):", counts())
print("== 3. duplicate email / org name, orphan rows ==")
limiter.reset(); web(org_name="Dup Org", email="dup@d.ae"); n = counts()
limiter.reset(); r = web(org_name="Another Org", email="dup@d.ae"); print(" dup email web ->", r.status_code, "| orgs/operators delta:", tuple(a-b for a, b in zip(counts(), n)), "| text:", ("already exists" in r.text))
limiter.reset(); r = api(org_name="Another Org 2", email="DUP@d.ae"); print(" dup email api (case) ->", r.status_code, r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else "")
limiter.reset(); r = web(org_name="DUP-org!", email="x1@d.ae"); print(" slug collision 'DUP-org!' ->", r.status_code, "| text:", ("similar name" in r.text))
limiter.reset(); r1 = web(org_name="!!!", email="x2@d.ae"); limiter.reset(); r2 = web(org_name="???", email="x3@d.ae"); print(" empty-slug orgs '!!!' then '???' ->", r1.status_code, r2.status_code, "| text2 collision:", ("similar name" in r2.text))
limiter.reset(); r = web(org_name="شركة النور", email="x4@d.ae"); r2_ = None; limiter.reset(); r2_ = web(org_name="شركة الأمل", email="x5@d.ae"); print(" Arabic org names (slug 'org' for both?) ->", r.status_code, r2_.status_code, "| second collides:", ("similar name" in r2_.text))
print(" orphans (orgs without operator):", q("select count(*) from organizations o where not exists (select 1 from operators p where p.org_id=o.id)")[0][0])
print("== 4. input bounds / CRLF / markup ==")
for label, over in [("CRLF in name", {"name": "Ann\r\nBcc: a@evil.test"}), ("CRLF in org", {"org_name": "O\r\nBcc: a@evil.test"}), ("CRLF in email", {"email": "c@c.ae\r\nBcc: a@evil.test"}),
                    ("markup org", {"org_name": "<script>alert(1)</script>"}), ("5000-char org", {"org_name": "Z"*5000}), ("NUL in org", {"org_name": "a\x00b"}),
                    ("blank name", {"name": "   "}), ("blank org", {"org_name": "   "}), ("1MB password", {"password": "Aa1!"*250000})]:
    limiter.reset(); n = counts(); r = web(**{"email": f"i{abs(hash(label))}@i.ae", **({"org_name": f"I {label}"} if "org_name" not in over else {}), **over})
    print(f" web {label:15s} -> {r.status_code} created={tuple(a-b for a,b in zip(counts(), n))}")
print("== 5. rate limit (5/min per IP) ==")
limiter.reset(); codes = [web(org_name=f"R{i}", email=f"r{i}@r.ae", invite_code="bad").status_code for i in range(7)]; print(" 7 wrong-invite web posts:", codes)
limiter.reset(); codes = [api(org_name=f"RA{i}", email=f"ra{i}@r.ae", invite_code="bad").status_code for i in range(7)]; print(" 7 wrong-invite api posts:", codes)
print(" auth_events register_denied rows:", q("select count(*) from auth_events where event='register_denied'")[0][0] if q("select name from sqlite_master where name='auth_events'") else "n/a")
print("== 6. invite unset => closed? ==")
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = ""; limiter.reset(); n = counts(); r = web(invite_code=""); r2 = api(invite_code=""); print(" web", r.status_code, "api", r2.status_code, "created:", counts() != n)

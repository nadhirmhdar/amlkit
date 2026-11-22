"""Red-team 2026-11-19: PR #463 master switch AMLKIT_BILLING_ENABLED. With the Stripe keys present but the switch unset/false, every billing surface must stay off and sign-up must go back
to the invite gate; with the switch on it must behave as before. Includes odd flag spellings. LOCAL ONLY; Stripe never contacted."""
import os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
os.environ.update({"AMLKIT_DB": str(Path(tempfile.mkdtemp())/"s.db"), "STRIPE_SECRET_KEY": "sk_test_x", "STRIPE_WEBHOOK_SECRET": "whsec_x", "STRIPE_PRICE_STARTER": "price_s", "AMLKIT_REGISTRATION_INVITE_CODE": "invite-123"})
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.billing import self_serve_enabled
from amlkit.billing.stripe_client import billing_switched_on
def probe(flag):
    if flag is None: os.environ.pop("AMLKIT_BILLING_ENABLED", None)
    else: os.environ["AMLKIT_BILLING_ENABLED"] = flag
    limiter.reset(); cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False)
    r = cl.get("/register-organization"); form_has_invite = "invite" in r.text.lower()
    cl.get("/register-organization"); limiter.reset()
    reg = cl.post("/register-organization", data={"org_name": f"O {flag}", "name": "N", "email": f"{abs(hash(str(flag)))}@x.test", "password": "Str0ng!Passw0rd", "invite_code": "", "csrf_token": cl.cookies.get(auth.CSRF_COOKIE)})
    created = "Account created" in reg.text or "verification" in reg.text.lower() and "Invalid invite" not in reg.text
    wh = cl.post("/billing/webhook", content=b"{}"); bl = cl.get("/billing"); pr = cl.get("/pricing")
    print(f" flag={flag!r:10} switched_on={billing_switched_on()!s:5} self_serve={self_serve_enabled()!s:5} | signup form shows invite field: {form_has_invite!s:5} | open sign-up without invite works: {created!s:5} | webhook {wh.status_code} /billing {bl.status_code} /pricing {pr.status_code}")
for f in [None, "", "0", "false", "no", "off", "maybe", "2", "1", "true", "YES", " on ", "On"]: probe(f)

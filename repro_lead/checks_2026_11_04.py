"""Lead checks for 2026-11-04 (master 6560fb0). Local scratch DB only, no network.

Counts as reproducing (exit 0 if any reproduce, 1 if none):
  SS1  open sign-up (Stripe mode, dummy key) reveals an existing account email / org name
  SS2  an unpaid (pending_payment) org can run and persist ad-hoc screenings
Printed for information (not counted):
  MK2  public copy says every confirmed sanctions match creates a freeze obligation
  CS24 uaepass_verifications has no column recording which UAE PASS environment produced the row

Run from the repo root:  PYTHONPATH=. python repro_lead/checks_2026_11_04.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

tmp = Path(tempfile.mkdtemp(prefix="lead1104_"))
os.environ["AMLKIT_DB"] = str(tmp / "lead.db")
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)
os.environ["STRIPE_SECRET_KEY"] = "sk_test_dummy_never_used"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_dummy"
os.environ["STRIPE_PRICE_STARTER"] = "price_starter_dummy"

from test_api import _csrf, _db, _seed_sanctions_data  # noqa: E402
from conftest import settle_mfa  # noqa: E402

_seed_sanctions_data(Path(os.environ["AMLKIT_DB"]))
from fastapi.testclient import TestClient  # noqa: E402
from amlkit.api.app import app  # noqa: E402
from amlkit.api.app import limiter  # noqa: E402

limiter.enabled = False  # rate limits are not under test here


def signup(c, org, email):
    c.get("/register-organization")
    return c.post("/register-organization", data={
        "org_name": org, "name": "Owner One", "email": email,
        "password": "A-strong-password-1", "csrf_token": _csrf(c),
    }, follow_redirects=True)


repro = 0

# ---- SS1
c = TestClient(app)
r1 = signup(c, "Alpha Trading", "victim@alpha.ae")
first_ok = "Check your email" in r1.text
anon = TestClient(app)
r2 = signup(anon, "Totally Different Firm", "victim@alpha.ae")
r3 = signup(anon, "Another Firm", "nobody@nowhere.ae")
r4 = signup(TestClient(app), "Alpha Trading", "someone@else.ae")
email_leak = "already exists" in r2.text and "Check your email" in r3.text
name_leak = "similar name already exists" in r4.text
print(f"SS1  first signup ok={first_ok}; known email -> {'already exists' if 'already exists' in r2.text else 'generic'}; "
      f"unknown email -> {'Check your email' if 'Check your email' in r3.text else 'other'}; "
      f"known org name -> {'similar name already exists' if name_leak else 'generic'}")
ss1 = first_ok and (email_leak or name_leak)
print(f"SS1  reproduces={ss1}")
repro += ss1

# ---- SS2
m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r1.text)
c.get(f"/verify-email?token={m.group(1)}", follow_redirects=False)
settle_mfa(c)
conn = _db()
org = conn.execute("SELECT id, plan, plan_status FROM organizations WHERE name='Alpha Trading'").fetchone()
before = conn.execute("SELECT COUNT(*) FROM screenings WHERE org_id=?", (org["id"],)).fetchone()[0]
conn.close()
codes = []
for i in range(5):
    rr = c.post("/screen", data={"name": f"Probe Person {i}", "csrf_token": _csrf(c)}, follow_redirects=False)
    codes.append(rr.status_code)
conn = _db()
after = conn.execute("SELECT COUNT(*) FROM screenings WHERE org_id=?", (org["id"],)).fetchone()[0]
ret = conn.execute("SELECT retention_until FROM screenings WHERE org_id=? ORDER BY id DESC LIMIT 1", (org["id"],)).fetchone()
conn.close()
print(f"SS2  org plan={org['plan']} status={org['plan_status']}; 5 x POST /screen -> {codes}; "
      f"screenings rows {before} -> {after}; retention_until={ret[0] if ret else None}")
ss2 = org["plan_status"] == "pending_payment" and after - before >= 5
print(f"SS2  reproduces={ss2}")
repro += ss2

# ---- MK2 (info)
from amlkit.sanctions_scope import is_uae_freeze_list  # noqa: E402
land = (ROOT / "amlkit/web/templates/landing.html").read_text()
law = (ROOT / "amlkit/web/templates/aml_law.html").read_text()
print(f"MK2  landing says 'Confirmed sanctions matches create freeze obligations': "
      f"{'Confirmed sanctions matches create freeze obligations' in land}; "
      f"aml_law says 'Freeze obligations created from confirmed matches': "
      f"{'Freeze obligations created from confirmed matches' in law}; "
      f"is_uae_freeze_list('us_ofac_sdn')={is_uae_freeze_list('us_ofac_sdn')}")

# ---- CS24 (info)
conn = _db()
cols = [r[1] for r in conn.execute("PRAGMA table_info(uaepass_verifications)")]
conn.close()
print(f"CS24 uaepass_verifications columns={cols}; environment column present="
      f"{any('env' in x for x in cols)}; landing mentions 'sandbox'={'sandbox' in land.lower()}")

print(f"{repro}/2 reproduce")
sys.exit(0 if repro else 1)

"""Lead checks for 2026-11-09 (master 9219e26). Local scratch DB only, no network.

Counts as reproducing (exit 0 if any reproduce, 1 if none):
  SS5   a sign-up display name carrying markup and a URL is accepted and lands
        verbatim in the body of the verification mail groAML sends
        (SMTP is a fake class patched into amlkit.mail; nothing is sent)
  RT1   a complete DPMSR / REAR report is refused by the goAML layer
        (SUPPORTED_REPORT_TYPES = STR, SAR, FFR)
  RT2   GET /reports/build?report_type=DPMSR renders the builder (200) for a
        type that cannot be saved

Run from the repo root:  PYTHONPATH=. python repro_lead/checks_2026_11_09.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

tmp = Path(tempfile.mkdtemp(prefix="lead1109_"))
os.environ["AMLKIT_DB"] = str(tmp / "lead.db")
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)
os.environ.pop("AMLKIT_SMTP_HOST", None)
os.environ.pop("STRIPE_SECRET_KEY", None)
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = "test-invite"

from test_api import _register, _seed_sanctions_data  # noqa: E402

_seed_sanctions_data(Path(os.environ["AMLKIT_DB"]))
from fastapi.testclient import TestClient  # noqa: E402
from amlkit import auth, db as amldb, mail  # noqa: E402
from amlkit.api.app import app, limiter  # noqa: E402
from amlkit.cases import manager  # noqa: E402
from amlkit.reporting import goaml  # noqa: E402

limiter.enabled = False
repro = 0

# --- SS5 -------------------------------------------------------------------
hostile = "Mallory <b>bold</b> https://evil.test/pay"
clean_name, _ = auth.check_operator_identity(hostile, "target@victim.ae")
sent: list = []


class FakeSMTP:
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self, *a, **k): pass
    def login(self, *a, **k): pass
    def send_message(self, msg, *a, **k): sent.append(msg)


os.environ["AMLKIT_SMTP_HOST"] = "smtp.invalid"
mail.smtplib.SMTP = FakeSMTP
try:
    outcome = mail.send_verification_email("target@victim.ae", clean_name, "tok123")
finally:
    os.environ.pop("AMLKIT_SMTP_HOST", None)
body = sent[0].get_content() if sent else ""
first = body.splitlines()[0] if body else ""
print(f"SS5   name accepted by check_operator_identity={clean_name!r}; send outcome={outcome}")
print(f"SS5   mail greeting line: {first!r}")
ss5 = "https://evil.test/pay" in first and "<b>" in first
print(f"SS5   reproduces={ss5}")
repro += ss5

# --- RT1 -------------------------------------------------------------------
refused = {}
for code in ("DPMSR", "REAR"):
    try:
        goaml.serialize_goaml_xml({"report_type": code})
        refused[code] = None
    except ValueError as exc:
        refused[code] = str(exc)
print(f"RT1   SUPPORTED_REPORT_TYPES={sorted(goaml.SUPPORTED_REPORT_TYPES)}")
for code, msg in refused.items():
    print(f"RT1   {code}: {msg}")
rt1 = all(m and "not supported" in m for m in refused.values())
print(f"RT1   reproduces={rt1}")
repro += rt1

# --- RT2 -------------------------------------------------------------------
c = _register(TestClient(app), "Lead Realty", "Owner One", "owner@leadrealty.ae")
conn = amldb.connect(os.environ["AMLKIT_DB"])
org_id = conn.execute("SELECT org_id FROM operators WHERE email=?", ("owner@leadrealty.ae",)).fetchone()[0]
result = manager.onboard(conn, org_id=org_id, reference="RE-1", full_name="Test Buyer", actor="Owner One")
conn.commit()
cid = conn.execute("SELECT id FROM customers WHERE org_id=? AND reference='RE-1'", (org_id,)).fetchone()[0]
conn.close()
statuses = {}
for code in ("STR", "DPMSR", "REAR", "HRCT"):
    r = c.get(f"/reports/build?customer_id={cid}&report_type={code}", follow_redirects=False)
    statuses[code] = (r.status_code, "not supported" in r.text.lower() or "not available" in r.text.lower())
print(f"RT2   GET /reports/build (status, page warns type unsupported): {statuses}")
rt2 = all(statuses[k][0] == 200 and not statuses[k][1] for k in ("DPMSR", "REAR", "HRCT"))
print(f"RT2   reproduces={rt2}")
repro += rt2

print(f"{repro}/3 reproduce")
sys.exit(0 if repro else 1)

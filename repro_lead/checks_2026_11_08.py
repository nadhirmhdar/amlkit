"""Lead checks for 2026-11-08 (master 9219e26). Local scratch DB only, no network.

Counts as reproducing (exit 0 if any reproduce, 1 if none):
  SS1b  open sign-up (Stripe mode, dummy key): existing-email path is measurably
        faster than the new-email path although the pages match (timing oracle)
  SS3b  repeated open sign-ups for one existing address each send a notice mail
        (no per-address cooldown)
  CS24  uaepass_verifications has no column recording the UAE PASS environment,
        and the in-product button is gated on "configured", not "production"
  CS5d  the Cloud Scheduler step that sets the 4-hourly refresh is
        continue-on-error and nothing reads the schedule back
Printed for information only:
  CR40  EU_FSF_TOKEN expression is blanked on pull_request runs (fixed by #462)

Run from the repo root:  PYTHONPATH=. python repro_lead/checks_2026_11_08.py
"""
from __future__ import annotations

import os
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

tmp = Path(tempfile.mkdtemp(prefix="lead1108_"))
os.environ["AMLKIT_DB"] = str(tmp / "lead.db")
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)
os.environ.pop("AMLKIT_SMTP_HOST", None)
os.environ["STRIPE_SECRET_KEY"] = "sk_test_dummy_never_used"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_dummy"
os.environ["STRIPE_PRICE_STARTER"] = "price_starter_dummy"

from test_api import _csrf, _seed_sanctions_data  # noqa: E402

_seed_sanctions_data(Path(os.environ["AMLKIT_DB"]))
from fastapi.testclient import TestClient  # noqa: E402
from amlkit import mail  # noqa: E402
from amlkit.api.app import app, limiter  # noqa: E402

limiter.enabled = False  # rate limits are not under test here

notices: list[str] = []
_orig_notice = mail.send_existing_account_notice


def _count_notice(to_email, name):
    notices.append(to_email)
    return _orig_notice(to_email, name)


mail.send_existing_account_notice = _count_notice
import amlkit.cases.operators as ops  # noqa: E402
ops.mail.send_existing_account_notice = _count_notice


def signup(c, org, email):
    c.get("/register-organization")
    t0 = time.perf_counter()
    r = c.post("/register-organization", data={
        "org_name": org, "name": "Owner One", "email": email,
        "password": "A-strong-password-1", "csrf_token": _csrf(c),
    }, follow_redirects=True)
    return r, (time.perf_counter() - t0) * 1000


def mask(text, email):
    text = text.replace(email, "EMAIL")
    return re.sub(r'name="csrf_token" value="[^"]*"', "", text)


repro = 0
c = TestClient(app)
r0, _ = signup(c, "Alpha Trading", "victim@alpha.ae")
assert r0.status_code == 200, r0.status_code

new_ms, old_ms, same = [], [], True
for i in range(12):
    rn, tn = signup(TestClient(app), f"Firm {i}", f"new{i}@nowhere.ae")
    ro, to = signup(TestClient(app), f"Other {i}", "victim@alpha.ae")
    new_ms.append(tn)
    old_ms.append(to)
    same &= mask(rn.text, f"new{i}@nowhere.ae") == mask(ro.text, "victim@alpha.ae")
mn, mo = statistics.median(new_ms), statistics.median(old_ms)
print(f"SS1b  12 pairs: median new-email {mn:.1f} ms vs existing-email {mo:.1f} ms; pages identical after masking={same}")
ss1b = mn - mo > 30
print(f"SS1b  reproduces={ss1b}")
repro += ss1b

print(f"SS3b  existing-account notices sent to victim@alpha.ae over 12 sign-ups: {notices.count('victim@alpha.ae')}")
ss3b = notices.count("victim@alpha.ae") >= 12
print(f"SS3b  reproduces={ss3b}")
repro += ss3b

db_src = (ROOT / "amlkit/db.py").read_text()
m = re.search(r"CREATE TABLE IF NOT EXISTS uaepass_verifications \((.*?)\);", db_src, re.S)
cols = re.findall(r"^\s+(\w+)\s", m.group(1), re.M)
has_env = any("env" in col for col in cols)
helpers = (ROOT / "amlkit/api/helpers.py").read_text()
button_gate = re.search(r'ctx\.setdefault\("uaepass_enabled",\s*(.*?)\)\n', helpers)
gate = button_gate.group(1) if button_gate else "?"
print(f"CS24  uaepass_verifications columns={cols}; env column={has_env}")
print(f"CS24  in-product button gate: uaepass_enabled = {gate}")
cs24 = (not has_env) and "ENV" not in gate and "production" not in gate
print(f"CS24  reproduces={cs24}")
repro += cs24

wf = (ROOT / ".github/workflows/source-canary.yml").read_text()
idx = wf.find('--schedule "0 */4 * * *"')
step_start = wf.rfind("- name:", 0, idx)
step = wf[step_start:idx]
coe = "continue-on-error: true" in step
# An existence probe (`describe ... >/dev/null`) is not a read-back; a real one
# reads the schedule field and compares it.
readback = bool(re.search(r"scheduler jobs describe[^\n]*(\\\n[^\n]*)*--format[^\n]*schedule", wf))
print(f"CS5d  refresh step continue-on-error={coe}; any 'scheduler jobs describe' read-back={readback}")
cs5d = coe and not readback
print(f"CS5d  reproduces={cs5d}")
repro += cs5d

pr_lines = [ln.strip() for ln in wf.splitlines() if "EU_FSF_TOKEN" in ln and "AMLKIT_EU_FSF_TOKEN:" in ln]
print(f"CR40  (info) token lines: {pr_lines}")

print(f"{repro}/4 reproduce")
sys.exit(0 if repro else 1)

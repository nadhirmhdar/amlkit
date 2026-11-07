"""Lead checks for 2026-11-07 (master 6560fb0). Local scratch DB only, no network.

Counts as reproducing (exit 0 if any reproduce, 1 if none):
  BL1  a signed subscription event with an unknown price and metadata.tier not in PLANS
       stores that string as the plan, and check_limit then allows creation past the cap
  CR1  no web or mobile route edits a customer's full_name / birth_date / nationality /
       id_number after onboarding (route scan + grep of every UPDATE customers statement)
  CR2  the same person (same name, same birth date) onboards twice under new references
  CR3  references differing only by case ('c-001' vs 'C-001') coexist in one org

Run from the repo root:  PYTHONPATH=. python repro_lead/checks_2026_11_07.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

tmp = Path(tempfile.mkdtemp(prefix="lead1107_"))
os.environ["AMLKIT_DB"] = str(tmp / "lead.db")
os.environ["STRIPE_SECRET_KEY"] = "sk_test_dummy_never_used"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_dummy"
os.environ["STRIPE_PRICE_STARTER"] = "price_starter_dummy"

import logging  # noqa: E402

logging.disable(logging.CRITICAL)

sys.path.insert(0, str(ROOT / "tests"))
from test_api import _seed_sanctions_data  # noqa: E402

_seed_sanctions_data(Path(os.environ["AMLKIT_DB"]))
from amlkit.db import connect  # noqa: E402
from amlkit.billing import limits, stripe_client  # noqa: E402
from amlkit.billing.service import apply_subscription  # noqa: E402
from amlkit.cases import manager  # noqa: E402

repro = 0
conn = connect(Path(os.environ["AMLKIT_DB"]))
conn.execute("INSERT INTO organizations (name, slug, created_at) VALUES ('Lead Org', 'lead-org', '2026-11-07T00:00:00+00:00')")
org = conn.execute("SELECT id FROM organizations").fetchone()[0]

# ---- BL1
conn.execute("UPDATE organizations SET plan='starter', plan_status='active' WHERE id=?", (org,))
for i in range(3):  # starter cap = 3 operators
    conn.execute("INSERT INTO operators (org_id, name, email, role, created_at) VALUES (?,?,?,?,?)",
                 (org, f"Op {i}", f"op{i}@lead.test", "officer", "2026-11-07T00:00:00+00:00"))
conn.commit()


def allowed() -> str:
    try:
        limits.check_limit(conn, org, "operators")
        return "allowed"
    except limits.BillingLimitError as e:
        return "refused: " + str(e)[:50]


before = allowed()
cfg = stripe_client.load_config()
sub = {"id": "sub_1", "status": "active", "customer": "cus_1",
       "metadata": {"org_id": str(org), "tier": "enterprise-free"},
       "items": {"data": [{"price": {"id": "price_unknown"}}]}}
apply_subscription(conn, org, sub, cfg, event_type="customer.subscription.updated")
conn.commit()
plan = conn.execute("SELECT plan FROM organizations WHERE id=?", (org,)).fetchone()[0]
after = allowed()
bl1 = before.startswith("refused") and plan == "enterprise-free" and after == "allowed"
print(f"BL1  starter, 3/3 operators: 4th operator -> {before}")
print(f"BL1  after signed event (unknown price, metadata.tier='enterprise-free'): plan={plan!r}; 4th operator -> {after}")
print(f"BL1  reproduces={bl1}")
repro += bl1

# ---- CR1
edit_routes = []  # static scan: decorators in amlkit/api (web routers + mobile)
for py in (ROOT / "amlkit" / "api").rglob("*.py"):
    for m in re.finditer(r'@\w+\.(post|put|patch)\(\s*"([^"]*customers/\{[^"]*)"', py.read_text(encoding="utf-8")):
        edit_routes.append(f"{m.group(1).upper()} {m.group(2)}")
identity = ("full_name", "birth_date", "nationality", "id_number", "name_arabic")
updates_identity = []
for py in (ROOT / "amlkit").rglob("*.py"):
    if py.name == "db.py":
        continue
    text = py.read_text(encoding="utf-8")
    for m in re.finditer(r"UPDATE customers SET[^\"']*", text):
        stmt = m.group(0)
        if any(f"{f}=" in stmt.replace(" ", "") for f in identity):
            updates_identity.append(f"{py.relative_to(ROOT)}: {stmt[:60]}")
named_edit = [p for p in edit_routes if re.search(r"/(edit|update|identity|details)\b", p)]
print(f"CR1  customer write routes: {sorted(edit_routes)}")
print(f"CR1  any named edit/update/identity/details: {named_edit}")
print(f"CR1  literal UPDATE customers statements naming {identity}: {updates_identity}")
print("CR1  (the only dynamic SET lists are the UAE PASS empty-field backfill, manager.py:1509,"
      " and mobile risk-factors, mobile.py:941 - sector/delivery_channel/is_cash_intensive)")
cr1 = not named_edit and not updates_identity
print(f"CR1  reproduces={cr1}")
repro += cr1

# ---- CR2 / CR3
def onb(ref: str, name: str) -> str:
    try:
        manager.onboard(conn, org_id=org, reference=ref, full_name=name, birth_date="1990-01-01",
                        nationality="AE", actor="lead")
        conn.commit()
        return "accepted"
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return f"refused ({type(e).__name__}: {str(e)[:50]})"


# legacy org for CR2/CR3 so billing limits do not interfere
conn.execute("UPDATE organizations SET plan='trial', plan_status=NULL, trial_ends_at=NULL WHERE id=?", (org,))
conn.commit()
r1 = onb("C-001", "Fatma Khan")
r2 = onb("C-002", "Fatma Khan")
r3 = onb("C-003", "fatma khan")
r4 = onb("c-001", "Someone Else")
r5 = onb("C-001", "Someone Else")
n = conn.execute("SELECT COUNT(*) FROM customers WHERE org_id=? AND lower(full_name)='fatma khan'"
                 " AND birth_date='1990-01-01'", (org,)).fetchone()[0]
print(f"CR2  C-001 {r1}; C-002 same name+DOB {r2}; C-003 lower-case name {r3}; rows for that person={n}")
cr2 = n >= 2
print(f"CR2  reproduces={cr2}")
refs = [x[0] for x in conn.execute("SELECT reference FROM customers WHERE org_id=? AND lower(reference)='c-001'", (org,))]
print(f"CR3  'c-001' {r4}; exact 'C-001' again {r5}; references stored={refs}")
cr3 = len(refs) == 2
print(f"CR3  reproduces={cr3}")
repro += cr3 + cr2

print(f"{repro}/4 reproduce")
sys.exit(0 if repro else 1)

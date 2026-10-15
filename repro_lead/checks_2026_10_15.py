"""Lead repro, 2026-10-15. Exits 0 when every defect below reproduces.

L-56 (mlro-user C4, owed by the lead): customer search is not truncated; the
     over-long query is canonicalised. canonical_tokens('a'*2000) == ['a'],
     and search_customers() matches each canonical token with a substring
     LIKE '%a%' on canonical_key, so any customer whose key contains an 'a'
     comes back. Same for a short query such as 'aa'.
R1   (red-team, skeptic): register_organization's slug keeps [a-z0-9] only
     (cases/operators.py:38), so two Arabic-only org names both become 'org'
     and the second hits UNIQUE(slug) (db.py:147).
R2   (red-team, skeptic): register_organization checks len(password) >= 10
     only (cases/operators.py:32), not validate_password_complexity.

Scratch :memory: DB, no network.
Run from the repo root: PYTHONPATH=.:tests python repro_lead/checks_2026_10_15.py
"""
import os
import sys

os.environ.pop("AMLKIT_SMTP_HOST", None)

from amlkit import db, queries
from amlkit.cases.manager import onboard
from amlkit.cases.operators import register_organization
from test_p43_alerts_group_dismiss import _seed

conn = db.connect(":memory:")
org = _seed(conn)["org_id"]
for ref, name in [("Q-001", "Ahmed Abd Al-Jaleel Al-Hasnawi"), ("Q-002", "Fatima Khan"),
                  ("Q-003", "100% Trading_LLC"), ("Q-004", "O'Brien Holdings")]:
    onboard(conn, org_id=org, reference=ref, full_name=name, actor="lead")
ok = 0

def refs(q):
    return sorted(c["reference"] for c in queries.search_customers(conn, org, q) if c["reference"].startswith("Q-"))

long_hits, aa_hits = refs("a" * 2000), refs("aa")
s56 = bool(long_hits) and bool(aa_hits)
print(f"L-56 search 'a'*2000 -> {long_hits}; search 'aa' -> {aa_hits} -> reproduces={s56}")
ok += s56

def reg(org_name, email, pw):
    try:
        register_organization(conn, org_name=org_name, operator_name="Op", email=email, password=pw)
        return "created"
    except Exception as e:  # noqa: BLE001 - the repro reports whatever is raised
        return f"{type(e).__name__}: {e}"

first, second = reg("شركة النور", "r1a@t.test", "Str0ng-pass!"), reg("شركة الأمل", "r1b@t.test", "Str0ng-pass!")
r1 = first == "created" and second.startswith("ValueError")
print(f"R1   Arabic org #1 {first}; #2 {second} -> reproduces={r1}")
ok += r1

weak = reg("Weak Pw Firm", "r2@t.test", "xxxxxxxxxx")
r2 = weak == "created"
print(f"R2   register with 'xxxxxxxxxx' -> {weak} -> reproduces={r2}")
ok += r2

sys.exit(0 if ok == 3 else 1)

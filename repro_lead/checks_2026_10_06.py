"""Lead 2026-10-06 checks. Local :memory: DB and synthetic watchlist only.

Exit 0 when BOTH open defects reproduce:
  G9  - /admin/rescreen reads outcome['customers'] but rescreen_all returns
        {'screened', 'alerts'}, so the route always shows "Re-screening failed".
  L-9 - rescreen_all raises a fresh open alert for a match whose alert is
        already pending_review or dismissed (dedupe keys on status='open').
Also prints (informational, not part of the exit code) the #426 four-eyes
fix on the operator_id path and its legacy name-only fallback.
"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
from amlkit.db import connect, upsert_dataset, utcnow
from amlkit.names.arabic import blocking_keys, canonical_key
from amlkit.match.engine import rescreen_all
from amlkit.cases import manager
from amlkit.cases.review import propose_disposition, confirm_disposition, ReviewError
from amlkit.cases.operators import rename_operator
import test_matching as tm

c = connect(":memory:")
ds = upsert_dataset(c, "test_list", "Synthetic", is_mandatory=True); now = utcnow()
for sid, schema, caption, aliases, country, dob, gender in tm.WATCHLIST:
    eid = c.execute("""INSERT INTO entities (dataset_id, source_id, schema_type, caption, countries,
        birth_date, gender, topics, raw, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, sid, schema, caption, f'["{country}"]', dob, gender, '["sanction"]', "{}", now, now)).lastrowid
    for i, nm in enumerate([caption, *aliases]):
        c.execute("INSERT INTO entity_names (entity_id,name,name_type,canonical_key,script) VALUES (?,?,?,?,?)",
                  (eid, nm, "primary" if i == 0 else "alias", canonical_key(nm), "latin"))
        for t in blocking_keys(nm):
            c.execute("INSERT OR IGNORE INTO name_tokens (token,entity_id) VALUES (?,?)", (t, eid))
c.execute("UPDATE datasets SET last_refresh=?, entity_count=?", (now, len(tm.WATCHLIST)))
c.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)", (now,))
for name, role in (("Alice", "mlro"), ("Bob", "officer")):
    c.execute("INSERT INTO operators (org_id,email,password_hash,name,role,is_active,created_at) VALUES (1,?,?,?,?,1,?)",
              (f"{name.lower()}@t", "x", name, role, now))
c.commit()
alice_id = c.execute("SELECT id FROM operators WHERE name='Alice'").fetchone()[0]

# ---- G9: route key vs rescreen_all return keys
app_src = open(os.path.join(ROOT, "amlkit/api/app.py"), encoding="utf-8").read()
route_reads = "outcome['customers']" in app_src
out = rescreen_all(c, 1)
g9 = route_reads and "customers" not in out
print(f"G9  rescreen_all keys={sorted(out)} | route reads outcome['customers']={route_reads} -> reproduces={g9}")

# ---- L-9: re-alert on already-decided alerts
for i, ref in enumerate(("R1", "R2")):
    manager.onboard(c, org_id=1, reference=ref, full_name="BILAL ALI AL-WAFI", actor="lead")
c.commit()
alerts = [r[0] for r in c.execute("SELECT id FROM alerts WHERE org_id=1 AND status='open' ORDER BY id")]
print("L-9 open alerts after onboarding:", alerts)
propose_disposition(c, alerts[0], org_id=1, status="false_positive", reason_code="name_coincidence",
                    operator="Alice", operator_id=alice_id, narrative="different DOB")   # -> pending_review
c.execute("UPDATE alerts SET status='false_positive' WHERE id=?", (alerts[1],)); c.commit()  # already decided
before = [tuple(r) for r in c.execute("SELECT id,status FROM alerts ORDER BY id")]
r = rescreen_all(c, 1); c.commit()
after = [tuple(r) for r in c.execute("SELECT id,status FROM alerts ORDER BY id")]
new_open = [a for a, s in after if s == "open" and a not in alerts]
l9 = len(new_open) > 0
print(f"L-9 before={before}\n    rescreen_all={r}\n    after={after} -> new open alerts {new_open}, reproduces={l9}")

# ---- #426 four-eyes (informational)
rename_operator(c, alice_id, 1, "Alice Renamed", actor="Alice"); c.commit()
try:
    confirm_disposition(c, alerts[0], org_id=1, operator="Alice Renamed", operator_id=alice_id, agree=True)
    print("4E  id path: self-confirm after rename ALLOWED (regression)")
except ReviewError as e:
    print("4E  id path: self-confirm after rename refused ->", str(e)[:70])
legacy = c.execute("SELECT id FROM alerts WHERE status='open' ORDER BY id DESC LIMIT 1").fetchone()[0]
propose_disposition(c, legacy, org_id=1, status="false_positive", reason_code="name_coincidence",
                    operator="Alice Renamed", narrative="x")   # no operator_id: a pre-#426 pending row
rename_operator(c, alice_id, 1, "Alice Again", actor="Alice"); c.commit()
try:
    o = confirm_disposition(c, legacy, org_id=1, operator="Alice Again", operator_id=alice_id, agree=True)
    print("4E  legacy NULL-operator_id row: same person confirmed after rename ->", o.independent_review)
except ReviewError as e:
    print("4E  legacy row refused ->", str(e)[:70])

print("exit", 0 if (g9 and l9) else 1)
sys.exit(0 if (g9 and l9) else 1)

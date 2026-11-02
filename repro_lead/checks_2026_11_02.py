"""Lead 2026-11-02 checks on master e8ddf26. :memory: SQLite, synthetic data, no network.

Exit 0 when ALL FOUR still reproduce:
  U4   - cases.manager._identified_ownership recurses once per ownership-chain
         level with no depth bound; add_ubo accepts an unbounded chain, so
         ownership_state() raises RecursionError for a ~1100-level chain.
  UBO1 - add_ubo accepts a legal customer as its own beneficial owner
         (no comparison with the customer's own name / canonical key).
  CS23 - screening.pf.obligation_note checks the dataset only AFTER the
         terrorism / proliferation branches, so an OFAC/EU/UK-only terrorism
         entry still says "Freeze without delay" although is_uae_freeze_list()
         is False and no freeze obligation is raised.
  CR31 - hypothesis (test-only) is listed in the production requirements.txt.
Exit 1 when any is fixed (re-read the printed lines).
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from amlkit import db as dbm
from amlkit.cases import manager as M
from amlkit.screening import pf
from amlkit.sanctions_scope import is_uae_freeze_list

hits = 0
c = dbm.connect(":memory:"); now = dbm.utcnow()
c.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)", (now,))
c.execute("INSERT INTO customers (org_id,reference,customer_type,full_name,canonical_key,onboarded_at,created_at,updated_at)"
          " VALUES (1,'C1','legal','Gulf Holdings LLC',?,?,?,?)", (M.canonical_key("Gulf Holdings LLC"), now, now, now))
c.commit()

# UBO1
try:
    M.add_ubo(c, 1, org_id=1, person_name="Gulf Holdings LLC", ownership_pct=30, actor="lead")
    r = "accepted"
except ValueError as e:
    r = f"ValueError: {e}"
ubo1 = r == "accepted"
print(f"UBO1 add_ubo(customer 'Gulf Holdings LLC' as its own 30% owner) -> {r} -> reproduces={ubo1}")
hits += ubo1

# U4
parent, depth, res = None, 0, None
for target in (900, 1100):
    try:
        while depth < target:
            parent = M.add_ubo(c, 1, org_id=1, person_name=f"Holdco {depth}",
                               ownership_pct=(40 if parent is None else 100), parent_ubo_id=parent, actor="lead")
            depth += 1
    except ValueError as e:
        res = f"add_ubo refused at depth {depth}: {e}"; break
    try:
        res = f"ownership_state -> {M.ownership_state(c, 1, 1, 'legal')}"
    except RecursionError:
        res = "ownership_state -> RecursionError"
    print(f"U4   depth {depth}: {res}")
u4 = res == "ownership_state -> RecursionError"
print(f"U4   reproduces={u4} (recursionlimit {sys.getrecursionlimit()})")
hits += u4

# CS23
ds = "us_ofac_sdn"
note = pf.obligation_note({"terrorism"}, ds)
cs23 = (not is_uae_freeze_list(ds)) and "freeze without delay" in note.lower()
print(f"CS23 is_uae_freeze_list({ds!r})={is_uae_freeze_list(ds)}; obligation_note({{'terrorism'}}, {ds!r}) = "
      f"{note[:60]!r}... -> reproduces={cs23}")
hits += cs23

# CR31
req = open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8").read().splitlines()
line = next((f"{i+1}: {l}" for i, l in enumerate(req) if l.strip().lower().startswith("hypothesis")), None)
cr31 = line is not None
print(f"CR31 requirements.txt hypothesis line -> {line} -> reproduces={cr31}")
hits += cr31

print(f"{hits}/4 reproduce")
sys.exit(0 if hits == 4 else 1)

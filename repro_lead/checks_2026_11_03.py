"""Lead 2026-11-03 checks on master 938050f. :memory: SQLite, synthetic data, no network.

Exit 0 when BOTH defects still reproduce:
  UBO1b - cases.manager._check_ubo_structure compares the owner with the
          customer by exact casefolded name / canonical_key only, so a legal-
          suffix variant ("GULF HOLDINGS L.L.C.", "Gulf Holdings") of the
          customer "Gulf Holdings LLC" is accepted as its own owner.
  N8b   - cases.review.confirm_disposition lets the proposer confirm a legacy
          proposal whose alert_reviews.operator_id is NULL (review.py:411-413).
Informational (not counted; settles disputed claims):
  N3b   - red-team's probe puts Cyrillic Ve (looks like B) in place of the W
          of "AL-WAFI". A true homoglyph swap (Cyrillic Ve for the B of BILAL)
          and the Latin control "AL-BAFI" are both printed.
  H1    - Referrer-Policy / Permissions-Policy on GET /login via TestClient.
Exit 1 when either counted defect is fixed (re-read the printed lines).
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.setdefault("AMLKIT_DB", ":memory:")
from amlkit import db as dbm
from amlkit.cases import manager as M
from amlkit.match.engine import screen
from amlkit.names.arabic import blocking_keys, canonical_key

hits = 0
now = dbm.utcnow()

# UBO1b
c = dbm.connect(":memory:")
c.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)", (now,))
c.execute("INSERT INTO customers (org_id,reference,customer_type,full_name,canonical_key,onboarded_at,created_at,updated_at)"
          " VALUES (1,'C1','legal','Gulf Holdings LLC',?,?,?,?)", (canonical_key("Gulf Holdings LLC"), now, now, now))
c.commit()
accepted = []
for nm in ("Gulf Holdings LLC", "GULF  holdings llc", "GULF HOLDINGS L.L.C.", "Gulf Holdings", "Gulf Holdings FZE"):
    try:
        M.add_ubo(c, 1, org_id=1, person_name=nm, ownership_pct=10, actor="lead"); r = "accepted"; accepted.append(nm)
    except ValueError as e:
        r = f"refused ({str(e)[:45]}...)"
    print(f"UBO1b owner {nm!r:24} canonical_key={canonical_key(nm)!r:22} -> {r}")
ubo1b = len(accepted) > 0
print(f"UBO1b reproduces={ubo1b} ({len(accepted)} suffix variants accepted)")
hits += ubo1b

# N8b: legacy proposal with NULL operator_id confirmed by its own proposer
from amlkit.cases.review import propose_disposition, confirm_disposition, ReviewError
from test_p43_alerts_group_dismiss import _seed
c2 = dbm.connect(":memory:"); sd = _seed(c2); org, aid = sd["org_id"], sd["alert_ids"][0]
op = c2.execute("SELECT id FROM operators WHERE org_id=?", (org,)).fetchone()[0]
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)
propose_disposition(c2, aid, org_id=org, status="false_positive", reason_code="name_coincidence",
                    narrative="legacy", operator="Proposer", operator_id=op)
c2.execute("UPDATE alert_reviews SET operator_id=NULL WHERE alert_id=? AND action='propose'", (aid,)); c2.commit()
try:
    confirm_disposition(c2, aid, org_id=org, operator="Proposer", operator_id=op, agree=True)
    r, n8b = "accepted (proposer confirmed own legacy proposal)", True
except ReviewError as e:
    r, n8b = f"refused: {e}", False
print(f"N8b   propose by op {op}; proposal operator_id set NULL; confirm by op {op} -> {r} -> reproduces={n8b}")
hits += n8b

# N3b (informational)
import test_matching as tm
s = dbm.connect(":memory:")
ds = dbm.upsert_dataset(s, "test_list", "Synthetic", is_mandatory=True)
for sid, schema, caption, aliases, country, dob, gender in tm.WATCHLIST:
    eid = s.execute("INSERT INTO entities (dataset_id,source_id,schema_type,caption,countries,birth_date,gender,topics,raw,first_seen,last_seen)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?)", (ds, sid, schema, caption, f'["{country}"]', dob, gender, '["sanction"]', "{}", now, now)).lastrowid
    for i, nm in enumerate([caption, *aliases]):
        s.execute("INSERT INTO entity_names (entity_id,name,name_type,canonical_key,script) VALUES (?,?,?,?,?)",
                  (eid, nm, "primary" if i == 0 else "alias", canonical_key(nm), "arabic" if i else "latin"))
        for t in blocking_keys(nm):
            s.execute("INSERT OR IGNORE INTO name_tokens (token,entity_id) VALUES (?,?)", (t, eid))
s.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)", (now,)); s.commit()
for label, q in (("red-team probe: Cyrillic Ve for W", "BILAL ALI AL-ВAFI"),
                 ("Latin control:   AL-BAFI       ", "BILAL ALI AL-BAFI"),
                 ("true homoglyph:  Cyrillic Ve for B", "ВILAL ALI AL-WAFI"),
                 ("true homoglyph:  Cyrillic a, o   ", "BILаL ALI AL-WAFI")):
    r = screen(s, q, org_id=1, persist=False)
    print(f"N3b   {label} -> {'HIT' if r.hits else 'MISS'} {round(max([h.score for h in r.hits], default=0), 2)}")

# H1 (informational)
from fastapi.testclient import TestClient
from amlkit.api.app import app
with TestClient(app) as tc:
    h = tc.get("/login").headers
print(f"H1    GET /login Referrer-Policy={h.get('referrer-policy')!r} Permissions-Policy={h.get('permissions-policy')!r}")

print(f"{hits}/2 reproduce")
sys.exit(0 if hits == 2 else 1)

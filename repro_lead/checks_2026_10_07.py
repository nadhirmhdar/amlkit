"""Lead 2026-10-07 checks. Local :memory: DB and synthetic list entries only.

Exit 0 when BOTH defects reproduce:
  CS-2 - a confirmed (true_positive) match to an entity that exists only on a
         non-UAE list (here dataset 'eu_sanctions', topics ['sanction'], no
         programmes) creates a freeze obligation. review.py:163 decides
         freeze-worthiness from topics/programmes only, never from the dataset.
         EOCN guidance puts only the UAE Local Terrorist List and the UNSC
         Consolidated List under Cabinet Decision 74/2020.
  M2   - one TOTP code verifies twice (auth.mfa_verify keeps no last-used step).
Exit 1 when either is fixed (re-read the printed lines).
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["AMLKIT_SINGLE_OPERATOR_MODE"] = "1"  # apply the disposition directly

import pyotp
from amlkit import auth
from amlkit.db import connect, upsert_dataset, utcnow
from amlkit.names.arabic import blocking_keys, canonical_key
from amlkit.cases import manager
from amlkit.cases.review import propose_disposition

c = connect(":memory:")
now = utcnow()
c.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)", (now,))
c.execute("INSERT INTO operators (org_id,email,password_hash,name,role,is_active,created_at) "
          "VALUES (1,'m@t','x','Mona','mlro',1,?)", (now,))
op_id = c.execute("SELECT id FROM operators").fetchone()[0]

# A fresh mandatory UAE list with no entries, so onboarding passes the freshness gate.
upsert_dataset(c, "ae_local_terrorists", "UAE Local Terrorist List (synthetic, empty)", is_mandatory=True)
ds = upsert_dataset(c, "eu_sanctions", "EU consolidated (synthetic)", is_mandatory=False)
NAME = "ZORAN SYNTHETIC KOVALENKO"
eid = c.execute("""INSERT INTO entities (dataset_id, source_id, schema_type, caption, countries,
    birth_date, gender, topics, programs, raw, first_seen, last_seen)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
    (ds, "EU-SYN-1", "Person", NAME, '["ru"]', None, "male", '["sanction"]', "[]", "{}", now, now)).lastrowid
c.execute("INSERT INTO entity_names (entity_id,name,name_type,canonical_key,script) VALUES (?,?,?,?,?)",
          (eid, NAME, "primary", canonical_key(NAME), "latin"))
for t in blocking_keys(NAME):
    c.execute("INSERT OR IGNORE INTO name_tokens (token,entity_id) VALUES (?,?)", (t, eid))
c.execute("UPDATE datasets SET last_refresh=?, entity_count=1", (now,))
c.commit()

manager.onboard(c, org_id=1, reference="C-1", full_name=NAME, actor="Mona")
c.commit()
alert = c.execute("SELECT id FROM alerts WHERE org_id=1 AND entity_id=?", (eid,)).fetchone()
cs2 = False
if alert is None:
    print("CS-2 no alert raised for the EU-only entity (check the seed)")
else:
    propose_disposition(c, alert[0], org_id=1, status="true_positive", reason_code="confirmed_match",
                        operator="Mona", operator_id=op_id, narrative="Synthetic confirmed match")
    c.commit()
    rows = [dict(r) for r in c.execute(
        "SELECT id, obligation_type, risk_category, status FROM freeze_obligations WHERE org_id=1")]
    cs2 = bool(rows)
    print(f"CS-2 EU-only sanction hit, true_positive -> freeze_obligations={rows} -> reproduces={cs2}")

secret, _ = auth.mfa_enroll(c, op_id)
code = pyotp.TOTP(secret).now()
first = auth.mfa_verify(c, op_id, code)
second = auth.mfa_verify(c, op_id, code)
m2 = first and second
print(f"M2   same TOTP code: first={first} second={second} -> reproduces={m2}")

sys.exit(0 if (cs2 and m2) else 1)

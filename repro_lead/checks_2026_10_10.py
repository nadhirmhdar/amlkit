"""Lead 2026-10-10 checks. Local temp DBs and synthetic list entries only.

Answers the question the 2026-10-07 lead report owed (L-38 option (a)):
  DUAL - a person listed on BOTH the UN list and OFAC (two `entities` rows,
         one per dataset; the engine never merges across datasets) raises one
         alert per dataset, so a UN-only freeze rule would still see the UN hit.
         Informational: printed, not part of the exit code.

Exit 0 when BOTH defects reproduce:
  DL   - PATCH /compliance/deadlines/{id} with a new due_date returns 200 but
         leaves due_date unchanged (app.py:4509-4512 only updates title).
  DLA  - neither PATCH nor DELETE of a deadline writes an audit row.
Exit 1 when either is fixed (re-read the printed lines).
"""
import os, re, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
tmp = tempfile.mkdtemp()
os.environ["AMLKIT_DB"] = os.path.join(tmp, "web.db")
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = "test-invite"
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)

from amlkit.db import connect, upsert_dataset, utcnow
from amlkit.names.arabic import blocking_keys, canonical_key
from amlkit.match.engine import screen

# ---- DUAL: UN + OFAC listing of the same person --------------------------
c = connect(":memory:")
now = utcnow()
c.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)", (now,))
NAME = "ZORAN SYNTHETIC KOVALENKO"
for key, label in (("un_sc_sanctions", "UN (synthetic)"), ("us_ofac_sdn", "OFAC (synthetic)")):
    ds = upsert_dataset(c, key, label, is_mandatory=True)
    eid = c.execute("""INSERT INTO entities (dataset_id, source_id, schema_type, caption, countries,
        birth_date, gender, topics, programs, raw, first_seen, last_seen)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, f"{key}-1", "Person", NAME, '["ru"]', None, "male", '["sanction"]', "[]", "{}", now, now)).lastrowid
    c.execute("INSERT INTO entity_names (entity_id,name,name_type,canonical_key,script) VALUES (?,?,?,?,?)",
              (eid, NAME, "primary", canonical_key(NAME), "latin"))
    for t in blocking_keys(NAME):
        c.execute("INSERT OR IGNORE INTO name_tokens (token,entity_id) VALUES (?,?)", (t, eid))
c.commit()
res = screen(c, NAME, org_id=1, persist=True, actor="lead")
c.commit()
per_ds = [r[0] for r in c.execute(
    "SELECT d.key FROM alerts a JOIN entities e ON e.id=a.entity_id JOIN datasets d ON d.id=e.dataset_id "
    "WHERE a.org_id=1 ORDER BY d.key")]
print(f"DUAL hits={[h.dataset for h in res.hits]} alerts_by_dataset={per_ds}")

# ---- DL / DLA: compliance deadline PATCH and audit -----------------------
from fastapi.testclient import TestClient
from amlkit.api.app import app
from test_t15_compliance_calendar import _register

web = TestClient(app)
_register(web, "mlro@lead.ae")
web.get("/compliance/calendar")
h = {"X-CSRF-Token": web.cookies.get("amlkit_csrf")}
r = web.post("/compliance/deadlines", json={"title": "Annual EWRA", "due_date": "2026-12-31T00:00:00"}, headers=h)
did = r.json()["id"]
r = web.patch(f"/compliance/deadlines/{did}", json={"due_date": "2027-03-31T00:00:00"}, headers=h)
after = r.json()["due_date"]
dl = r.status_code == 200 and after.startswith("2026-12-31")
print(f"DL   PATCH due_date->2027-03-31: status={r.status_code} stored due_date={after} -> reproduces={dl}")
web.patch(f"/compliance/deadlines/{did}", json={"title": "Renamed"}, headers=h)
rd = web.delete(f"/compliance/deadlines/{did}", headers=h)
db = connect(os.environ["AMLKIT_DB"])
acts = [r[0] for r in db.execute(
    "SELECT action FROM audit_log WHERE action LIKE 'compliance.deadline%' ORDER BY id")]
dla = rd.status_code == 204 and acts == ["compliance.deadline_created"]
print(f"DLA  delete status={rd.status_code}; deadline audit actions={acts} -> reproduces={dla}")

sys.exit(0 if (dl and dla) else 1)

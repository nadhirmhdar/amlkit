"""Lead probe 2026-11-19 (CS-27b): does a match dropped by the pre-#464 scorer
surface as an alert when the post-#464 code re-screens the same database?

Two phases, run with different code trees on the same DB file:
  PYTHONPATH=<old 9219e26 tree> python repro_lead/probe_lookback_rescreen_2026_11_19.py onboard <db>
  PYTHONPATH=.                  python repro_lead/probe_lookback_rescreen_2026_11_19.py rescreen <db>
The seeded listed person carries the country as a NAME ('Libya'), as the UN/OFAC/
EU/UK adapters store it; the customer has the ISO code 'LY', exact name, same DOB.
'onboard' exits 0 when no alert is raised (old defect present).
'rescreen' exits 0 when rescreen_all raises the alert (look-back works).
"""
import json, os, sys
from pathlib import Path
# test_api re-inserts ITS OWN repo root, so load tests/ from the tree under test
import amlkit as _a
_root = Path(_a.__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "tests"))
from test_api import LISTED, _seed_sanctions_data
from amlkit import db as amldb
from amlkit.cases import manager
from amlkit.match import engine

mode, d = sys.argv[1], Path(sys.argv[2])
import amlkit as _b
assert Path(_b.__file__).resolve().parent.parent == _root, "wrong amlkit tree loaded"
print("code tree:", _root)
if mode == "onboard":
    _seed_sanctions_data(d); amldb._reset_init_cache()
    c = amldb.connect(d)
    c.execute("UPDATE entities SET countries=?", (json.dumps(["Libya"]),))
    c.execute("INSERT INTO organizations (name, slug, created_at) VALUES ('o','o','2026-01-01')")
    oid = c.execute("SELECT max(id) FROM organizations").fetchone()[0]; c.commit()
    manager.onboard(c, org_id=oid, reference="R", full_name=LISTED, nationality="LY",
                    birth_date="1975-03-12", actor="t")
    n = c.execute("SELECT count(*) FROM alerts").fetchone()[0]
    print(f"onboard: alerts={n}")
    sys.exit(0 if n == 0 else 1)
else:
    c = amldb.connect(d)
    oid = c.execute("SELECT max(id) FROM organizations").fetchone()[0]
    r = engine.rescreen_all(c, oid, actor="t"); c.commit()
    rows = c.execute("SELECT score, status FROM alerts").fetchall()
    print(f"rescreen_all: {r.get('alerts')} new; alerts={[tuple(x) for x in rows]}")
    sys.exit(0 if rows else 1)

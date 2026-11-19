"""Lead probe 2026-11-19 (L-164): rescreen_all screens a customer with only the
primary `nationality`, not `nationalities`, while onboarding uses all of them
(engine.py rescreen_all SELECT/screen(country=row["nationality"]) vs
manager.onboard screen(countries=all_nats)).

Dual national IN+PK, exact name and DOB of a listed person whose country is
'Pakistan'. Onboarding alerts; after the alert is cleared from the scratch DB,
the list-update re-screen of the same customer does not.
Exit 0 when the difference reproduces. Run: PYTHONPATH=. python <this file>
"""
import json, sys, tempfile
from pathlib import Path
import amlkit as _a
sys.path.insert(0, str(Path(_a.__file__).resolve().parent.parent / "tests"))
from test_api import LISTED, _seed_sanctions_data
from amlkit import db as amldb
from amlkit.cases import manager
from amlkit.match import engine

d = Path(tempfile.mkdtemp()) / "x.db"
_seed_sanctions_data(d); amldb._reset_init_cache()
c = amldb.connect(d)
c.execute("UPDATE entities SET countries=?", (json.dumps(["Pakistan"]),))
c.execute("INSERT INTO organizations (name, slug, created_at) VALUES ('o','o','2026-01-01')")
oid = c.execute("SELECT max(id) FROM organizations").fetchone()[0]; c.commit()
manager.onboard(c, org_id=oid, reference="R", full_name=LISTED, nationality="IN",
                nationalities=["IN", "PK"], birth_date="1975-03-12", actor="t")
on = c.execute("SELECT score FROM alerts").fetchall()
print("onboard (IN+PK):", [r[0] for r in on])
# Simulate a listing that first appears at a later refresh: no prior alert.
c.execute("PRAGMA foreign_keys=OFF")
try:
    c.execute("DELETE FROM alerts"); c.commit()
except Exception as e:  # append-only trigger: fall back to a fresh org/customer copy
    print("cannot delete alerts:", e); sys.exit(2)
r = engine.rescreen_all(c, oid, actor="t"); c.commit()
re = c.execute("SELECT score FROM alerts").fetchall()
print("rescreen_all result:", r, "alerts:", [x[0] for x in re])
rep = bool(on) and not re
print("L164 reproduces=%s" % rep)
sys.exit(0 if rep else 1)

"""Lead probe 2026-11-18 (DOB1): end-to-end onboard() of an exact-name customer
against the seeded listed person (DOB 1975-03-12, LY), one fresh scratch DB per
row. Exit 0 when the inversion reproduces (one-day DOB difference -> no alert,
six-year difference -> alert). Run: PYTHONPATH=. python repro_lead/probe_dob_onboard_2026_11_18.py
"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, "."); sys.path.insert(0, "tests")
from test_api import LISTED, _seed_sanctions_data
from amlkit import db as amldb
from amlkit.cases import manager
res = {}
for dob, nat in [("1975-03-13","LY"),("1975-03-12","LY"),("1981-01-02","LY"),("1975-03-12","IN"),(None,"LY"),(None,None),("1975-12-31","LY"),("1976-03-12","LY")]:
    d = Path(tempfile.mkdtemp())/"x.db"; _seed_sanctions_data(d); amldb._reset_init_cache()
    c = amldb.connect(d)
    c.execute("INSERT INTO organizations (name, slug, created_at) VALUES ('o','o','2026-01-01')"); oid=c.execute("SELECT max(id) FROM organizations").fetchone()[0]; c.commit()
    manager.onboard(c, org_id=oid, reference="R", full_name=LISTED, nationality=nat, birth_date=dob, actor="t")
    row = c.execute("SELECT a.score, a.score_detail FROM alerts a").fetchone()
    sc = c.execute("SELECT score, score_detail FROM screening_results").fetchall() if c.execute("SELECT name FROM sqlite_master WHERE name='screening_results'").fetchone() else None
    print(dob, nat, "alert" if row else "NO ALERT", row[0] if row else ""); res[(dob, nat)] = bool(row)
sys.exit(0 if (not res[("1975-03-13","LY")] and res[("1981-01-02","LY")]) else 1)

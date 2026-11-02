"""Skeptic repro: an empty or blank name screens CLEAN (not 'unscreenable'), so a nameless customer created through
the mobile API (full_name has no minimum length) is recorded as screened clear. Scratch :memory: DB.
Exit 0 only if the empty and blank names both come back clear and not unscreenable."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(sys.path[0], "tests"))
from amlkit import db
from amlkit.match.engine import screen
from test_p43_alerts_group_dismiss import _seed
c = db.connect(":memory:"); s = _seed(c); org = s["org_id"]
bad = 0
for label, name in (("empty", ""), ("blank", "   ")):
    r = screen(c, name, org_id=org, persist=False)
    print(f"{label:6s} -> clear={r.clear} unscreenable={r.unscreenable} candidates={r.candidates} hits={len(r.hits)}")
    bad += int(r.clear and not r.unscreenable)
sys.exit(0 if bad == 2 else 1)

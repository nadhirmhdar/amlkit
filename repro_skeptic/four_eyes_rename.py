"""Skeptic repro: four-eyes identity is a name string, so a rename defeats it.
Exit 0 only if the defect reproduces. Local scratch DB only (:memory:)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(sys.path[0], "tests"))
from amlkit import db
from amlkit.cases.review import propose_disposition, confirm_disposition, ReviewError
from amlkit.cases.operators import rename_operator
from test_p43_alerts_group_dismiss import _seed

c = db.connect(":memory:")
s = _seed(c)
org, alert = s["org_id"], s["alert_ids"][0]
op_id = c.execute("SELECT id FROM operators WHERE org_id=?", (org,)).fetchone()[0]
c.execute("UPDATE operators SET name='Proposer' WHERE id=?", (op_id,)); c.commit()
out = propose_disposition(c, alert, org_id=org, status="false_positive",
                          reason_code="name_coincidence", narrative="different person", operator="Proposer")
print("propose ->", out)
try:
    confirm_disposition(c, alert, org_id=org, operator="Proposer", agree=True)
    print("self-confirm unexpectedly allowed"); sys.exit(1)
except ReviewError as e:
    print("self-confirm refused:", str(e)[:60])
rename_operator(c, op_id, org, "Proposer Renamed", actor="Proposer"); c.commit()
r = confirm_disposition(c, alert, org_id=org, operator="Proposer Renamed", agree=True)
st = c.execute("SELECT status FROM alerts WHERE id=?", (alert,)).fetchone()[0]
print("confirm after rename ->", r, "| alert status:", st)
print("same operator_id proposed and confirmed; alert_reviews stores only names:",
      [tuple(x) for x in c.execute("SELECT action, operator FROM alert_reviews ORDER BY id")])
sys.exit(0 if st == "false_positive" else 1)

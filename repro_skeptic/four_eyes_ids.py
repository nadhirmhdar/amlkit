"""Skeptic repro for #426: id-anchored four-eyes check. Scratch :memory: DB.
Prints three cases. Exit 0 only if the LEGACY case (proposal stored without operator_id) is still bypassable by rename,
i.e. the residual hazard is real; the live-path case (both sides carry ids) must be refused or the script exits 2."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(sys.path[0], "tests"))
from amlkit import db
from amlkit.cases.review import propose_disposition, confirm_disposition, ReviewError
from amlkit.cases.operators import rename_operator
from test_p43_alerts_group_dismiss import _seed

def fresh():
    c = db.connect(":memory:"); s = _seed(c); org, alerts = s["org_id"], s["alert_ids"]
    op = c.execute("SELECT id FROM operators WHERE org_id=?", (org,)).fetchone()[0]
    c.execute("UPDATE operators SET name='Proposer' WHERE id=?", (op,)); c.commit()
    return c, org, alerts, op

def attempt(label, propose_kw, confirm_kw):
    c, org, alerts, op = fresh()
    a = alerts[0]
    propose_disposition(c, a, org_id=org, status="false_positive", reason_code="name_coincidence",
                        narrative="x", operator="Proposer", **propose_kw(op))
    if "legacy" in label:   # simulate a proposal staged before the operator_id column existed
        c.execute("UPDATE alert_reviews SET operator_id=NULL"); c.commit()
    rename_operator(c, op, org, "Proposer Renamed", actor="Proposer"); c.commit()
    try:
        confirm_disposition(c, a, org_id=org, operator="Proposer Renamed", agree=True, **confirm_kw(op))
        res = "ACCEPTED"
    except ReviewError:
        res = "refused"
    print(f"{label:55s} -> {res}")
    return res

live = attempt("live path (ids on both sides)", lambda op: {"operator_id": op}, lambda op: {"operator_id": op})
legacy = attempt("legacy proposal (id NULL) + id on confirm", lambda op: {"operator_id": op}, lambda op: {"operator_id": op}) if False else attempt("legacy proposal (id NULL) + id on confirm [legacy]", lambda op: {"operator_id": op}, lambda op: {"operator_id": op})
omit = attempt("proposal has id, confirm call omits id", lambda op: {"operator_id": op}, lambda op: {})
if live != "refused": sys.exit(2)
sys.exit(0 if (legacy == "ACCEPTED" and omit == "ACCEPTED") else 1)

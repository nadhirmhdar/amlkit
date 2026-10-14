"""Lead repro, 2026-10-14. Exits 0 when every defect below reproduces.

EN  (mlro-user C1, skeptic): onboard() accepts a blank full_name (the web
    form's "   " and the mobile API's "" both reach it as "") and records the
    customer as screened clear, not unscreenable.
SEC (mlro-user C2): an unknown sector is stored and scores the default 5
    points; a typo of real_estate (25) silently lowers the risk score, and
    validate_risk_inputs() has no sector entry.

Scratch :memory: DB, no network.
Run from the repo root: PYTHONPATH=.:tests python repro_lead/checks_2026_10_14.py
"""
import sys

from amlkit import db
from amlkit.cases.manager import onboard
from amlkit.risk.model import validate_risk_inputs
from test_p43_alerts_group_dismiss import _seed

conn = db.connect(":memory:")
org = _seed(conn)["org_id"]
ok = 0

r = onboard(conn, org_id=org, reference="EN-1", full_name="   ".strip(), actor="lead")
row = conn.execute("SELECT full_name FROM customers WHERE id=?", (r.customer_id,)).fetchone()
s = r.screening
en = row[0] == "" and s.clear and not s.unscreenable
print(f"EN   blank full_name onboarded id={r.customer_id} stored={row[0]!r} "
      f"clear={s.clear} unscreenable={s.unscreenable} rating={r.risk.rating} -> reproduces={en}")
ok += en

good = onboard(conn, org_id=org, reference="SEC-1", full_name="Sector Good",
               sector="real_estate", actor="lead")
typo = onboard(conn, org_id=org, reference="SEC-2", full_name="Sector Typo",
               sector="realestate", actor="lead")
stored = conn.execute("SELECT sector FROM customers WHERE id=?", (typo.customer_id,)).fetchone()[0]
try:
    validate_risk_inputs(sector="realestate")  # type: ignore[call-arg]
    rejects = True
except TypeError:
    rejects = False  # no sector parameter at all
except ValueError:
    rejects = True
sec = (stored == "realestate" and typo.risk.score < good.risk.score and not rejects)
print(f"SEC  sector real_estate score={good.risk.score} vs 'realestate' score={typo.risk.score} "
      f"stored={stored!r} validator_checks_sector={rejects} -> reproduces={sec}")
ok += sec

print(f"exit={0 if ok == 2 else 1}")
sys.exit(0 if ok == 2 else 1)

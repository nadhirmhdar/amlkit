"""Lead checks for 2026-11-18 (master 9219e26). Local scratch DB only, no network.

Counts as reproducing (exit 0 if any reproduce, 1 if none):
  EX1   a customer onboarded with DOB 1981-01-02 / nationality IN raises an
        alert against the seeded listed person (DOB 1975-03-12, LY); /alerts
        and the alert panel show the listed DOB but never the customer's own
        DOB or nationality.
  EX3   the alert panel (/alerts/{id}/panel) omits facts the queue row shows:
        the listed person's DOB and the reason/explanation text.
  GV1   cases.diagram.generate_ubo_diagram with a stub `dot` that sleeps 6 s
        blocks for the full 6 s (no timeout on dot.pipe()).

  DOB1  (new, lead) scorer penalty inversion: an exact-name customer whose DOB
        differs from the listed DOB by one day, or by a DD/MM swap, in the
        same year gets dob_day_mismatch -0.25 -> score 0.75, NO alert; a DOB
        six years away gets dob_year_mismatch -0.15 -> 0.85, alert
        (match/scorer.py:29-30, 272-277, elif at :275).

Printed, not counted:
  EX2   whether the queue row shows "recall"/"precision" (_macros.html:21-22).

Run from the repo root:  PYTHONPATH=. python repro_lead/checks_2026_11_18.py
"""
from __future__ import annotations

import os
import re
import stat
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

tmp = Path(tempfile.mkdtemp(prefix="lead1118_"))
os.environ["AMLKIT_DB"] = str(tmp / "lead.db")
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)
os.environ.pop("AMLKIT_SMTP_HOST", None)
os.environ.pop("STRIPE_SECRET_KEY", None)
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = "test-invite"

from test_api import LISTED, _register, _seed_sanctions_data  # noqa: E402

_seed_sanctions_data(Path(os.environ["AMLKIT_DB"]))
from fastapi.testclient import TestClient  # noqa: E402
from amlkit import db as amldb  # noqa: E402
from amlkit.api.app import app, limiter  # noqa: E402
from amlkit.cases import diagram, manager  # noqa: E402

limiter.enabled = False
results: dict[str, bool] = {}

w = _register(TestClient(app), "Lead Explain Firm", "Explain Mlro", "mlro@leadex.ae")
conn = amldb.connect(os.environ["AMLKIT_DB"])
oid = conn.execute("SELECT org_id FROM operators WHERE email='mlro@leadex.ae'").fetchone()[0]
LIST_DOB = "1975-03-12"
# A full DOB + nationality mismatch raises no alert (mlro-user's observation,
# reproduced here as variant 1), so try progressively closer customers and use
# the first that alerts. Each customer's DOB differs from the listed DOB, so
# the customer's own DOB is a unique marker on the page.
cid = aid = CUST_DOB = None
for i, (dob, nat) in enumerate([("1981-01-02", "IN"), ("1981-01-02", "LY"),
                                ("1975-03-13", "LY")]):
    cust = manager.onboard(conn, org_id=oid, reference=f"EX-{i}", full_name=LISTED,
                           nationality=nat, birth_date=dob, actor="lead")
    c_id = conn.execute("SELECT id FROM customers WHERE org_id=? AND reference=?",
                        (oid, f"EX-{i}")).fetchone()[0]
    a = conn.execute(
        "SELECT a.id FROM alerts a JOIN screenings s ON s.id=a.screening_id"
        " WHERE s.customer_id=? ORDER BY a.id LIMIT 1", (c_id,)).fetchone()
    print(f"setup variant {i}: customer DOB={dob} nat={nat} -> alert={a[0] if a else None}")
    if a and aid is None:
        cid, aid, CUST_DOB = c_id, a, dob
    if cid is None:
        cid = c_id

if aid:
    aid = aid[0]
    page = w.get("/alerts").text
    panel = w.get(f"/alerts/{aid}/panel")
    ptxt = panel.text
    print(f"EX1   /alerts listed DOB shown={LIST_DOB in page} customer DOB shown={CUST_DOB in page}"
          f" customer nationality 'IN' token shown={bool(re.search(r'[^A-Z]IN[^A-Z]', page))}")
    print(f"EX1   panel status={panel.status_code} listed DOB={LIST_DOB in ptxt} customer DOB={CUST_DOB in ptxt}")
    results["EX1"] = LIST_DOB in page and CUST_DOB not in page and CUST_DOB not in ptxt
    reason_in_page = bool(re.search(r"Matched tokens|canonical match|recall", page))
    reason_in_panel = bool(re.search(r"Matched tokens|canonical match|recall", ptxt))
    print(f"EX3   queue row: DOB={LIST_DOB in page} reason={reason_in_page};"
          f" panel: DOB={LIST_DOB in ptxt} reason={reason_in_panel}")
    results["EX3"] = (LIST_DOB in page and LIST_DOB not in ptxt) or (reason_in_page and not reason_in_panel)
    print(f"EX2   queue shows 'precision'={'precision' in page} 'recall'={'recall' in page} (not counted)")
else:
    print("EX1/EX3 could not run: no alert raised for the mismatched-DOB customer")
    results["EX1"] = results["EX3"] = False

# DOB1: score the listed name against itself with different customer DOBs
from amlkit.match import scorer  # noqa: E402
import inspect  # noqa: E402
params = inspect.signature(scorer.score_entity).parameters
def _s(dob):
    r = scorer.score_entity(LISTED, [LISTED], query_birth_date=dob, cand_birth_date=LIST_DOB)
    return round(r.score, 3), r.features.get("adjustments", {})
try:
    one_day, swap, six_y = _s("1975-03-13"), _s("1975-12-03"), _s("1981-03-12")
    print(f"DOB1  scorer: +1 day={one_day}  DD/MM swap={swap}  6 years={six_y}  threshold=0.85")
    results["DOB1"] = one_day[0] < 0.85 <= six_y[0] and swap[0] < 0.85
except TypeError as e:
    print("DOB1  scorer signature differs:", e, list(params))
    results["DOB1"] = False

# GV1: stub dot that hangs
bindir = tmp / "bin"
bindir.mkdir()
stub = bindir / "dot"
stub.write_text("#!/bin/sh\nsleep 6\n")
stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
old = os.environ["PATH"]
os.environ["PATH"] = f"{bindir}:{old}"
t0 = time.monotonic()
out = diagram.generate_ubo_diagram(conn, cid, oid)
dt = time.monotonic() - t0
os.environ["PATH"] = old
print(f"GV1   hung dot stub: generate_ubo_diagram returned {'None' if out is None else 'svg'} after {dt:.1f}s")
results["GV1"] = dt >= 5.5
conn.close()

n = sum(results.values())
for k, v in results.items():
    print(f"{k:5} reproduces={v}")
print(f"{n}/{len(results)} reproduce")
sys.exit(0 if n else 1)

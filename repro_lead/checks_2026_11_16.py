"""Lead checks for 2026-11-16 (master 9219e26). Local scratch DB only, no network.

Counts as reproducing (exit 0 if any reproduce, 1 if none):
  CL1  close_relationship() accepts a customer with an OPEN sanctions alert
       (from a real onboard() match against the seeded test list), and a
       customer whose freeze obligation is executed but not reported
       (status executed_pending_report; inserted by SQL to skip the UI walk).
  CL2  after closure the sanctions alert is still status='open'.
  TD1  three cash transactions of AED 54,999 within the window raise a
       'structuring' flag when direction is 'in','in','in' but none when it
       is 'in','IN',' in' (direction stored verbatim, grouped by exact string).
  TX1  a USD 100,000 cash transaction recorded with amount_aed=1 is accepted
       and raises no flag (no plausibility check of the operator-typed AED).
  TX2  currency 'XXX' is accepted.
  N3c  canonical_key of 'عبدالله' with Urdu heh U+06C1 differs from the
       standard spelling, and 'خالد بن هاشم القحطاني' with one Urdu heh scores
       below 0.85 against its Latin listing (red-team's case).

Run from the repo root:  PYTHONPATH=. python repro_lead/checks_2026_11_16.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

tmp = Path(tempfile.mkdtemp(prefix="lead1116_"))
os.environ["AMLKIT_DB"] = str(tmp / "lead.db")
os.environ.pop("STRIPE_SECRET_KEY", None)

from test_api import LISTED, _seed_sanctions_data  # noqa: E402
from conftest import seed_org  # noqa: E402

from amlkit import db as amldb  # noqa: E402
from amlkit.cases import manager  # noqa: E402
from amlkit.match.scorer import name_score  # noqa: E402
from amlkit.names.arabic import canonical_key  # noqa: E402

_seed_sanctions_data(Path(os.environ["AMLKIT_DB"]))
conn = amldb.connect(os.environ["AMLKIT_DB"])
org = seed_org.__wrapped__(conn)
conn.commit()
OID = org["org_id"]
results: dict[str, bool] = {}

# ---- CL1 / CL2: close with open sanctions alert ---------------------------
r = manager.onboard(conn, org_id=OID, reference="CL-1", full_name=LISTED,
                    nationality="LY", actor="lead")
cid = r.customer_id
open_alerts = conn.execute(
    "SELECT a.id FROM alerts a JOIN screenings s ON s.id=a.screening_id"
    " WHERE s.customer_id=? AND a.org_id=? AND a.status='open'", (cid, OID)).fetchall()
closed_with_alert = False
if open_alerts:
    try:
        manager.close_relationship(conn, cid, OID, "customer_request", actor="lead")
        closed_with_alert = conn.execute(
            "SELECT status FROM customers WHERE id=?", (cid,)).fetchone()[0] == "closed"
    except ValueError as e:
        print("CL1a refused:", e)
still_open = conn.execute(
    "SELECT COUNT(*) FROM alerts WHERE id=? AND status='open'",
    (open_alerts[0]["id"],)).fetchone()[0] if open_alerts else 0

# executed-but-unreported freeze
r2 = manager.onboard(conn, org_id=OID, reference="CL-2", full_name="Plain Customer Two",
                     nationality="AE", actor="lead")
now = amldb.utcnow()
with conn:
    conn.execute(
        "INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,"
        " identified_at, identified_by, executed_at, executed_by, status)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (OID, r2.customer_id, "sanctions", "critical", now, "lead", now, "lead",
         "executed_pending_report"))
closed_with_freeze = False
try:
    manager.close_relationship(conn, r2.customer_id, OID, "customer_request", actor="lead")
    closed_with_freeze = True
except ValueError as e:
    print("CL1b refused:", e)
print(f"CL1  open sanctions alerts={len(open_alerts)} closed_with_open_alert={closed_with_alert};"
      f" closed_with_executed_unreported_freeze={closed_with_freeze}")
results["CL1"] = closed_with_alert or closed_with_freeze
print(f"CL2  alert still open after closure={bool(still_open)}")
results["CL2"] = bool(still_open)


# ---- TD1: direction spelling splits structuring ---------------------------
def structuring_for(directions: list[str], ref: str) -> bool:
    c = manager.onboard(conn, org_id=OID, reference=ref, full_name=f"Cash Customer {ref}",
                        nationality="AE", actor="lead").customer_id
    base = datetime.now(timezone.utc) - timedelta(days=2)
    flags_all: list = []
    for i, d in enumerate(directions):
        _, flags = manager.record_transaction(
            conn, c, OID, direction=d, method="cash", amount=54999.0,
            occurred_at=(base + timedelta(hours=i)).isoformat(), actor="lead")
        flags_all.extend(flags)
    names = [getattr(f, "rule", None) or (f.get("rule") if isinstance(f, dict) else str(f))
             for f in flags_all]
    return any("structuring" in str(n) for n in names)


same = structuring_for(["in", "in", "in"], "TD-A")
split = structuring_for(["in", "IN", " in"], "TD-B")
print(f"TD1  structuring with in/in/in={same}; with in/IN/' in'={split}")
results["TD1"] = same and not split

# ---- TX1 / TX2 --------------------------------------------------------------
c3 = manager.onboard(conn, org_id=OID, reference="TX-1", full_name="Fx Customer",
                     nationality="AE", actor="lead").customer_id
try:
    _, f1 = manager.record_transaction(conn, c3, OID, direction="in", method="cash",
                                       amount=100000.0, currency="USD", amount_aed=1.0,
                                       actor="lead")
    tx1 = len(f1) == 0
    print(f"TX1  USD 100,000 cash recorded as AED 1 accepted; flags={len(f1)}")
except ValueError as e:
    tx1 = False
    print("TX1  refused:", e)
results["TX1"] = tx1
try:
    manager.record_transaction(conn, c3, OID, direction="in", method="wire",
                               amount=10.0, currency="XXX", amount_aed=10.0, actor="lead")
    cur = conn.execute("SELECT currency FROM transactions WHERE customer_id=?"
                       " ORDER BY id DESC LIMIT 1", (c3,)).fetchone()[0]
    print(f"TX2  currency 'XXX' accepted, stored as {cur!r}")
    results["TX2"] = True
except ValueError as e:
    print("TX2  refused:", e)
    results["TX2"] = False

# ---- N3c: Urdu heh ----------------------------------------------------------
# Core case (skeptic): the key changes but the fuzzy score still alerts.
std = "عبدالله"
urdu = std.replace("ه", "\u06c1")
k_std, k_urdu = canonical_key(std), canonical_key(urdu)
s_std, _ = name_score(std, "Abdullah")
s_urdu, _ = name_score(urdu, "Abdullah")
print(f"N3c  canonical_key std={k_std!r} urdu_heh={k_urdu!r};"
      f" name_score vs 'Abdullah' std={s_std:.2f} urdu_heh={s_urdu:.2f} (still >=0.85)")
# Red-team case: one Urdu heh in a full name drops below the threshold.
base = "خالد بن هاشم القحطاني"
listed = ["Khalid bin Hashim Al Qahtani", "Khaled Hashem al-Qahtani"]
b_sc = max(name_score(base, x)[0] for x in listed)
v_sc = max(name_score(base.replace("ه", "\u06c1", 1), x)[0] for x in listed)
print(f"N3c  {base!r} vs Latin listing: standard={b_sc:.2f} urdu_heh={v_sc:.2f}")
results["N3c"] = k_std != k_urdu and v_sc < 0.85

conn.close()
n = sum(results.values())
for k, v in results.items():
    print(f"{k:5s} reproduces={v}")
print(f"{n}/{len(results)} reproduce")
sys.exit(0 if n else 1)

"""Lead repro, 2026-10-12. Exits 0 when the defect reproduces.

TA1 (mlro-user): a cash transaction alert can be closed as false_positive
with an empty note; the stored disposition is NULL and the audit row's
note is ''. Local scratch DB only, no network.

Run from the repo root: PYTHONPATH=. python repro_lead/checks_2026_10_12.py
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

from amlkit.db import connect, utcnow
from amlkit.cases.manager import (
    disposition_transaction_alert, record_transaction,
)

tmp = Path(tempfile.mkdtemp()) / "ta1.db"
conn = connect(str(tmp))
conn.row_factory = sqlite3.Row
with conn:
    org_id = conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES ('Org TA', 'org-ta', ?)",
        (utcnow(),),
    ).lastrowid
    # Direct insert: onboard() refuses without a fresh sanctions dataset and
    # this check needs no screening.
    now = utcnow()
    cid = conn.execute(
        "INSERT INTO customers (org_id, reference, customer_type, full_name, canonical_key,"
        " onboarded_at, created_at, updated_at) VALUES (?, 'TA-1', 'natural',"
        " 'Test Cash Customer', 'test cash customer', ?, ?, ?)",
        (org_id, now, now, now),
    ).lastrowid
_, triggered = record_transaction(
    conn, cid, org_id, direction="in", method="cash", amount=60000, currency="AED",
)
alert = conn.execute(
    "SELECT id, rule_key FROM transaction_alerts WHERE org_id=? ORDER BY id", (org_id,)
).fetchone()
if alert is None:
    print(f"TA1  no alert raised (triggered={triggered}) -> cannot test")
    sys.exit(2)
disposition_transaction_alert(conn, alert["id"], org_id, status="false_positive",
                              note="   ", actor="Alice Officer")
row = conn.execute(
    "SELECT status, disposition FROM transaction_alerts WHERE id=?", (alert["id"],)
).fetchone()
reproduces = row["status"] == "false_positive" and row["disposition"] is None
print(f"TA1  {alert['rule_key']} alert closed with blank note -> status={row['status']} "
      f"disposition={row['disposition']!r} -> reproduces={reproduces}")
sys.exit(0 if reproduces else 1)

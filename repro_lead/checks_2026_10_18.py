"""Lead repro, 2026-10-18. Exits 0 when every defect below reproduces.

Owed by the 10-17 lead report:
  RV  - L-70 incidental reset: a customer overdue for periodic review
        (due_for_review lists them) drops off the list after an unrelated
        cash transaction raises an alert, because record_transaction ->
        reassess_transaction_risk -> assess() writes a fresh next_review.
        No review was done.
  EV  - auth.consume_email_verify_token: same check-then-act shape as
        L-66/L-69 (SELECT used_at, then unconditional UPDATE ... WHERE id=?).
        5 threads redeem one token concurrently: more than one succeeds.
  US  - auth.consume_uaepass_state: same shape for the OAuth state row.

Local scratch DB only, no network. Run from the repo root:
  PYTHONPATH=. python repro_lead/checks_2026_10_18.py
"""
import json, os, sqlite3, sys, tempfile, threading
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import logging; logging.disable(logging.CRITICAL)

from amlkit import auth, db as dbm
from amlkit.db import utcnow
from amlkit.cases.manager import due_for_review, record_transaction

DBP = os.path.join(tempfile.mkdtemp(), "lead18.db")
w = dbm.connect(DBP)
w.row_factory = sqlite3.Row
now = utcnow()
with w:
    org_id = w.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES ('Org RV', 'org-rv', ?)", (now,)
    ).lastrowid
    cid = w.execute(
        "INSERT INTO customers (org_id, reference, customer_type, full_name, canonical_key,"
        " onboarded_at, created_at, updated_at) VALUES (?, 'RV-1', 'natural',"
        " 'Overdue Review Customer', 'overdue review customer', ?, ?, ?)",
        (org_id, now, now, now),
    ).lastrowid
    w.execute(
        "INSERT INTO risk_assessments (org_id, customer_id, score, rating, factors,"
        " ruleset_version, requires_edd, assessed_at, next_review)"
        " VALUES (?, ?, 10, 'low', ?, 'test', 0, '2025-01-01T00:00:00+00:00', '2026-01-01')",
        (org_id, cid, json.dumps({})),
    )
ok = 0

before = [r["id"] for r in due_for_review(w, org_id)]
record_transaction(w, cid, org_id, direction="in", method="cash", amount=60000, currency="AED")
w.commit()
after = [r["id"] for r in due_for_review(w, org_id)]
nr = w.execute(
    "SELECT next_review FROM risk_assessments WHERE customer_id=? ORDER BY id DESC LIMIT 1", (cid,)
).fetchone()["next_review"]
today = datetime.now(timezone.utc).date().isoformat()
rv = cid in before and cid not in after and nr > today
print(f"RV  overdue before={cid in before}; after one cash txn alert: overdue={cid in after}, "
      f"next_review={nr}, review recorded=False -> reproduces={rv}")
ok += rv

op_id = w.execute(
    "INSERT INTO operators (org_id, name, email, role, password_hash, created_at)"
    " VALUES (?, 'Eve Verify', 'eve@t.test', 'analyst', 'x', ?)", (org_id, now)
).lastrowid
w.commit()


def race(fn, n=5):
    res, barrier = [], threading.Barrier(n)

    def run():
        k = dbm.connect(DBP)
        k.row_factory = sqlite3.Row
        barrier.wait()
        try:
            res.append(fn(k) is not None)
        except sqlite3.OperationalError as e:
            res.append(f"err:{e}")
        finally:
            k.close()
    th = [threading.Thread(target=run) for _ in range(n)]
    [t.start() for t in th]; [t.join() for t in th]
    return res


ev_hits = []
for _ in range(5):
    raw = auth.create_email_verify_token(w, op_id); w.commit()
    ev_hits.append(race(lambda k: auth.consume_email_verify_token(k, raw)).count(True))
ev = max(ev_hits) > 1
print(f"EV  one email-verify token, 5 concurrent redeems x5 rounds: successes per round={ev_hits} -> reproduces={ev}")
ok += ev

us_hits = []
for _ in range(5):
    st = auth.create_uaepass_state(w, purpose="operator_sso", redirect_uri="http://localhost/cb")
    us_hits.append(race(lambda k: auth.consume_uaepass_state(k, st, purpose="operator_sso")).count(True))
us = max(us_hits) > 1
print(f"US  one UAE PASS state, 5 concurrent consumes x5 rounds: successes per round={us_hits} -> reproduces={us}")
ok += us

print(f"exit={0 if ok == 3 else 1}")
sys.exit(0 if ok == 3 else 1)

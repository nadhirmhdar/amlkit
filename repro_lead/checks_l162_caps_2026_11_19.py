"""Lead checks 2026-11-19 (owed L-162): 200-row caps with no paging or notice
outside the screening-alert queue (L-156). Real SQLite, seeded directly.

  T1  queries.transaction_alert_queue (mobile /api/v1/transaction-alerts, web
      queue) returns 200 of 250 open transaction alerts
  T2  queries.dashboard 'oldest_open_transaction_alerts' is taken from that
      newest-first, capped list, so the five shown are NOT the five oldest
  A1  queries.adverse_media_queue (mobile /api/v1/adverse-media) returns 200 of 250
  X1  queries.transactions_for_customer (case file + mobile customer
      transactions) returns 200 of 250 transactions
Exit 0 while any reproduces. Run: PYTHONPATH=. python <this file>
"""
import sys, tempfile
from pathlib import Path
from amlkit import db as amldb, queries

N = 250
import amlkit as _a
sys.path.insert(0, str(Path(_a.__file__).resolve().parent.parent / "tests"))
from test_api import _seed_sanctions_data
d = Path(tempfile.mkdtemp()) / "x.db"
_seed_sanctions_data(d); amldb._reset_init_cache()
c = amldb.connect(d)
c.execute("INSERT INTO organizations (name, slug, created_at) VALUES ('o','o','2026-01-01')")
oid = c.execute("SELECT max(id) FROM organizations").fetchone()[0]
from amlkit.cases import manager
manager.onboard(c, org_id=oid, reference="R1", full_name="Test Customer One", actor="t")
cid = c.execute("SELECT id FROM customers").fetchone()[0]
sid = c.execute(
    "INSERT INTO adverse_media_screenings (org_id, customer_id, query_name, trigger,"
    " window_months, status, articles_considered, findings, severity, run_at)"
    " VALUES (?,?,?,?,?,?,?,?,?,?)",
    (oid, cid, "Test Customer One", "adhoc", 24, "ok", N, N, "reputational_only", "2026-01-01T00:00:00")).lastrowid
for i in range(N):
    ts = f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}T00:00:00"
    tid = c.execute(
        "INSERT INTO transactions (org_id, customer_id, direction, method, amount, amount_aed,"
        " occurred_at, recorded_by, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (oid, cid, "inbound", "cash", 60000, 60000, ts, "t", ts)).lastrowid
    c.execute(
        "INSERT INTO transaction_alerts (org_id, transaction_id, customer_id, rule_key, severity,"
        " detail, created_at) VALUES (?,?,?,?,?,?,?)",
        (oid, tid, cid, "large_cash", "high", "{}", ts))
    c.execute(
        "INSERT INTO adverse_media_findings (org_id, screening_id, customer_id, url, title,"
        " severity, matched_terms, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (oid, sid, cid, f"https://example.test/{i}", f"t{i}", "reputational_only", "[]", ts))
c.commit()

hits = 0
t1 = len(queries.transaction_alert_queue(c, oid, status="open"))
print(f"T1  transaction_alert_queue open: {t1} of {N} (no total/next returned)"); hits += t1 < N
dash = queries.dashboard(c, oid)
shown = [a["created_at"][:10] for a in dash["oldest_open_transaction_alerts"]]
true_oldest = [r[0][:10] for r in c.execute(
    "SELECT created_at FROM transaction_alerts WHERE org_id=? AND status='open'"
    " ORDER BY created_at LIMIT 5", (oid,))]
t2 = shown != true_oldest
print(f"T2  dashboard 'oldest' shown={shown} true oldest={true_oldest}"); hits += t2
a1 = len(queries.adverse_media_queue(c, oid, status="open"))
print(f"A1  adverse_media_queue open: {a1} of {N}"); hits += a1 < N
x1 = len(queries.transactions_for_customer(c, cid, oid))
print(f"X1  transactions_for_customer: {x1} of {N}"); hits += x1 < N
print(f"{hits}/4 reproduce")
sys.exit(0 if hits else 1)

"""Red-team 2026-10-07: cost of the #421 category-first alert_queue (reads every matching alert of the org per call).
LOCAL ONLY (scratch SQLite). Reports seconds per call as the org's open-alert count grows."""
import json, os, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
from amlkit.db import connect, upsert_dataset, utcnow
from amlkit import queries
db = Path(tempfile.mkdtemp())/"s.db"; c = connect(db); now = utcnow()
c.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)", (now,))
ds = upsert_dataset(c, "test_list", "Synthetic", is_mandatory=True)
eid = c.execute("""INSERT INTO entities (dataset_id, source_id, schema_type, caption,countries,birth_date,gender,topics,programs,raw,first_seen,last_seen)
  VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",(ds,"E1","Person","LISTED","[]",None,None,'["sanction"]','["AE-UNSC1373"]',"{}",now,now)).lastrowid
tot = 0
for target in (1_000, 10_000, 50_000):
    n = target - tot
    c.executemany("INSERT INTO customers (org_id,reference,customer_type,full_name,canonical_key,status,onboarded_at,created_at,updated_at) VALUES (1,?, 'natural','X','x','active',?,?,?)",
                  [(f"R{tot+i}", now, now, now) for i in range(n)])
    first_c = c.execute("select min(id) from customers where reference=?", (f"R{tot}",)).fetchone()[0]
    c.executemany("INSERT INTO screenings (org_id,customer_id,query_name,trigger,algorithm,threshold,candidates,hits,datasets_used,run_at) VALUES (1,?,?,?,?,?,?,?,?,?)",
                  [(first_c+i, "X", "onboarding", "t", 0.85, 1, 1, "[]", now) for i in range(n)])
    first_s = c.execute("select max(id) from screenings").fetchone()[0] - n + 1
    c.executemany("INSERT INTO alerts (org_id,screening_id,entity_id,score,score_detail,matched_name,created_at) VALUES (1,?,?,?,?,?,?)",
                  [(first_s+i, eid, 0.9, "{}", "LISTED", now) for i in range(n)])
    c.commit(); tot = target
    for label, fn in [("alert_queue(open, limit=200)", lambda: queries.alert_queue(c, 1, status="open", limit=200)),
                      ("alert_queue(open, offset=tail)", lambda: queries.alert_queue(c, 1, status="open", limit=200, offset=tot-200)),
                      ("dashboard()", lambda: queries.dashboard(c, 1))]:
        t = time.time(); fn(); print(f" open alerts={tot:>6}  {label:34s} {time.time()-t:6.2f}s")

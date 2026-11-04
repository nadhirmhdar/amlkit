"""Red-team 2026-10-07: retention purge (#422): early deletion, tenant scoping, NULL exit_date. LOCAL ONLY (in-memory DB)."""
import os, sys
os.environ["AMLKIT_PURGE_ENABLED"] = "true"
from datetime import date, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
from amlkit.db import connect, utcnow
from amlkit.cases.manager import purge_expired
c = connect(":memory:"); now = utcnow()
for i in (1, 2): c.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES (?,?,?,?)", (f"o{i}", f"o{i}", "active", now))
today = date.today()
def cust(org, ref, exit_date, retention_until, status="closed"):
    return c.execute("""INSERT INTO customers (org_id,reference,customer_type,full_name,canonical_key,status,exit_date,retention_until,onboarded_at,created_at,updated_at)
        VALUES (?,?,'natural','X','x',?,?,?,?,?,?)""", (org, ref, status, exit_date, retention_until, now, now, now)).lastrowid
past = (today - timedelta(days=30)).isoformat()
cust(1, "A-stale-1y",      (today - timedelta(days=365)).isoformat(),      past)               # exit 1y ago, retention_until stale in the past
cust(1, "A-expired-11y",   (today - timedelta(days=365*11)).isoformat(),   past)               # genuinely past 10y
cust(1, "A-null-exit",     None,                                           past)               # closed, no exit_date anchor
cust(1, "A-active-past",   None,                                           past, status="active")
cust(2, "B-expired-11y",   (today - timedelta(days=365*11)).isoformat(),   past)               # other org
c.commit()
print(" dry run org 1:", [d["reference"] for d in purge_expired(c, 1, dry_run=True)["details"]])
res = purge_expired(c, 1)
print(" real purge org 1 purged:", res["purged"], [d["reference"] for d in res["details"]])
print(" remaining:", [(r["org_id"], r["reference"]) for r in c.execute("select org_id, reference from customers order by id")])

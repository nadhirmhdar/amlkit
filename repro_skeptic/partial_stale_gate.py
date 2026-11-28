"""DS1: datasets_fresh() passes when ONE mandatory list is fresh and the rest are days old.
Exit 0 = defect reproduces (gate open with other lists stale); exit 1 = fixed."""
import sys, tempfile, os
from datetime import datetime, timezone, timedelta
from amlkit import db
from amlkit.ingest.loader import datasets_fresh
d = tempfile.mkdtemp(); conn = db.connect(os.path.join(d, "t.db"))
with conn:
    for k in ("ae_local_terrorists", "un_sc_consolidated", "ofac_sdn"):
        conn.execute("INSERT OR IGNORE INTO datasets (key,title,is_mandatory,max_age_hours) VALUES (?,?,1,24)", (k, k))
keys = [r["key"] for r in conn.execute("SELECT key FROM datasets WHERE is_mandatory=1 ORDER BY id")]
print("mandatory keys:", keys)
old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
new = datetime.now(timezone.utc).isoformat()
screenable = [k for k in keys if k != "fatf_country_risk"]
if len(screenable) < 2:
    print("need >=2 mandatory screenable datasets"); sys.exit(2)
with conn:
    conn.execute("UPDATE datasets SET entity_count=100, last_refresh=? WHERE is_mandatory=1", (old,))
    conn.execute("UPDATE datasets SET last_refresh=? WHERE key=?", (new, screenable[-1]))
print("stale:", screenable[:-1], "fresh:", screenable[-1])
r = datasets_fresh(conn)
print("datasets_fresh ->", r)
sys.exit(0 if r else 1)

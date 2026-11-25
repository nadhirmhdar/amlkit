"""Red-team 2026-11-25: owner-granted trial expiry (#468) -- with billing ON, is creation refused after trial_ends_at + 7d grace, and what do odd trial_ends_at values do? Function level, scratch DB. LOCAL ONLY."""
import sys, os, tempfile, logging  # run with AMLKIT_SRC=<checkout of origin/master> when this branch lacks the code under test
from pathlib import Path
from datetime import datetime, timedelta, timezone
ROOT = Path(os.environ.get("AMLKIT_SRC") or Path(__file__).resolve().parent.parent); sys.path.insert(0, str(ROOT)); logging.disable(logging.CRITICAL)
os.environ.update({"AMLKIT_BILLING_ENABLED": "1", "STRIPE_SECRET_KEY": "sk_test_x"})
from amlkit.db import connect
from amlkit.cases.operators import grant_trial
from amlkit.billing import limits
conn = connect(str(Path(tempfile.mkdtemp())/"t.db"))
org = grant_trial(conn, org_name="Acme", operator_name="Ann", email="a@a.ae", password="Str0ng!Passw0rd", days=1)["org_id"]
now = datetime.now(timezone.utc)
def at(delta): return (now + delta).isoformat(timespec="seconds")
cases = [("ends in 1 day", at(timedelta(days=1))), ("ended 1 day ago", at(-timedelta(days=1))), ("ended 6d23h ago (inside grace)", at(-timedelta(days=6, hours=23))),
         ("ended 7d1h ago (past grace)", at(-timedelta(days=7, hours=1))), ("ended 400 days ago", at(-timedelta(days=400))),
         ("naive timestamp, past", (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")), ("date only, past", (now - timedelta(days=30)).strftime("%Y-%m-%d")),
         ("with Z suffix, past", (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")), ("garbage", "tomorrow"), ("empty string", ""), ("NULL", None)]
for res in ("operators", "customers"):
    print("==", res)
    for label, v in cases:
        conn.execute("UPDATE organizations SET trial_ends_at=? WHERE id=?", (v, org)); conn.commit()
        try: limits.check_limit(conn, org, res); out = "allowed"
        except Exception as e: out = f"REFUSED {type(e).__name__}"
        print(f"  {out:34s} {label:34s} {v!r}")

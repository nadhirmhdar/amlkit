"""Skeptic repro: unclamped integer offsets overflow SQLite (alert_queue via /api/v1/alerts?offset=,
audit_trail via /audit?page=, feedback_list via /admin feedback page=). Exit 0 only if all overflow."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from amlkit import db, queries
c = db.connect(":memory:")
c.execute("INSERT INTO organizations (name,slug,status,created_at) VALUES ('t','t','active',?)", (db.utcnow(),)); c.commit()
big = 10**20
cases = {"alert_queue": lambda: queries.alert_queue(c, 1, status="open", limit=10, offset=big),
         "audit_trail": lambda: queries.audit_trail(c, 1, limit=50, offset=(10**19 - 1) * 50),
         "feedback_list": lambda: queries.feedback_list(c, 1, limit=50, offset=(10**19 - 1) * 50)}
bad = 0
for k, f in cases.items():
    try: f(); print(k, "ok")
    except OverflowError as e: bad += 1; print(k, "OverflowError:", e)
sys.exit(0 if bad == len(cases) else 1)

"""Skeptic check: time alert_queue(limit=200) as the open-alert set grows (post-#421 reads all matching rows).
Prints timings; exit 0 if 20k alerts take > 5x the 2k time (cost grows with the whole set)."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(sys.path[0], "tests"))
from amlkit import db, queries
from test_p43_alerts_group_dismiss import _seed
c = db.connect(":memory:"); s = _seed(c); org = s["org_id"]
ent = c.execute("SELECT id FROM entities LIMIT 1").fetchone()[0]
scr = c.execute("SELECT id FROM screenings LIMIT 1").fetchone()[0]
now = db.utcnow()
def grow(n):
    c.executemany("INSERT INTO alerts (org_id, screening_id, entity_id, score, score_detail, matched_name, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
                  [(org, scr, ent, 0.85 + (i % 100) / 1000, "{}", "x", "open", now) for i in range(n)]); c.commit()
def t():
    best = 9
    for _ in range(3):
        a = time.perf_counter(); queries.alert_queue(c, org, status="open", limit=200); best = min(best, time.perf_counter() - a)
    return best
grow(2000); t2 = t(); grow(18000); t20 = t()
print(f"2k alerts: {t2*1000:.1f} ms | 20k alerts: {t20*1000:.1f} ms | ratio {t20/t2:.1f}x")
sys.exit(0 if t20 > 5 * t2 else 1)

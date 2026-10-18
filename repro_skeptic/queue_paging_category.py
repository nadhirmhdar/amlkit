"""Skeptic repro: alert_queue pages by score in SQL, then re-sorts by category inside the page,
so a proliferation alert with a lower score sits behind 200 higher-scoring alerts.
Exit 0 only if the defect reproduces. Scratch :memory: DB."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(sys.path[0], "tests"))
from amlkit import db, queries
from test_p43_alerts_group_dismiss import _seed
c = db.connect(":memory:"); s = _seed(c); org = s["org_id"]
ents = [r[0] for r in c.execute("SELECT id FROM entities ORDER BY id")]
c.execute("UPDATE entities SET programs='[\"NPWMD\"]' WHERE id=?", (ents[2],))
scr = c.execute("SELECT id FROM screenings LIMIT 1").fetchone()[0]
c.execute("UPDATE alerts SET score=0.80 WHERE entity_id=?", (ents[2],))
now = db.utcnow()
for i in range(204):
    c.execute("INSERT INTO alerts (org_id, screening_id, entity_id, score, score_detail, matched_name, status, created_at)"
              " VALUES (?,?,?,?,?,?,?,?)", (org, scr, ents[0], 0.95 - i * 0.0001, "{}", "x", "open", now))
c.commit()
p1 = queries.alert_queue(c, org, status="open", limit=200, offset=0)
p2 = queries.alert_queue(c, org, status="open", limit=200, offset=200)
cnt = lambda p: {k: sum(1 for a in p if a["category"] == k) for k in {a["category"] for a in p}}
print("page1", len(p1), cnt(p1), "| page2", len(p2), cnt(p2))
sys.exit(0 if cnt(p1).get("proliferation", 0) == 0 and cnt(p2).get("proliferation", 0) == 1 else 1)

"""Red-team 2026-11-22 (PC1b e2e): two DIFFERENT same-name PEPs on two lists; dismiss the alert on the first; does the second ever get an alert? LOCAL scratch DB only."""
import sys, json, tempfile, logging
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/"tests"))
logging.disable(logging.CRITICAL)
from amlkit.db import connect
from amlkit.match import cache
from amlkit.match.engine import screen
from test_pep_dedupe import _load
conn = connect(str(Path(tempfile.mkdtemp())/"t.db"))
conn.execute("INSERT INTO organizations (id,name,slug,status,created_at) VALUES (1,'T','t','active','2026-01-01')"); conn.commit(); cache.invalidate()
_load(conn, "us_cia_world_leaders", [("c1", "John Smith", [], ["role.pep"])])      # person A (minister, no country published)
_load(conn, "wikidata_ministers", [("WD-9", "John Smith", ["Ghana"], ["role.pep"])])  # person B (different person, has a country)
def show(tag):
    r = screen(conn, "John Smith", org_id=1, persist=True)
    al = conn.execute("SELECT id, entity_id, status FROM alerts ORDER BY id").fetchall()
    print(f"{tag}: hits={len(r.hits)} alerts_created={r.alerts_created} alert rows={[tuple(a) for a in al]}")
    print("   absorbed:", [(a['entity_id'], a['dataset']) for h in r.hits for a in h.detail.get('also_listed', [])])
show("run 1 (customer has no country)")
conn.execute("UPDATE alerts SET status='dismissed'"); conn.commit()
show("run 2 after dismissing A")
print("entities:", [tuple(x) for x in conn.execute("SELECT id, caption FROM entities")])

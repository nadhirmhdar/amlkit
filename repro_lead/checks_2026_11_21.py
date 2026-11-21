"""Lead checks 2026-11-21 (master bfb0253). Local scratch SQLite only, no network.

PC1b  Two different people named 'John Smith' on PEP-only lists (CIA: GB; Wikidata: no country)
      fold into one alert at onboarding. The reviewer dismisses it (false_positive,
      name_coincidence). On every later re-screen the second entity is still absorbed and is
      never alerted, never offered to _coverage. Reproduces when the absorbed entity has no
      alert row after the re-screen.
CS30  (owed from 11-20) After that dismissal, a refresh delists the kept CIA entry. The
      absorbed Wikidata entity now survives as primary and raises a fresh alert for the same
      customer. Reproduces when that re-screen creates >= 1 alert (re-alert = noise, not a miss).
GEN1  (owed from 11-20) Exact-name sanctions entity with gender 'male'; customer onboarded with
      gender 'female' (and no DOB / country) through cases.manager.onboard. Reproduces when no
      alert is raised (score 0.80 < 0.85).

Exit 0 while at least one item reproduces; exit 1 when all are fixed.
Run from the repo root: PYTHONPATH=. python repro_lead/checks_2026_11_21.py
"""
import sys
import tempfile
from pathlib import Path

from amlkit.cases import manager, review
from amlkit.db import connect
from amlkit.ingest import loader
from amlkit.ingest.base import SourceEntity
from amlkit.match import cache
from amlkit.match.engine import rescreen_all, screen


class _Adapter:
    def __init__(self, key, entities):
        self.key = key
        self.title = key
        self.publisher = key
        self.source_url = "https://example.invalid"
        self.licence = "test"
        self.is_mandatory = True  # onboard() refuses without a fresh mandatory list
        self._entities = entities

    def fetch(self):
        return repr((self.key, self._entities, id(self))).encode()

    def parse(self, payload):
        for sid, name, countries, topics, gender in self._entities:
            yield SourceEntity(
                source_id=sid, schema_type="Person", caption=name, names=[],
                countries=list(countries), birth_date=None, gender=gender,
                topics=list(topics), programs=[], identifiers=[], listed_at=None, raw={},
            )


def _load(conn, key, entities):
    loader.load(conn, _Adapter(key, entities))
    cache.invalidate()


def _db(path):
    conn = connect(str(path))
    conn.execute("INSERT INTO organizations (id, name, slug, status, created_at)"
                 " VALUES (1,'T','t','active','2026-01-01')")
    conn.commit()
    return conn


def _eid(conn, dataset, sid):
    return conn.execute("SELECT e.id FROM entities e JOIN datasets d ON d.id=e.dataset_id WHERE d.key=? AND e.source_id=?",
                        (dataset, sid)).fetchone()["id"]


def _alerts_for(conn, eid, cid):
    return conn.execute(
        "SELECT a.id, a.status FROM alerts a JOIN screenings s ON s.id=a.screening_id"
        " WHERE a.entity_id=? AND s.customer_id=?", (eid, cid)).fetchall()


results = {}
tmp = Path(tempfile.mkdtemp(prefix="lead1121_"))

# ---------------------------------------------------------------- PC1b + CS30
conn = _db(tmp / "pc1b.db")
_load(conn, "us_cia_world_leaders", [("c1", "John SMITH", ["United Kingdom"], ["role.pep"], None)])
_load(conn, "wikidata_ministers", [("WD-9", "John Smith", [], ["role.pep"], None)])
a_id = _eid(conn, "us_cia_world_leaders", "c1")
b_id = _eid(conn, "wikidata_ministers", "WD-9")

out = manager.onboard(conn, org_id=1, reference="C-1", full_name="John Smith", actor="mlro")
cid = conn.execute("SELECT id FROM customers WHERE reference='C-1'").fetchone()["id"]
onb = conn.execute("SELECT a.id, a.entity_id, a.score_detail FROM alerts a").fetchall()
print(f"PC1b  onboarding alerts: {[(r['id'], r['entity_id']) for r in onb]}  (A={a_id}, B={b_id})")
alert_a = onb[0]["id"]
review.propose_disposition(conn, alert_a, org_id=1, status="false_positive",
                           reason_code="name_coincidence", operator="mlro",
                           narrative="Customer is not the UK official.")
st = conn.execute("SELECT status FROM alerts WHERE id=?", (alert_a,)).fetchone()["status"]
print(f"PC1b  alert {alert_a} disposed -> {st}")
rs2 = rescreen_all(conn, 1)
r2 = screen(conn, "John Smith", org_id=1, persist=False)
print(f"PC1b  re-screen: hits={[(h.entity_id, h.dataset) for h in r2.hits]}"
      f" also_listed={[x['entity_id'] for x in r2.hits[0].detail.get('also_listed', [])]}"
      f" rescreen_all={rs2}; alerts ever on B={len(_alerts_for(conn, b_id, cid))}")
results["PC1b"] = len(r2.hits) == 1 and len(_alerts_for(conn, b_id, cid)) == 0

# CS30: CIA delists A; B becomes the kept hit.
_load(conn, "us_cia_world_leaders", [("c2", "Jane DOE", ["United Kingdom"], ["role.pep"], None)])
r3 = screen(conn, "John Smith", org_id=1, persist=False)
rs3 = rescreen_all(conn, 1)
print(f"CS30  after A delisted: hits={[(h.entity_id, h.dataset) for h in r3.hits]}"
      f" rescreen_all={rs3}; alerts on B={[tuple(x) for x in _alerts_for(conn, b_id, cid)]}")
results["CS30"] = len(_alerts_for(conn, b_id, cid)) >= 1
# Side observation (DL1): the dismissed alert on A is cascade-deleted with the delisted entity
# (alerts.entity_id ON DELETE CASCADE, db.py; documented in loader.py:158-161). Audit rows stay.
fp_left = conn.execute("SELECT COUNT(*) n FROM alerts WHERE status='false_positive'").fetchone()["n"]
aud = conn.execute("SELECT COUNT(*) n FROM audit_log WHERE action LIKE 'alert.%'").fetchone()["n"]
print(f"DL1   false_positive alert rows left after delisting A: {fp_left}; alert.* audit rows: {aud}")
conn.close()

# ---------------------------------------------------------------- GEN1
conn = _db(tmp / "gen.db")
_load(conn, "eu_fsf", [("e1", "Ahmed Hassan Ali", [], ["sanction"], "male")])
manager.onboard(conn, org_id=1, reference="G-1", full_name="Ahmed Hassan Ali",
                gender="female", actor="mlro")
manager.onboard(conn, org_id=1, reference="G-2", full_name="Ahmed Hassan Ali",
                gender="male", actor="mlro")
rows = conn.execute(
    "SELECT c.reference, c.gender, s.hits, (SELECT COUNT(*) FROM alerts a WHERE a.screening_id=s.id) n"
    " FROM screenings s JOIN customers c ON c.id=s.customer_id ORDER BY c.reference").fetchall()
for r in rows:
    print(f"GEN1  {r['reference']} gender={r['gender']} hits={r['hits']} alerts={r['n']}")
g = {r["reference"]: r["n"] for r in rows}
results["GEN1"] = g.get("G-1", 0) == 0 and g.get("G-2", 0) >= 1
conn.close()

for k, v in results.items():
    print(f"{k:5s} reproduces={v}")
n = sum(results.values())
print(f"{n}/{len(results)} reproduce")
sys.exit(0 if n else 1)

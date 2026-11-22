"""DL1b (owed by the lead from 2026-11-21): when a refresh delists an entity whose
alert was confirmed true_positive (and so auto-created a freeze obligation),
what survives?

Scratch SQLite only, no network. Exits 0 when the confirmed alert row is
cascade-deleted by the delisting (the defect reproduces). Also prints whether the
freeze_obligations row survives and whether its alert_id is nulled.

Run from the repo root: PYTHONPATH=. python repro_lead/dl1b_delist_true_positive_2026_11_22.py
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



# ---------------------------------------------------------------- DL1b
tmp = Path(tempfile.mkdtemp(prefix="lead1122_"))
conn = _db(tmp / "dl1b.db")
_load(conn, "un_sc_sanctions", [("e1", "Ahmed Hassan Ali", [], ["sanction"], None),
                       ("e2", "Keep Alive Person", [], ["sanction"], None)])
manager.onboard(conn, org_id=1, reference="D-1", full_name="Ahmed Hassan Ali", actor="mlro")
cid = conn.execute("SELECT id FROM customers WHERE reference='D-1'").fetchone()["id"]
alert = conn.execute("SELECT id FROM alerts").fetchone()["id"]
out = review.propose_disposition(conn, alert, org_id=1, status="true_positive",
                                 reason_code="confirmed_match", operator="mlro",
                                 narrative="Confirmed: same person as UN listing.")
conn.commit()
st = conn.execute("SELECT status FROM alerts WHERE id=?", (alert,)).fetchone()["status"]
fo = conn.execute("SELECT id, alert_id, status FROM freeze_obligations").fetchall()
rv = conn.execute("SELECT COUNT(*) n FROM alert_reviews WHERE alert_id=?", (alert,)).fetchone()["n"]
print(f"DL1b  before delisting: alert {alert} status={st}; alert_reviews={rv};"
      f" freeze_obligations={[tuple(r) for r in fo]}")
# Refresh: e1 delisted (e2 keeps the list non-empty)
_load(conn, "un_sc_sanctions", [("e2", "Keep Alive Person", [], ["sanction"], None)])
conn.commit()
a_left = conn.execute("SELECT COUNT(*) n FROM alerts WHERE id=?", (alert,)).fetchone()["n"]
rv_left = conn.execute("SELECT COUNT(*) n FROM alert_reviews WHERE alert_id=?", (alert,)).fetchone()["n"]
fo2 = conn.execute("SELECT id, alert_id, status, obligation_type FROM freeze_obligations").fetchall()
aud = conn.execute("SELECT COUNT(*) n FROM audit_log WHERE action LIKE 'alert.%'").fetchone()["n"]
print(f"DL1b  after delisting: alert row left={a_left}; alert_reviews left={rv_left};"
      f" freeze_obligations={[tuple(r) for r in fo2]}; alert.* audit rows={aud}")
alert_gone = a_left == 0
freeze_orphaned = bool(fo2) and all(r["alert_id"] is None for r in fo2)
print(f"DL1b  true_positive alert cascade-deleted={alert_gone}; freeze row kept but alert_id NULL={freeze_orphaned}")
sys.exit(0 if alert_gone else 1)

"""DL1c (owed by the lead from 2026-11-22), derived from dl1b: when a refresh delists an entity whose
alert was confirmed true_positive (and so auto-created a freeze obligation),
what survives?

Scratch SQLite only, no network. Exits 0 when the confirmed alert row is
cascade-deleted by the delisting (the defect reproduces). Also prints whether the
freeze_obligations row survives and whether its alert_id is nulled.

Question: once a refresh delists the entity behind a pending freeze obligation,
does the hourly overdue check (cases.manager.check_unexecuted_freeze_obligations,
called by POST /system/check-freeze-obligations -- NOT called here as an endpoint)
still count it? And does a legacy OFAC-linked obligation (out of scope while its
alert exists) flip INTO scope when its alert is cascade-deleted?

Scratch SQLite only, no network, SMTP unset (console only). Also (DL1d) tries to close the delisted obligation: as 'delisted' and as
'false_positive'. Exit 0 when all three reproduce.

Run from the repo root: PYTHONPATH=. python repro_lead/dl1c_delisted_freeze_overdue_2026_11_23.py
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




from amlkit.sanctions_scope import freeze_obligation_in_scope

tmp = Path(tempfile.mkdtemp(prefix="lead1123_"))
conn = _db(tmp / "dl1c.db")
_load(conn, "un_sc_sanctions", [("e1", "Ahmed Hassan Ali", [], ["sanction"], None),
                                ("e2", "Keep Alive Person", [], ["sanction"], None)])
_load(conn, "us_ofac_sdn", [("o1", "Viktor Petrovich Orlov", [], ["sanction"], None),
                            ("o2", "Keep Alive Ofac", [], ["sanction"], None)])
manager.onboard(conn, org_id=1, reference="D-1", full_name="Ahmed Hassan Ali", actor="mlro")
manager.onboard(conn, org_id=1, reference="D-2", full_name="Viktor Petrovich Orlov", actor="mlro")
c1 = conn.execute("SELECT id FROM customers WHERE reference='D-1'").fetchone()["id"]
c2 = conn.execute("SELECT id FROM customers WHERE reference='D-2'").fetchone()["id"]
a_un = _alerts_for(conn, _eid(conn, "un_sc_sanctions", "e1"), c1)[0]["id"]
a_ofac = _alerts_for(conn, _eid(conn, "us_ofac_sdn", "o1"), c2)[0]["id"]
review.propose_disposition(conn, a_un, org_id=1, status="true_positive",
                           reason_code="confirmed_match", operator="mlro",
                           narrative="Confirmed: same person as UN listing.")
conn.commit()
# Legacy OFAC-linked obligation (created before the UN/UAE scope rule): insert directly.
conn.execute("INSERT INTO freeze_obligations (org_id, customer_id, alert_id, obligation_type,"
             " risk_category, identified_at, identified_by, status)"
             " VALUES (1, ?, ?, 'sanctions', 'high', '2026-01-01T00:00:00Z', 'legacy', 'pending_execution')",
             (c2, a_ofac))
conn.commit()
fo = {r["customer_id"]: r["id"] for r in conn.execute("SELECT id, customer_id FROM freeze_obligations")}
f_un, f_ofac = fo[c1], fo[c2]
# Backdate so both are > 24h pending.
conn.execute("UPDATE freeze_obligations SET identified_at='2026-01-01T00:00:00Z'")
conn.commit()
def overdue_ids():
    return sorted(o["id"] for o in manager.check_unexecuted_freeze_obligations(conn, 1))
print(f"DL1c  before delisting: in_scope UN={freeze_obligation_in_scope(conn, f_un, 1)}"
      f" OFAC={freeze_obligation_in_scope(conn, f_ofac, 1)}; overdue ids={overdue_ids()}")
_load(conn, "un_sc_sanctions", [("e2", "Keep Alive Person", [], ["sanction"], None)])
_load(conn, "us_ofac_sdn", [("o2", "Keep Alive Ofac", [], ["sanction"], None)])
conn.commit()
rows = [tuple(r) for r in conn.execute("SELECT id, alert_id, status FROM freeze_obligations ORDER BY id")]
in_un = freeze_obligation_in_scope(conn, f_un, 1)
in_ofac = freeze_obligation_in_scope(conn, f_ofac, 1)
od = overdue_ids()
print(f"DL1c  after delisting: freeze rows={rows}; in_scope UN={in_un} OFAC={in_ofac}; overdue ids={od}")
un_still_counted = f_un in od
ofac_flipped = in_ofac and f_ofac in od
print(f"DL1c  delisted UN freeze still overdue/pending={un_still_counted}; legacy OFAC freeze flipped into scope={ofac_flipped}")
# DL1d: how can the MLRO close the delisted, still-pending UN obligation?
try:
    manager.resolve_freeze_obligation(conn, f_un, org_id=1, resolved_by="mlro",
                                      resolution_reason="delisted")
    delisted_ok = True
except ValueError as e:
    delisted_ok = False
    print(f"DL1d  resolve as 'delisted' refused: {e}")
manager.resolve_freeze_obligation(conn, f_un, org_id=1, resolved_by="mlro",
                                  resolution_reason="false_positive",
                                  notes="Entity no longer on the UN list after refresh.")
fp_ok = conn.execute("SELECT status, resolution_reason FROM freeze_obligations WHERE id=?",
                     (f_un,)).fetchone()
print(f"DL1d  resolve as 'false_positive' on a four-eyes-confirmed (now deleted) true_positive -> {tuple(fp_ok)}")
dl1d = (not delisted_ok) and fp_ok["resolution_reason"] == "false_positive"
print(f"DL1d  only exit is mislabelling a confirmed match as false_positive={dl1d}")
sys.exit(0 if (un_still_counted and ofac_flipped and dl1d) else 1)

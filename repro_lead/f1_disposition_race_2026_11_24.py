"""F-1 (compliance-specialist 2026-11-24, from draft PR #411): propose_disposition checks
the alert's status with a separate SELECT, then runs UPDATE alerts ... WHERE id=? AND org_id=?
with no status guard. Deterministic interleave on two connections to one scratch file:

  op A (conn_a) proposes false_positive  -> passes the 'open' check
  op B (conn_b) proposes true_positive   -> runs to completion in the gap (applied, freeze created)
  op A continues                         -> overwrites the confirmed match with pending_review
  op C confirms A's dismissal            -> alert false_positive, B's freeze obligation still pending

The gap is opened by wrapping review.needs_independent_review (called after the check and
before the write); no app code is changed. Scratch SQLite only, no network.
Exit 0 when the confirmed true_positive ends up false_positive with a live freeze obligation.
Run from the repo root: PYTHONPATH=. python repro_lead/f1_disposition_race_2026_11_24.py
"""
import sys
import tempfile
from pathlib import Path

from amlkit.cases import manager, review
from amlkit.db import connect
from amlkit.ingest import loader
from amlkit.ingest.base import SourceEntity
from amlkit.match import cache


class _Adapter:
    key = title = publisher = "un_sc_sanctions"
    source_url = "https://example.invalid"
    licence = "test"
    is_mandatory = True

    def fetch(self):
        return b"f1"

    def parse(self, payload):
        yield SourceEntity(source_id="e1", schema_type="Person", caption="Ahmed Hassan Ali", names=[],
                           countries=[], birth_date=None, gender=None, topics=["sanction"],
                           programs=[], identifiers=[], listed_at=None, raw={})


path = Path(tempfile.mkdtemp(prefix="lead1124_")) / "f1.db"
conn_a = connect(str(path))
conn_a.execute("INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1,'T','t','active','2026-01-01')")
conn_a.commit()
loader.load(conn_a, _Adapter())
cache.invalidate()
manager.onboard(conn_a, org_id=1, reference="F-1", full_name="Ahmed Hassan Ali", actor="mlro")
conn_a.commit()
alert_id = conn_a.execute("SELECT id FROM alerts ORDER BY id LIMIT 1").fetchone()["id"]
conn_b = connect(str(path))

orig = review.needs_independent_review
fired = {"done": False}


def _gap(conn, aid, org_id, status):
    if not fired["done"]:
        fired["done"] = True
        r = review.propose_disposition(conn_b, aid, org_id=1, status="true_positive",
                                       reason_code="confirmed_match", operator="opB", operator_id=2,
                                       narrative="Confirmed: same person as UN listing.")
        conn_b.commit()
        print(f"F1  op B in the gap: {r.status}; freeze rows="
              f"{[tuple(x) for x in conn_b.execute('SELECT id, alert_id, status FROM freeze_obligations')]}")
    return orig(conn, aid, org_id, status)


review.needs_independent_review = _gap
try:
    ra = review.propose_disposition(conn_a, alert_id, org_id=1, status="false_positive",
                                    reason_code="name_coincidence", operator="opA", operator_id=1,
                                    narrative="Different person: DOB and nationality differ.")
    conn_a.commit()
    print(f"F1  op A after B: {ra.status} (no error raised)")
except review.ReviewError as e:
    print(f"F1  op A refused (guard present): {e}")
    sys.exit(1)
finally:
    review.needs_independent_review = orig

rc = review.confirm_disposition(conn_a, alert_id, org_id=1, operator="opC", operator_id=3, agree=True)
conn_a.commit()
st = conn_a.execute("SELECT status FROM alerts WHERE id=?", (alert_id,)).fetchone()["status"]
fo = [tuple(x) for x in conn_a.execute("SELECT id, alert_id, status FROM freeze_obligations")]
trail = [tuple(x) for x in conn_a.execute("SELECT operator, action, status FROM alert_reviews WHERE alert_id=? ORDER BY id", (alert_id,))]
print(f"F1  op C confirms: {rc.status}; final alert status={st}; freeze rows={fo}")
print(f"F1  alert_reviews trail={trail}")
bad = st == "false_positive" and any(r[2] == "pending_execution" for r in fo)
print(f"F1  confirmed true_positive overwritten to false_positive with live freeze obligation={bad}")
sys.exit(0 if bad else 1)

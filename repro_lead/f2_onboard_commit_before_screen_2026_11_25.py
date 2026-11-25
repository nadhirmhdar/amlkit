"""F-2 (compliance-specialist 2026-11-24, from draft PR #411): cases.manager.onboard commits the
customer row in its own `with conn:` block (manager.py:424) before screen() runs (manager.py:460).
If anything raises between the two (here: screen() raising once, standing in for e.g. a lock
timeout or an engine error), the customer stays active with no screening and no risk rating, and a
retry with the same reference is refused by UNIQUE(org_id, reference).

Scratch SQLite only, no network, no app code changed (manager.screen is wrapped in-process).
Exit 0 when an active, unscreened, unrated customer is left behind.
Run from the repo root: PYTHONPATH=. python repro_lead/f2_onboard_commit_before_screen_2026_11_25.py
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

from amlkit.cases import manager
from amlkit.db import connect
from amlkit.ingest import loader
from amlkit.ingest.base import SourceEntity


class _Adapter:
    key = title = publisher = "un_sc_sanctions"
    source_url = "https://example.invalid"
    licence = "test"
    is_mandatory = True

    def fetch(self):
        return b"f2"

    def parse(self, payload):
        yield SourceEntity(source_id="e1", schema_type="Person", caption="Ahmed Hassan Ali", names=[],
                           countries=[], birth_date=None, gender=None, topics=["sanction"],
                           programs=[], identifiers=[], listed_at=None, raw={})


path = Path(tempfile.mkdtemp(prefix="lead1125_")) / "f2.db"
conn = connect(str(path))
conn.execute("INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1,'T','t','active','2026-01-01')")
conn.commit()
loader.load(conn, _Adapter())

_real_screen = manager.screen
calls = {"n": 0}


def _failing_screen(*a, **kw):
    calls["n"] += 1
    if calls["n"] == 1:
        raise sqlite3.OperationalError("database is locked (simulated)")
    return _real_screen(*a, **kw)


manager.screen = _failing_screen
try:
    manager.onboard(conn, org_id=1, reference="F2-1", full_name="Ahmed Hassan Ali", nationality="AE")
    print("F2  onboard returned normally (unexpected)")
except sqlite3.OperationalError as e:
    print(f"F2  onboard raised: {e}")

cust = conn.execute("SELECT id, status FROM customers WHERE org_id=1 AND reference='F2-1'").fetchall()
cid = cust[0][0] if cust else None
scr = conn.execute("SELECT COUNT(*) FROM screenings WHERE customer_id=?", (cid,)).fetchone()[0]
ra = conn.execute("SELECT COUNT(*) FROM risk_assessments WHERE customer_id=?", (cid,)).fetchone()[0]
al = conn.execute("SELECT COUNT(*) FROM alerts WHERE org_id=1").fetchone()[0]
print(f"F2  customer rows={[tuple(r) for r in cust]} screenings={scr} risk_assessments={ra} alerts={al}")

retry = "n/a"
try:
    manager.onboard(conn, org_id=1, reference="F2-1", full_name="Ahmed Hassan Ali", nationality="AE")
    retry = "succeeded"
except Exception as e:  # noqa: BLE001
    retry = f"{type(e).__name__}: {e}"
print(f"F2  retry with same reference: {retry}")

left_behind = bool(cust) and cust[0][1] == "active" and scr == 0 and ra == 0
print(f"F2  active customer left unscreened and unrated (UN-listed name)={left_behind}")
sys.exit(0 if left_behind else 1)

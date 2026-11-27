"""DS1 (skeptic 2026-11-27): loader.datasets_fresh() (ingest/loader.py:267-297) returns True on the
FIRST mandatory screenable dataset that is fresh, so onboarding (cases/manager.py:360) proceeds when
the UAE Local Terrorist List is days stale as long as the UN list is fresh, while
staleness_report() (loader.py:234-252) flags the UAE list as a breach.

Note: only UN and the UAE list are mandatory in code (un.py:23, eocn.py:520, opensanctions.py:157/162);
OFAC/EU/UK are is_mandatory=False and never feed the gate.

Scratch SQLite only, no network, no app code changed.
Exit 0 when: UAE list stale + UN fresh -> datasets_fresh True, staleness_report breach for the UAE
list, and onboard() accepted.
Run from the repo root: PYTHONPATH=. python repro_lead/ds1_partial_stale_gate_2026_11_27.py
"""
import sys
import tempfile
from pathlib import Path

from amlkit.cases import manager
from amlkit.db import connect
from amlkit.ingest import loader
from amlkit.ingest.base import SourceEntity


def _adapter(key, caption):
    class _A:
        title = publisher = key
        source_url = "https://example.invalid"
        licence = "test"
        is_mandatory = True

        def fetch(self):
            return key.encode()

        def parse(self, payload):
            yield SourceEntity(source_id=key + "1", schema_type="Person", caption=caption, names=[],
                               countries=[], birth_date=None, gender=None, topics=["sanction"],
                               programs=[], identifiers=[], listed_at=None, raw={})
    a = _A()
    a.key = key
    return a


path = Path(tempfile.mkdtemp(prefix="lead1127_")) / "ds1.db"
conn = connect(str(path))
conn.execute("INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1,'T','t','active','2026-01-01')")
conn.commit()
loader.load(conn, _adapter("un_sc_sanctions", "Ahmed Hassan Ali"))
loader.load(conn, _adapter("ae_local_terrorists", "Khalid Saeed Rashid"))
with conn:
    conn.execute("UPDATE datasets SET last_refresh='2026-01-01T00:00:00+00:00' WHERE key='ae_local_terrorists'")

fresh = loader.datasets_fresh(conn)
report = loader.staleness_report(conn)
uae = [r for r in report if r.get("key") == "ae_local_terrorists"]
uae_breach = bool(uae and uae[0].get("breach"))
print(f"DS1 datasets: {[(r.get('key'), r.get('mandatory'), r.get('breach')) for r in report]}")
print(f"DS1 UAE list stale (2026-01-01), UN fresh -> datasets_fresh={fresh}, UAE breach={uae_breach}")
try:
    cid = manager.onboard(conn, org_id=1, reference="DS1-1", full_name="Zainab Omar Khalid", nationality="AE")
    onboard = f"accepted (customer {cid})"
except manager.StaleDatasetsError as e:
    onboard = f"refused ({e})"
print(f"DS1 onboard with UAE list stale: {onboard}")

reproduced = fresh and uae_breach and onboard.startswith("accepted")
print(f"DS1 gate passes on one fresh list while the UAE list is in breach={reproduced}")
sys.exit(0 if reproduced else 1)

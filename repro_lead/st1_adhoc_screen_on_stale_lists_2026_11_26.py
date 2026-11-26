"""ST-1 (lead 2026-11-26, from skeptic's "not tested by anyone" list): onboarding fails closed on stale
sanctions lists (manager.py:360-364, StaleDatasetsError), but the ad-hoc screen path does not.
engine.screen() has no freshness check, the web POST /screen route (routers/screening.py:59-113)
and mobile POST /api/v1/screen (mobile.py:556) call it without one, and screen.html carries no
"lists as of" / stale notice, so a non-super-admin officer gets a CLEAR on lists days out of date.

Scratch SQLite only, no network, no app code changed.
Exit 0 when: datasets_fresh() is False, onboard() is refused, and screen() still returns a CLEAR
result (no flag on ScreeningResult telling the caller the lists were stale), and neither route
source nor screen.html mentions freshness.
Run from the repo root: PYTHONPATH=. python repro_lead/st1_adhoc_screen_on_stale_lists_2026_11_26.py
"""
import dataclasses
import sys
import tempfile
from pathlib import Path

from amlkit.cases import manager
from amlkit.db import connect
from amlkit.ingest import loader
from amlkit.ingest.base import SourceEntity
from amlkit.match import engine


class _Adapter:
    key = title = publisher = "un_sc_sanctions"
    source_url = "https://example.invalid"
    licence = "test"
    is_mandatory = True

    def fetch(self):
        return b"st1"

    def parse(self, payload):
        yield SourceEntity(source_id="e1", schema_type="Person", caption="Ahmed Hassan Ali", names=[],
                           countries=[], birth_date=None, gender=None, topics=["sanction"],
                           programs=[], identifiers=[], listed_at=None, raw={})


path = Path(tempfile.mkdtemp(prefix="lead1126_")) / "st1.db"
conn = connect(str(path))
conn.execute("INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1,'T','t','active','2026-01-01')")
conn.commit()
loader.load(conn, _Adapter())
with conn:
    conn.execute("UPDATE datasets SET last_refresh='2026-01-01T00:00:00+00:00'")
fresh = loader.datasets_fresh(conn)
print(f"ST1 datasets_fresh after backdating to 2026-01-01: {fresh}")

try:
    manager.onboard(conn, org_id=1, reference="ST1-1", full_name="Zainab Omar Khalid", nationality="AE")
    onboard = "accepted"
except manager.StaleDatasetsError as e:
    onboard = f"refused ({e})"
print(f"ST1 onboard on stale lists: {onboard}")

res = engine.screen(conn, "Zainab Omar Khalid", org_id=1, trigger="adhoc", actor="lead")
fields = [f.name for f in dataclasses.fields(res)]
stale_flag = any("stale" in f or "fresh" in f for f in fields)
print(f"ST1 ad-hoc screen on stale lists: {res.summary()}")
print(f"ST1 ScreeningResult fields={fields} stale/fresh flag present={stale_flag}")

root = Path(__file__).resolve().parent.parent / "amlkit"
web_route = (root / "api/routers/screening.py").read_text().split('@router.post("/screen"')[1].split("\n# ----")[0]
mobile_route = (root / "api/mobile.py").read_text().split('@router.post("/screen")')[1].split("\n@router")[0]
template = (root / "web/templates/screen.html").read_text().lower()
route_checks = {
    "web /screen checks freshness": "fresh" in web_route or "stale" in web_route,
    "mobile /screen checks freshness": "fresh" in mobile_route or "stale" in mobile_route,
    "screen.html mentions freshness": any(k in template for k in ("stale", "fresh", "last_refresh", "as of")),
}
print(f"ST1 static checks: {route_checks}")

reproduced = (not fresh) and onboard.startswith("refused") and res.clear and not stale_flag \
    and not any(route_checks.values())
print(f"ST1 onboarding fails closed but ad-hoc screen returns CLEAR on stale lists={reproduced}")
sys.exit(0 if reproduced else 1)

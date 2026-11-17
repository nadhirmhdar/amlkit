"""Lead checks for 2026-11-17 (master 9219e26). Local scratch DB only, no network.

Counts as reproducing (exit 0 if any reproduce, 1 if none):
  QU1w  web /alerts with 205 open alerts renders only 200 alert rows and no
        "showing 200 of N" notice, while the dashboard says 205 are waiting.
  QU1c  web /alerts.csv (default status=all) exports 200 rows, not 205.
  QU1m  mobile GET /api/v1/alerts.csv exports 200 rows, not 205
        (mobile.py:1492 calls alert_queue with no limit; skeptic missed it).
  TD2   add_case_note stores a 1 MB body containing NUL and U+202E unchanged.

Printed, not counted (control):
  QU2   /alerts?status=bogus shows "Unknown filter ignored." (L-62 is
        implemented; mlro-user's "no message" is refuted). ?page=2 / ?q=
        are not recognised parameters and are silently ignored.

Run from the repo root:  PYTHONPATH=. python repro_lead/checks_2026_11_17.py
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

tmp = Path(tempfile.mkdtemp(prefix="lead1117_"))
os.environ["AMLKIT_DB"] = str(tmp / "lead.db")
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)
os.environ.pop("AMLKIT_SMTP_HOST", None)
os.environ.pop("STRIPE_SECRET_KEY", None)
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = "test-invite"

from test_api import LISTED, _register, _seed_sanctions_data  # noqa: E402

_seed_sanctions_data(Path(os.environ["AMLKIT_DB"]))
from conftest import unlock_mobile_mfa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from amlkit import db as amldb  # noqa: E402
from amlkit.api.app import app, limiter  # noqa: E402
from amlkit.cases import manager  # noqa: E402

limiter.enabled = False
N = 205
results: dict[str, bool] = {}

# Two orgs: one registered on mobile (bearer token), one on web (session).
m = TestClient(app)
r = m.post("/api/v1/auth/register-organization", json={
    "org_name": "Lead Queue Firm", "name": "Queue Mlro", "email": "mlro@leadq.ae",
    "password": "A-strong-password-1", "invite_code": "test-invite",
})
tok = m.post("/api/v1/auth/verify-email",
             json={"token": r.json()["dev_verification_token"]}).json()["token"]
unlock_mobile_mfa(m, tok)
h = {"Authorization": f"Bearer {tok}"}

w = _register(TestClient(app), "Lead Web Queue Firm", "Web Mlro", "mlro@leadwq.ae")

conn = amldb.connect(os.environ["AMLKIT_DB"])


def fill(email: str) -> tuple[int, int]:
    oid = conn.execute("SELECT org_id FROM operators WHERE email=?", (email,)).fetchone()[0]
    for i in range(N):
        manager.onboard(conn, org_id=oid, reference=f"Q-{i:04d}", full_name=LISTED,
                        nationality="LY", actor="lead")
    return oid, conn.execute("SELECT COUNT(*) FROM alerts WHERE org_id=? AND status='open'",
                             (oid,)).fetchone()[0]


OID, open_n = fill("mlro@leadwq.ae")
_, open_m = fill("mlro@leadq.ae")
print(f"setup open alerts in DB: web org={open_n} mobile org={open_m}")
page = w.get("/alerts").text
rows = len(set(re.findall(r'/alerts/(\d+)/', page)))
notice = bool(re.search(r"(showing|of)\s+200\b|200 of", page, re.I))
dash = w.get("/dashboard")
dash_txt = dash.text if dash.status_code == 200 else w.get("/").text
m_d = re.search(r"(\d+) waiting for a decision", dash_txt)
print(f"QU1w  /alerts distinct alert ids={rows} cap-notice={notice};"
      f" dashboard says {m_d.group(1) if m_d else '?'} waiting")
results["QU1w"] = open_n > 200 and rows == 200 and not notice

c = w.get("/alerts.csv")
crow = len(list(csv.reader(io.StringIO(c.text)))) - 1
print(f"QU1c  web /alerts.csv status={c.status_code} data rows={crow}")
results["QU1c"] = c.status_code == 200 and crow == 200 < open_n

mc = m.get("/api/v1/alerts.csv", headers=h)
mrow = len(list(csv.reader(io.StringIO(mc.text)))) - 1
print(f"QU1m  mobile /api/v1/alerts.csv status={mc.status_code} data rows={mrow}")
results["QU1m"] = mc.status_code == 200 and mrow == 200 < open_m

bogus = w.get("/alerts?status=bogus").text
paged = w.get("/alerts?page=2").text
print(f"QU2   ?status=bogus shows 'Unknown filter ignored.'={'Unknown filter ignored.' in bogus};"
      f" ?page=2 shows it={'Unknown filter ignored.' in paged} (control, not counted)")

# TD2: 1 MB case note with NUL + RTL override
cid = conn.execute("SELECT id FROM customers WHERE org_id=? LIMIT 1", (OID,)).fetchone()[0]
body = "A\x00B‮evil" + "x" * (1024 * 1024)
try:
    nid = manager.add_case_note(conn, cid, OID, author="lead", body=body)
    stored = conn.execute("SELECT body FROM case_notes WHERE id=?", (nid,)).fetchone()[0]
    td2 = stored == body
    print(f"TD2   1 MB note with NUL+U+202E stored unchanged={td2} (len={len(stored)})")
except ValueError as e:
    td2 = False
    print("TD2   refused:", e)
results["TD2"] = td2
conn.close()

n = sum(results.values())
for k, v in results.items():
    print(f"{k:5s} reproduces={v}")
print(f"{n}/{len(results)} reproduce")
sys.exit(0 if n else 1)

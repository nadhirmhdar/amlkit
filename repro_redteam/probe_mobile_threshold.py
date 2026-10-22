"""Red-team 2026-10-05: /api/v1/admin/threshold input handling (NaN, bounds). LOCAL ONLY; needs fixtures/seed.db."""
import json, os, shutil, sqlite3, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
B = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text())["B"]
tmp = Path(tempfile.mkdtemp()); db = tmp/"s.db"; os.environ["AMLKIT_DB"] = str(db); os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE","test-invite")
shutil.copy(ROOT/"fixtures"/"seed.db", db)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app
from amlkit.db import connect
c = connect(db); t = auth.create_session(c, B["mlro_id"], B["org_id"], mfa_verified=True); c.close()
cl = TestClient(app, follow_redirects=False)
def stored(): return sqlite3.connect(db).execute("select alert_threshold from org_settings where org_id=?",(B["org_id"],)).fetchall()
for raw in ['{"threshold": 0.99}', '{"threshold": 1.0}', '{"threshold": 0.0}', '{"threshold": NaN}', '{"threshold": Infinity}', '{"threshold": -1}', '{"threshold": 1.5}', '{"threshold": null}']:
    r = cl.post("/api/v1/admin/threshold", content=raw, headers={"Authorization": f"Bearer {t}", "content-type": "application/json"})
    print(f" {raw:26s} -> {r.status_code} {r.text[:80]!r} stored={stored()}")

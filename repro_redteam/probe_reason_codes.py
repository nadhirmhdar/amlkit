"""Red-team 2026-11-08: PR #461 reason-code coherence (review.ALLOWED_REASON_CODES). Every status x reason combination through the mobile disposition route;
a PEP-style false positive cleared as 'confirmed_match' must be refused. LOCAL ONLY (needs fixtures/ from PR #412 make_seed)."""
import json, os, shutil, sqlite3, sys, tempfile, itertools
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); B = ids["B"]
db = Path(tempfile.mkdtemp())/"s.db"; os.environ["AMLKIT_DB"] = str(db); os.environ["AMLKIT_SINGLE_OPERATOR_MODE"] = "1"
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.cases.review import REASON_CODES, ALLOWED_REASON_CODES
from amlkit.db import connect, _reset_init_cache
shutil.copy(ROOT/"fixtures"/"seed.db", db); _reset_init_cache(); limiter.reset()
cl = TestClient(app, raise_server_exceptions=False)
c = connect(db); tok = auth.create_session(c, B["mlro_id"], B["org_id"], mfa_verified=True); c.close(); H = {"Authorization": f"Bearer {tok}"}
bad = []; n = 0
for status, code in itertools.product(["false_positive", "true_positive", "escalated", "open", "bogus"], list(REASON_CODES) + ["nonsense"]):
    c = connect(db); c.execute("update alerts set status='open', disposition=NULL, reason_code=NULL where id=?", (B["alert_id"],)); c.commit(); c.close(); limiter.reset()
    r = cl.post(f"/api/v1/alerts/{B['alert_id']}/disposition", headers=H, json={"status": status, "reason_code": code, "note": "red-team coherence probe, long enough note", "narrative": "red-team coherence probe, long enough narrative for the policy minimum"})
    allowed = status in ALLOWED_REASON_CODES and code in ALLOWED_REASON_CODES[status]; n += 1
    if (r.status_code < 300) != allowed: bad.append((status, code, r.status_code, r.text[:70]))
    if r.status_code >= 500: bad.append(("5xx", status, code, r.status_code))
print(f"{n} status x reason combinations; mismatches between the table and the route (accepted-but-disallowed, refused-but-allowed, or 5xx): {bad or 'none'}")

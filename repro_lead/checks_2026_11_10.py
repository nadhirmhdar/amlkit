"""Lead checks for 2026-11-10 (master 9219e26). Local scratch DB only, no network.

Counts as reproducing (exit 0 if any reproduce, 1 if none):
  MA1   POST /api/v1/admin/operators/{id}/deactivate lets the only active MLRO
        of an organisation deactivate themselves (200), leaving the org with
        zero active MLROs. The web route refuses the same operation.
  MA1w  control: the web route POST /admin/operators/{id}/deactivate refuses
        the last active MLRO (not counted; printed so a fix that changes the
        web route too is visible)

Run from the repo root:  PYTHONPATH=. python repro_lead/checks_2026_11_10.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

tmp = Path(tempfile.mkdtemp(prefix="lead1110_"))
os.environ["AMLKIT_DB"] = str(tmp / "lead.db")
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)
os.environ.pop("AMLKIT_SMTP_HOST", None)
os.environ.pop("STRIPE_SECRET_KEY", None)
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = "test-invite"

from test_api import _csrf, _register, _seed_sanctions_data  # noqa: E402

_seed_sanctions_data(Path(os.environ["AMLKIT_DB"]))
from conftest import unlock_mobile_mfa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from amlkit import db as amldb  # noqa: E402
from amlkit.api.app import app, limiter  # noqa: E402

limiter.enabled = False


def active_mlros(email_domain: str) -> int:
    conn = amldb.connect(os.environ["AMLKIT_DB"])
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM operators o WHERE o.role='mlro' AND o.is_active=1 "
            "AND o.org_id=(SELECT org_id FROM operators WHERE email LIKE ? LIMIT 1)",
            (f"%@{email_domain}",),
        ).fetchone()[0]
    finally:
        conn.close()


def op_id(email: str) -> int:
    conn = amldb.connect(os.environ["AMLKIT_DB"])
    try:
        return conn.execute("SELECT id FROM operators WHERE email=?", (email,)).fetchone()[0]
    finally:
        conn.close()


# --- MA1w control: web route, sole MLRO deactivates self -------------------
w = _register(TestClient(app), "Lead Web Firm", "Web Mlro", "mlro@leadweb.ae")
wid = op_id("mlro@leadweb.ae")
w.get("/admin")
r = w.post(f"/admin/operators/{wid}/deactivate", data={"csrf_token": _csrf(w)},
           follow_redirects=True)
web_refused = "last active MLRO" in r.text
print(f"MA1w  web deactivate of sole MLRO: status={r.status_code} refused={web_refused} "
      f"active_mlros_after={active_mlros('leadweb.ae')}")

# --- MA1: mobile route, sole MLRO deactivates self -------------------------
m = TestClient(app)
r = m.post("/api/v1/auth/register-organization", json={
    "org_name": "Lead Mobile Firm", "name": "Mob Mlro", "email": "mlro@leadmob.ae",
    "password": "A-strong-password-1", "invite_code": "test-invite",
})
tok = m.post("/api/v1/auth/verify-email",
             json={"token": r.json()["dev_verification_token"]}).json()["token"]
unlock_mobile_mfa(m, tok)
h = {"Authorization": f"Bearer {tok}"}
mid = op_id("mlro@leadmob.ae")
before = active_mlros("leadmob.ae")
r = m.post(f"/api/v1/admin/operators/{mid}/deactivate", headers=h)
after = active_mlros("leadmob.ae")
print(f"MA1   mobile deactivate of sole MLRO: status={r.status_code} body={r.json()} "
      f"active_mlros before={before} after={after}")
ma1 = r.status_code == 200 and before == 1 and after == 0
print(f"MA1   reproduces={ma1}")
print(f"{int(ma1)}/1 reproduce")
sys.exit(0 if ma1 else 1)

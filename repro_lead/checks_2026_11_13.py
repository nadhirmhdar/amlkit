"""Lead checks for 2026-11-13 (master 9219e26). Local scratch DB only, no network.

Counts as reproducing (exit 0 if any reproduce, 1 if none):
  SO1  one MLRO POSTs /admin/single-operator mode=on while the org has three
       active operators (MLRO, officer, second MLRO); single-operator mode is
       then effective, i.e. four-eyes is off for the whole firm.
  RL1  no route anywhere (web or mobile) changes an operator's role, yet the
       web last-MLRO guard tells the user to "Promote another operator".
  RL2  deactivate -> reactivate an officer: the officer signs in again with
       the old password (no reset forced).
  RL2d deactivation does not revoke the operator's "remember this device"
       token, so after reactivation the old trusted-device cookie still
       validates (MFA skip survives deactivation).
  RL3  reactivating an already active operator says "Operator reactivated."
       and writes another operator.reactivate audit row.

Run from the repo root:  PYTHONPATH=. python repro_lead/checks_2026_11_13.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

tmp = Path(tempfile.mkdtemp(prefix="lead1113_"))
os.environ["AMLKIT_DB"] = str(tmp / "lead.db")
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)
os.environ.pop("AMLKIT_SMTP_HOST", None)
os.environ.pop("STRIPE_SECRET_KEY", None)
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = "test-invite"

from test_api import _csrf, _login, _register, _seed_sanctions_data  # noqa: E402

_seed_sanctions_data(Path(os.environ["AMLKIT_DB"]))
from fastapi.testclient import TestClient  # noqa: E402
from amlkit import auth  # noqa: E402
from amlkit import db as amldb  # noqa: E402
from amlkit.api.app import app, limiter  # noqa: E402
from amlkit.cases.review import single_operator_mode  # noqa: E402

limiter.enabled = False
PW = "A-strong-password-1"


def conn():
    return amldb.connect(os.environ["AMLKIT_DB"])


def one(sql, args=()):
    c = conn()
    try:
        return c.execute(sql, args).fetchone()[0]
    finally:
        c.close()


mlro = _register(TestClient(app), "Lead Roles Firm", "Lead Mlro", "mlro@leadroles.ae")
org_id = one("SELECT org_id FROM operators WHERE email=?", ("mlro@leadroles.ae",))
mlro.get("/admin")
for name, email, role in (("Lead Officer", "officer@leadroles.ae", "officer"),
                          ("Second Mlro", "mlro2@leadroles.ae", "mlro")):
    mlro.post("/admin/operators", data={"name": name, "email": email, "password": PW,
                                        "role": role, "csrf_token": _csrf(mlro)})
active = one("SELECT COUNT(*) FROM operators WHERE org_id=? AND is_active=1", (org_id,))
off_id = one("SELECT id FROM operators WHERE email=?", ("officer@leadroles.ae",))
m2_id = one("SELECT id FROM operators WHERE email=?", ("mlro2@leadroles.ae",))

# --- SO1 ---------------------------------------------------------------------
c = conn()
before = single_operator_mode(c, org_id)
c.close()
r = mlro.post("/admin/single-operator", data={"mode": "on", "csrf_token": _csrf(mlro)},
              follow_redirects=True)
c = conn()
after = single_operator_mode(c, org_id)
c.close()
so1 = active == 3 and before is False and after is True
print(f"SO1  active_operators={active} single_operator before={before} after={after} "
      f"msg_on_page={'Single-operator mode is now on' in r.text}  reproduces={so1}")
mlro.post("/admin/single-operator", data={"mode": "default", "csrf_token": _csrf(mlro)})

# --- RL1 ---------------------------------------------------------------------
role_routes = [getattr(rt, "path", "") for rt in app.routes
               if "operators" in getattr(rt, "path", "")
               and any(k in getattr(rt, "path", "") for k in ("role", "promote", "demote"))]
src = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "amlkit").rglob("*.py"))
update_role = "SET role" in src
admin_src = (ROOT / "amlkit/api/routers/admin.py").read_text(encoding="utf-8")
promote_msg = "Promote another" in admin_src
rl1 = not role_routes and not update_role and promote_msg
print(f"RL1  role-change routes={role_routes} 'SET role' in source={update_role} "
      f"'Promote another' message present={promote_msg}  reproduces={rl1}")

# --- RL2 / RL2d --------------------------------------------------------------
c = conn()
raw_dev = auth.create_trusted_device(c, m2_id)
c.close()
mlro.get("/admin")
mlro.post(f"/admin/operators/{off_id}/deactivate", data={"csrf_token": _csrf(mlro)})
mlro.post(f"/admin/operators/{m2_id}/deactivate", data={"csrf_token": _csrf(mlro)})
blocked = TestClient(app)
_login(blocked, "officer@leadroles.ae", PW)
blocked_ok = blocked.get("/customers", follow_redirects=False).status_code == 200
mlro.get("/admin")
mlro.post(f"/admin/operators/{off_id}/reactivate", data={"csrf_token": _csrf(mlro)})
mlro.post(f"/admin/operators/{m2_id}/reactivate", data={"csrf_token": _csrf(mlro)})
back_in = TestClient(app)
_login(back_in, "officer@leadroles.ae", PW)
back_ok = back_in.get("/customers", follow_redirects=False).status_code == 200
rl2 = (not blocked_ok) and back_ok
print(f"RL2  officer signed in while deactivated={blocked_ok}; after reactivate with OLD "
      f"password={back_ok}  reproduces={rl2}")
c = conn()
dev_valid = auth.is_trusted_device_valid(c, m2_id, raw_dev)
c.close()
rl2d = dev_valid
print(f"RL2d trusted-device token minted before deactivation still valid after "
      f"reactivation={dev_valid}  reproduces={rl2d}")

# --- RL3 ---------------------------------------------------------------------
n0 = one("SELECT COUNT(*) FROM audit_log WHERE action='operator.reactivate' AND object_id=?",
         (str(off_id),))
mlro.get("/admin")
r = mlro.post(f"/admin/operators/{off_id}/reactivate", data={"csrf_token": _csrf(mlro)},
              follow_redirects=True)
n1 = one("SELECT COUNT(*) FROM audit_log WHERE action='operator.reactivate' AND object_id=?",
         (str(off_id),))
rl3 = "Operator reactivated." in r.text and n1 == n0 + 1
print(f"RL3  reactivate already-active officer: success msg={'Operator reactivated.' in r.text} "
      f"audit rows {n0} -> {n1}  reproduces={rl3}")

res = [so1, rl1, rl2, rl2d, rl3]
print(f"{sum(res)}/{len(res)} reproduce")
sys.exit(0 if any(res) else 1)

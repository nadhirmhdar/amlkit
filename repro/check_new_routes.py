"""Targeted tenant-isolation check for routes added after the generic sweep was written:
POST /customers/{id}/periodic-review (web), POST /api/v1/customers/{id}/periodic-review (mobile),
POST /admin/operators/{id}/unlock. As org B's MLRO, attack org A's IDs; control with B's own.
Exit 0 == a cross-tenant effect was reproduced; non-zero == not produced."""
import sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep
from sweep import A, B, auth, db  # noqa

LONG = "periodic review note long enough to satisfy the minimum length requirement"
findings, rows = [], []

def q(sql, *a):
    c = sqlite3.connect(db); c.row_factory = sqlite3.Row
    try: return c.execute(sql, a).fetchall()
    finally: c.close()

def x(sql, *a):
    c = sqlite3.connect(db); c.execute(sql, a); c.commit(); c.close()

def rep(name, status, cross, ctl):
    rows.append((name, status, cross, ctl))
    if cross: findings.append(name)

# ---- web periodic review
cl, raw = sweep.fresh("mlro"); csrf = cl.cookies.get(auth.CSRF_COOKIE)
form = {"csrf_token": csrf, "outcome": "no_change", "note": LONG}
before = q("SELECT COUNT(*) n FROM periodic_reviews WHERE org_id=?", A["org_id"])[0]["n"]
r = cl.post(f"/customers/{A['customer_id']}/periodic-review", data=form, headers={"X-CSRF-Token": csrf})
after = q("SELECT COUNT(*) n FROM periodic_reviews WHERE org_id=?", A["org_id"])[0]["n"]
cb = q("SELECT COUNT(*) n FROM periodic_reviews WHERE org_id=?", B["org_id"])[0]["n"]
rc = cl.post(f"/customers/{B['customer_id']}/periodic-review", data=form, headers={"X-CSRF-Token": csrf})
ca = q("SELECT COUNT(*) n FROM periodic_reviews WHERE org_id=?", B["org_id"])[0]["n"]
rep("web periodic-review", r.status_code, after != before or r.status_code in (200, 303) and "Periodic review recorded" in r.headers.get("location", "") + r.text,
    f"control {rc.status_code}, B rows {cb}->{ca}")

# ---- mobile periodic review
cl, raw = sweep.fresh("mlro")
hdr = {"Authorization": f"Bearer {raw}"}
before = q("SELECT COUNT(*) n FROM periodic_reviews WHERE org_id=?", A["org_id"])[0]["n"]
r = cl.post(f"/api/v1/customers/{A['customer_id']}/periodic-review", json={"outcome": "no_change", "note": LONG}, headers=hdr)
after = q("SELECT COUNT(*) n FROM periodic_reviews WHERE org_id=?", A["org_id"])[0]["n"]
cb = q("SELECT COUNT(*) n FROM periodic_reviews WHERE org_id=?", B["org_id"])[0]["n"]
rc = cl.post(f"/api/v1/customers/{B['customer_id']}/periodic-review", json={"outcome": "no_change", "note": LONG}, headers=hdr)
ca = q("SELECT COUNT(*) n FROM periodic_reviews WHERE org_id=?", B["org_id"])[0]["n"]
rep("mobile periodic-review", r.status_code, after != before or r.status_code == 200,
    f"control {rc.status_code}, B rows {cb}->{ca}")

# ---- unlock
cl, raw = sweep.fresh("mlro"); csrf = cl.cookies.get(auth.CSRF_COOKIE)
x("UPDATE operators SET failed_login_count=4, locked_until='2099-01-01T00:00:00+00:00' WHERE id IN (?,?)", A["officer_id"], B["officer_id"])
r = cl.post(f"/admin/operators/{A['officer_id']}/unlock", data={"csrf_token": csrf}, headers={"X-CSRF-Token": csrf})
a = q("SELECT failed_login_count f, locked_until l FROM operators WHERE id=?", A["officer_id"])[0]
rc = cl.post(f"/admin/operators/{B['officer_id']}/unlock", data={"csrf_token": csrf}, headers={"X-CSRF-Token": csrf})
b = q("SELECT failed_login_count f, locked_until l FROM operators WHERE id=?", B["officer_id"])[0]
rep("admin unlock", r.status_code, a["f"] == 0 or a["l"] is None,
    f"control {rc.status_code}, B officer lock cleared={b['f'] == 0 and b['l'] is None}")

for n, s, cross, ctl in rows:
    print(f"{n:24} attack={s} cross_tenant_effect={cross}  [{ctl}]")
print("FINDINGS:", findings or "none")
sys.exit(0 if findings else 1)

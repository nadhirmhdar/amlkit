"""Red-team 2026-11-02: PR #447 look-through ownership (cases.manager._identified_ownership is recursive) + UBO diagram. A deep chain of corporate owners
(each a 100% stake in its parent) -> RecursionError? Does the customer page / risk reassessment / diagram survive? LOCAL ONLY (needs fixtures/ from PR #412)."""
import json, os, shutil, sqlite3, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); B = ids["B"]
db = Path(tempfile.mkdtemp())/"s.db"; os.environ["AMLKIT_DB"] = str(db); shutil.copy(ROOT/"fixtures"/"seed.db", db)
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.cases import manager as M
from amlkit.db import connect, _reset_init_cache
_reset_init_cache(); limiter.reset()
c = connect(db); cid = c.execute("select id from customers where org_id=? limit 1", (B["org_id"],)).fetchone()[0]; c.execute("update customers set customer_type='legal' where id=?", (cid,)); c.commit()  # ownership_state() returns early for natural persons
tok = auth.create_session(c, B["mlro_id"], B["org_id"], mfa_verified=True)
cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False); cl.cookies.set(auth.SESSION_COOKIE, tok)
print("customer", cid, "limit", sys.getrecursionlimit())
parent = None; depth = 0
for target in (100, 900, 1100):
    t0 = time.time()
    while depth < target:
        try: parent = M.add_ubo(c, cid, org_id=B["org_id"], person_name=f"Holdco {depth}", ownership_pct=(40 if parent is None else 100), parent_ubo_id=parent, actor="probe")
        except Exception as e: print(f" add_ubo refused at depth {depth}: {type(e).__name__}: {e}"); target = depth; break
        depth += 1
    try: st = M.ownership_state(c, cid, B["org_id"], "legal"); res = f"ownership_state -> {st}"
    except RecursionError: res = "ownership_state -> RecursionError"
    except Exception as e: res = f"ownership_state -> {type(e).__name__}: {e}"
    r = cl.get(f"/customers/{cid}"); r2 = cl.get(f"/customers/{cid}/risk") if False else None
    print(f" depth {depth:5d} (built in {time.time()-t0:.1f}s): {res} | GET /customers/{cid} -> {r.status_code}")
    if depth < target or "RecursionError" in res: break
t0 = time.time(); r = cl.get(f"/customers/{cid}"); print(f" page time at depth {depth}: {time.time()-t0:.1f}s, status {r.status_code}, bytes {len(r.content)}")
print("== impact at depth", depth, "==")
H = {"Authorization": f"Bearer {tok}"}
r = cl.post(f"/api/v1/customers/{cid}/risk", headers=H, json={}); print(" mobile POST /customers/{id}/risk ->", r.status_code, r.text[:100])
r = cl.post(f"/api/v1/customers/{cid}/transactions", headers=H, json={"amount": 100, "currency": "AED", "direction": "in", "instrument": "cash"}); print(" mobile POST transaction ->", r.status_code, r.text[:100])
r = cl.get(f"/api/v1/customers/{cid}", headers=H); print(" mobile GET customer ->", r.status_code)
r = cl.get(f"/customers/{cid}/ubo-diagram") if False else None
print("== direct callers of ownership_state at this depth ==")
for fn in ("reassess_risk", "reassess_transaction_risk", "reassess_adverse_media"):
    f = getattr(M, fn, None)
    if f is None: print(f" {fn}: (not found)"); continue
    try:
        res = f(c, cid, B["org_id"], actor="probe") if fn != "complete_periodic_review" else f(c, cid, B["org_id"], actor="probe", note="x")
        print(f" {fn}: ok -> {getattr(res, 'rating', res)}")
    except RecursionError: print(f" {fn}: RecursionError")
    except Exception as e: print(f" {fn}: {type(e).__name__}: {str(e)[:80]}")
print("== determinism: ownership_state called 3x more at this depth ==")
for i in range(3):
    try: print("  ->", M.ownership_state(c, cid, B["org_id"], "legal"))
    except RecursionError: print("  -> RecursionError")
import inspect, amlkit.cases.manager as MM
print(" reassess_risk wraps ownership_state in try/except:", "try:" in inspect.getsource(MM.reassess_risk).split("ownership_state")[0][-300:])
print(" rows order from query (first 5 ids):", [r[0] for r in c.execute("select id from ubo_links where customer_id=? and org_id=? limit 5", (cid, B["org_id"])).fetchall()], "| EXPLAIN:", c.execute("explain query plan select id, parent_ubo_id from ubo_links where customer_id=? and org_id=?", (cid, B["org_id"])).fetchall()[0][-1])

"""Red-team 2026-11-14: web vs mobile parity for customer-side write routes (notes, UBO, transaction, close). The same hostile input goes through both surfaces, each on a fresh
copy of the seed DB; compare whether a row was stored. A mismatch = a validation that exists on one surface only. LOCAL ONLY (needs fixtures/ from PR #412 make_seed)."""
import json, os, shutil, sqlite3, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); B = ids["B"]; CID = B["customer_id"]
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.db import connect, _reset_init_cache
def env():
    db = Path(tempfile.mkdtemp())/"s.db"; os.environ["AMLKIT_DB"] = str(db); shutil.copy(ROOT/"fixtures"/"seed.db", db); _reset_init_cache(); limiter.reset()
    c = connect(db); tok = auth.create_session(c, B["mlro_id"], B["org_id"], mfa_verified=True); c.close()
    cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False); cl.cookies.set(auth.SESSION_COOKIE, tok); cl.get("/dashboard")
    return db, cl, {"Authorization": f"Bearer {tok}"}, cl.cookies.get(auth.CSRF_COOKIE)
count = lambda db, sql: sqlite3.connect(db).execute(sql, (B["org_id"],)).fetchone()[0]
def case(label, table_sql, web, mob):
    out = []
    for name, fn in (("web", web), ("mobile", mob)):
        db, cl, H, csrf = env(); n0 = count(db, table_sql); r = fn(cl, H, csrf); out.append((name, r.status_code, count(db, table_sql) - n0))
    same = (out[0][2] > 0) == (out[1][2] > 0); print(f"{'OK  ' if same else 'DIFF'} {label:44s} web: status {out[0][1]} stored {out[0][2]} | mobile: status {out[1][1]} stored {out[1][2]}")
N = "select count(*) from case_notes where org_id=?"; U = "select count(*) from ubo_links where org_id=?"; T = "select count(*) from transactions where org_id=?"
C = "select count(*) from customers where org_id=? and status='closed'"
for label, body in [("note: normal", "A normal case note"), ("note: empty", "   "), ("note: 1 MB", "N"*1_000_000), ("note: NUL + RLO", "x\x00y‮exe"), ("note: 10k chars", "N"*10_000)]:
    case(label, N, lambda cl, H, c, b=body: cl.post(f"/customers/{CID}/notes", data={"body": b, "csrf_token": c}), lambda cl, H, c, b=body: cl.post(f"/api/v1/customers/{CID}/notes", headers=H, json={"body": b}))
for label, pct, name in [("ubo: 30%", "30", "Pat Owner"), ("ubo: 150%", "150", "Pat Owner"), ("ubo: -5%", "-5", "Pat Owner"), ("ubo: 45% (seed already holds 60%) total>100", "45", "Pat Owner"),
                         ("ubo: blank name", "10", "  "), ("ubo: 5000-char name", "10", "P"*5000), ("ubo: self as owner (customer's own name)", "10", "BRAVO-SECRET Clean Customer")]:
    case(label, U, lambda cl, H, c, p=pct, n=name: cl.post(f"/customers/{CID}/ubo", data={"person_name": n, "ownership_pct": p, "csrf_token": c}),
         lambda cl, H, c, p=pct, n=name: cl.post(f"/api/v1/customers/{CID}/ubo", headers=H, json={"person_name": n, "ownership_pct": float(p)}))
for label, d in [("txn: normal cash in 1,000", dict(direction="in", method="cash", amount="1000")), ("txn: negative", dict(direction="in", method="cash", amount="-5")), ("txn: zero", dict(direction="in", method="cash", amount="0")),
                 ("txn: bad direction", dict(direction="sideways", method="cash", amount="10")), ("txn: bad method", dict(direction="in", method="crypto-magic", amount="10")), ("txn: bad currency 'XXXXXX'", dict(direction="in", method="cash", amount="10", currency="XXXXXX")),
                 ("txn: 1e30", dict(direction="in", method="cash", amount="1e30")), ("txn: future date 2099", dict(direction="in", method="cash", amount="10", occurred_at="2099-01-01")), ("txn: garbage date", dict(direction="in", method="cash", amount="10", occurred_at="yesterday"))]:
    case(label, T, lambda cl, H, c, d=d: cl.post(f"/customers/{CID}/transactions", data={**d, "csrf_token": c}), lambda cl, H, c, d=d: cl.post(f"/api/v1/customers/{CID}/transactions", headers=H, json={**d, "amount": float(d["amount"])}))
for label, reason in [("close: valid reason", "business_ended"), ("close: bogus reason", "because"), ("close: empty reason", "")]:
    case(label, C, lambda cl, H, c, r=reason: cl.post(f"/customers/{CID}/close", data={"exit_reason": r, "exit_note": "n", "csrf_token": c}), lambda cl, H, c, r=reason: cl.post(f"/api/v1/customers/{CID}/close", headers=H, json={"reason": r, "note": "n"}))

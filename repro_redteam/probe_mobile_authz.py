"""Red-team 2026-10-05: /api/v1 bearer-route auth matrix + alert paging edge cases on master 448a19b.
LOCAL ONLY. Needs fixtures/seed.db from PR #412's repro/make_seed.py. Never sends mail/network:
routes that fetch external data (refresh, adverse-media run, UAE PASS) are skipped."""
import json, os, re, shutil, sqlite3, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); A, B = ids["A"], ids["B"]
tmp = Path(tempfile.mkdtemp()); db = tmp/"s.db"; os.environ["AMLKIT_DB"] = str(db)
os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE", "test-invite")
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.db import connect, _reset_init_cache
def reset():
    for s in ("","-wal","-shm"): Path(str(db)+s).unlink(missing_ok=True)
    shutil.copy(ROOT/"fixtures"/"seed.db", db); _reset_init_cache(); limiter.reset()
def tok(org, who, mfa=True):
    c = connect(db); t = auth.create_session(c, org[f"{who}_id"], org["org_id"], mfa_verified=mfa); c.close(); return t
cl = TestClient(app, follow_redirects=False)
def call(m, path, token=None, **kw):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return cl.request(m, "/api/v1"+path, headers=h, **kw)

print("== 1. alert paging edge cases (as MLRO B) ==")
reset(); t = tok(B,"mlro")
for qs in ["", "?limit=0", "?limit=-5", "?limit=999999", "?offset=-1", "?offset=1000000000000", "?offset=99999999999999999999", "?limit=99999999999999999999", "?limit=abc", "?offset=1.5", "?status=all", "?status=x'%20OR%20'1'='1", "?status=open&limit=1&offset=1"]:
    try: r = call("GET", "/alerts"+qs, t); b = r.json() if r.headers.get("content-type","").startswith("application/json") else r.text[:60]; print(f" {qs:42s} -> {r.status_code}", {k:b[k] for k in ("total","limit","offset","truncated") if isinstance(b,dict) and k in b} or str(b)[:70])
    except Exception as e: print(f" {qs:42s} -> EXC {type(e).__name__}: {str(e)[:70]}")
print("== 1b. paging never crosses tenants ==")
reset(); t = tok(B,"mlro"); r = call("GET","/alerts?status=all",t).json()
print(" B sees", r["total"], "alerts; any ALPHA in payload:", "ALPHA" in json.dumps(r))
tot = sqlite3.connect(db).execute("select count(*) from alerts where org_id=?",(B["org_id"],)).fetchone()[0]; print(" DB count for org B:", tot)

print("== 2. auth matrix: no token / locked MLRO / officer / MLRO, every /api/v1 route ==")
SKIP = ("/auth/", "/admin/refresh", "/adverse-media/run-due", "/customers/scan-", "/reports", "/customers/{customer_id}/adverse-media")
src = (ROOT/"amlkit/api/mobile.py").read_text(encoding="utf-8-sig")
routes = [(m.upper(), p) for m,p in re.findall(r'@router\.(get|post|patch|delete)\("([^"]*)"', src)]
sub = lambda p: re.sub(r"\{(\w+)\}", lambda mo: str({"customer_id":B["customer_id"],"alert_id":B["alert_id"],"operator_id":B["officer_id"],"finding_id":B["finding_id"],"doc_id":B["doc_id"],"report_id":B["report_id"]}.get(mo.group(1),1)), p)
body = {"status":"false_positive","reason_code":"name_coincidence","note":"x","body":"x","direction":"in","method":"cash","amount":10,"person_name":"x","threshold":0.9,"name":"x","email":"x@y.ae","password":"A-long-password-1!","new_password":"A-long-password-1!","assigned_to":B["mlro_id"]}
rows = []
for m, p in routes:
    if any(s in p for s in SKIP): continue
    res = {}
    for actor in ("none","locked_mlro","officer","mlro"):
        reset(); t = {"none":None,"locked_mlro":tok(B,"mlro",mfa=False),"officer":tok(B,"officer"),"mlro":tok(B,"mlro")}[actor]
        try: r = call(m, sub(p), t, **({"json": body} if m != "GET" else {})); res[actor] = r.status_code
        except Exception as e: res[actor] = "EXC"
    rows.append((m,p,res))
bad_none = [r for r in rows if isinstance(r[2]["none"],int) and r[2]["none"] < 400]
bad_lock = [r for r in rows if isinstance(r[2]["locked_mlro"],int) and r[2]["locked_mlro"] < 400]
print(f" routes tested: {len(rows)}; reachable with NO token: {[(m,p) for m,p,_ in bad_none] or 'none'}")
print(f" reachable with MFA-LOCKED MLRO token: {[(m,p) for m,p,_ in bad_lock] or 'none'}")
print(" routes where OFFICER is refused (403) -> MLRO-only:", [f"{m} {p}" for m,p,r in rows if r["officer"]==403])
print(" officer 2xx on mutating routes:", [f"{m} {p}" for m,p,r in rows if m!="GET" and isinstance(r["officer"],int) and r["officer"]<300])
print(" 5xx/EXC anywhere:", [(m,p,r) for m,p,r in rows if any(v=="EXC" or (isinstance(v,int) and v>=500) for v in r.values())] or "none")
json.dump(rows, open(tmp/"matrix.json","w")); print(" full matrix:", tmp/"matrix.json")

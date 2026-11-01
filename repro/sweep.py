"""Exploratory sweep (NOT a repro): as org B's MLRO, hit every path-param route
(web + /api/v1) with org A's IDs, on a fresh scratch copy of fixtures/seed.db per
request. A control run with B's own IDs shows whether the payload is sufficient.
Reports 'LEAK' (response contains ALPHA) or 'MUTATED' (org A rows changed)."""
import hashlib, json, os, re, shutil, sqlite3, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT / "fixtures" / "seed_ids.json").read_text())
A, B = ids["A"], ids["B"]
tmp = Path(tempfile.mkdtemp())
db = tmp / "scratch.db"
os.environ["AMLKIT_DB"] = str(db)
os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE", "x")
(tmp / "documents").symlink_to(ROOT / "fixtures" / "documents") if (ROOT / "fixtures" / "documents").exists() else None

from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.db import connect, _reset_init_cache

def snapshot(org_id):
    c = sqlite3.connect(db); c.row_factory = sqlite3.Row
    out = {}
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
        cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
        if "org_id" in cols and t not in ("sessions", "audit_log", "auth_log"):
            rows = [tuple(r) for r in c.execute(f"SELECT * FROM {t} WHERE org_id=? ORDER BY 1", (org_id,))]
            out[t] = hashlib.sha1(repr(rows).encode()).hexdigest()
    c.close()
    return out

def fresh(operator="mlro"):
    for suf in ("", "-wal", "-shm"):
        Path(str(db) + suf).unlink(missing_ok=True)
    shutil.copy(ROOT / "fixtures" / "seed.db", db)
    _reset_init_cache()
    conn = connect(db)
    raw = auth.create_session(conn, B[f"{operator}_id"], B["org_id"], mfa_verified=True)
    conn.close()
    cl = TestClient(app, follow_redirects=False)
    cl.cookies.set(auth.SESSION_COOKIE, raw)
    cl.get("/")
    return cl, raw

PMAP = {"customer_id": "customer_id", "alert_id": "alert_id", "report_id": "report_id", "freeze_id": "freeze_id",
        "deadline_id": "deadline_id", "finding_id": "finding_id", "operator_id": "officer_id",
        "notification_id": "notif_id", "org_id": "org_id", "policy_id": "policy_id", "doc_id": "doc_id",
        "application_id": None}
FORMS = {
    "notes": {"body": "pwned-note"},
    "close": {"exit_reason": "pwned", "exit_date": "2026-01-01", "reason": "pwned"},
    "transactions": {"direction": "in", "method": "cash", "amount": "70000", "currency": "AED",
                     "counterparty_name": "pwned", "counterparty_country": "AE"},
    "ubo": {"person_name": "pwned-ubo", "ownership_pct": "10", "control_type": "ownership"},
    "signatures": {"purpose": "cdd", "statement": "pwned", "signer_name": "pwned", "signer_role": "customer",
                   "signature_data": "data:image/png;base64,AAAA"},
    "reset-password": {"new_password": "pwned-password-123"},
    "rename": {"name": "pwned"},
}
JSONB = {"transactions": {"direction": "in", "method": "cash", "amount": 70000, "currency": "AED"},
         "notes": {"body": "pwned-note"}, "ubo": {"person_name": "pwned-ubo", "ownership_pct": 10},
         "close": {"exit_reason": "pwned"}, "disposition": {"status": "false_positive", "reason_code": "name_coincidence"},
         "risk-factors": {"sector": "other"}, "reset-password": {"new_password": "pwned-password-123"},
         "signatures": {"purpose": "cdd", "statement": "pwned", "signer_name": "pwned"}}

def routes():
    seen = set()
    for r in app.routes:
        p = getattr(r, "path", None)
        if p and "{" in p and not p.startswith("/blog") and not p.startswith("/console"):
            for m in (r.methods or []):
                if m in ("GET", "POST", "PATCH", "DELETE"): seen.add((m, p))
    mob = (ROOT / "amlkit/api/mobile.py").read_text(encoding="utf-8-sig")
    for m, p in re.findall(r'@router\.(get|post|patch|delete)\("([^"]*\{[^"]*)"', mob):
        seen.add((m.upper(), "/api/v1" + p))
    return sorted(seen)

def run(m, p, src, mobile_ok=True):
    operator = "officer" if re.search(r"/(deactivate|reactivate|rename|reset-password)", p) else "mlro"
    cl, raw = fresh(operator)
    last = p.rstrip("/").split("/")[-1]
    def sub(mo):
        name = mo.group(1).split(":")[0]
        if name == "alert_id" and last in ("confirm",):
            return str(src["pending_alert_id"])
        if name == "operator_id":
            return str(src["officer_id"])
        k = PMAP.get(name)
        return str(src[k]) if k else "1"
    url = re.sub(r"\{([^}]+)\}", sub, p)
    org = src["org_id"]
    before = snapshot(org)
    csrf = cl.cookies.get(auth.CSRF_COOKIE)
    kw = {}
    is_api = p.startswith("/api/v1")
    if is_api:
        kw["headers"] = {"Authorization": f"Bearer {raw}"}
        if m != "GET":
            kw["json"] = JSONB.get(last, {"status": "false_positive", "reason_code": "name_coincidence", "note": "x"})
    elif m == "PATCH":
        kw = {"json": {"title": "pwned"}, "headers": {"X-CSRF-Token": csrf}}
    elif m != "GET":
        data = {"csrf_token": csrf, "status": "false_positive", "note": "x", "body": "x", "reason": "x",
                "notes": "x", "name": "pwned", "title": "pwned", "reason_code": "name_coincidence",
                "assigned_to": str(src["mlro_id"]), "operator_id": str(src["mlro_id"])}
        data.update(FORMS.get(last, {}))
        kw = {"data": data, "headers": {"X-CSRF-Token": csrf}}
    limiter.reset()
    loc = ""
    try:
        resp = cl.request(m, url, **kw)
        status, body, loc = resp.status_code, resp.text, resp.headers.get("location", "")
    except Exception as e:  # noqa
        status, body = "EXC", repr(e)
    after = snapshot(org)
    return url, status, loc, body, [t for t in before if before[t] != after.get(t)]

if __name__ == "__main__":
    hits = []
    for m, p in routes():
        curl, cst, cloc, cbody, cchg = run(m, p, B)
        url, st, loc, body, chg = run(m, p, A)
        leak = "ALPHA" in body
        flag = "LEAK" if leak else ("MUTATED" if chg else "")
        ctl = "ctl:mut" if cchg else ("ctl:BRAVO" if "BRAVO" in cbody else "ctl:inert")
        print(f"{st!s:>4} {m:6} {url:44} {flag:8} {ctl:10} ctl={cst}")
        if flag: hits.append((m, url, st, chg))
    print("\nHITS:", json.dumps(hits, indent=1))
    # Mechanical-verifier contract: exit 0 == defect reproduced, non-zero == not produced.
    sys.exit(0 if hits else 1)

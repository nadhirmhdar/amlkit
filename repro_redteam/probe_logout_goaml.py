"""Red-team 2026-10-06: (1) new logout CSRF behaviour (#424), (2) goAML XML export well-formedness with hostile field values.
LOCAL ONLY (needs fixtures/seed.db from PR #412's make_seed.py)."""
import json, os, shutil, sqlite3, sys, tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
B = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text())["B"]
tmp = Path(tempfile.mkdtemp()); db = tmp/"s.db"; os.environ["AMLKIT_DB"] = str(db); os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE","test-invite")
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.db import connect, _reset_init_cache
def reset():
    for s in ("","-wal","-shm"): Path(str(db)+s).unlink(missing_ok=True)
    shutil.copy(ROOT/"fixtures"/"seed.db", db); _reset_init_cache(); limiter.reset()
def login():
    c = connect(db); t = auth.create_session(c, B["mlro_id"], B["org_id"], mfa_verified=True); c.close()
    cl = TestClient(app, follow_redirects=False); cl.cookies.set(auth.SESSION_COOKIE, t); cl.get("/"); return cl, t
def alive(t):
    o = TestClient(app, follow_redirects=False); o.cookies.set(auth.SESSION_COOKIE, t); return o.get("/admin").status_code
print("== 1. logout CSRF ==")
reset(); cl, t = login(); r = cl.post("/logout", data={}); print(" no token      ->", r.status_code, r.headers.get("location"), "| session still valid:", alive(t) == 200)
reset(); cl, t = login(); r = cl.post("/logout", data={"csrf_token": "bad"}); print(" bad token     ->", r.status_code, r.headers.get("location"), "| session still valid:", alive(t) == 200)
reset(); cl, t = login(); r = cl.post("/logout", data={"csrf_token": cl.cookies.get(auth.CSRF_COOKIE)}); print(" valid token   ->", r.status_code, r.headers.get("location"), "| session still valid:", alive(t) == 200)
print("== 2. goAML export with hostile payload values ==")
reset(); cl, t = login()
con = sqlite3.connect(db); con.row_factory = sqlite3.Row
row = con.execute("select id, payload from reports where org_id=?", (B["org_id"],)).fetchone(); payload = json.loads(row["payload"])
print(" payload keys:", sorted(payload)[:14])
FREE = {"first_name","last_name","id_number","destination_account","entity_reference","reason_description","counterparty_name","address","entity_name","action_taken","notes"}
def walk(o, fn):
    if isinstance(o, dict): return {k: (fn(v) if k in FREE and isinstance(v, str) else walk(v, fn)) for k, v in o.items()}
    if isinstance(o, list): return [walk(v, fn) for v in o]
    return o
for label, ev in [("markup + entities", "<![CDATA[x]]></a><b>&amp;&#0;&lt;!DOCTYPE x [<!ENTITY y SYSTEM 'file:///etc/passwd'>]>&y;"),
                  ("XML-illegal control chars", "a\x00b\x0bc\x1fd￾퟿"), ("RLO + zero-width", "x‮​txt"), ("very long (1 MB)", "A"*1_000_000)]:
    p2 = walk(payload, lambda s: ev)
    con.execute("update reports set payload=? where id=?", (json.dumps(p2), row["id"])); con.commit()
    try:
        r = cl.get(f"/reports/{row['id']}/export")
        ok = None
        if r.status_code == 200:
            try: ET.fromstring(r.content); ok = "well-formed"
            except ET.ParseError as e: ok = f"NOT well-formed ({e})"
        print(f" {label:28s} -> {r.status_code} {ok or r.text[:90]!r} len={len(r.content)} etc/passwd leaked: {b'root:' in r.content}")
    except Exception as e: print(f" {label:28s} -> EXC {type(e).__name__}: {str(e)[:90]}")

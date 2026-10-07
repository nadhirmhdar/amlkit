"""Red-team 2026-10-06: XML-illegal control characters through the REAL save -> submit -> export path (#424 claims finalise validation).
LOCAL ONLY (needs fixtures/seed.db)."""
import json, os, shutil, sqlite3, sys, tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
B = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text())["B"]
tmp = Path(tempfile.mkdtemp()); db = tmp/"s.db"; os.environ["AMLKIT_DB"] = str(db); os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE","test-invite")
shutil.copy(ROOT/"fixtures"/"seed.db", db)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app
from amlkit.db import connect
from amlkit.cases.reports import save_report
c = connect(db)
t = auth.create_session(c, B["mlro_id"], B["org_id"], mfa_verified=True)
for label, bad in [("VT (\\x0b)", "Jo\x0bhn"), ("NUL (\\x00)", "Jo\x00hn"), ("U+FFFE", "Jo￾hn"), ("lone surrogate-ish U+D800 via json", "Jo\ud800hn"), ("ordinary", "John")]:
    try:
        rep = save_report(c, B["org_id"], "BRAVO-mlro", B["customer_id"], "STR", "Bravo Firm", "BRAVO-ENT", "BRAVO-mlro", "mlro@bravo.ae", bad, reason_description="r " + bad)
    except Exception as e: print(f" {label:34s} save_report -> {type(e).__name__}: {str(e)[:80]}"); continue
    if not rep.success: print(f" {label:34s} save_report refused: {rep.error}"); continue
    cl = TestClient(app, follow_redirects=False); cl.cookies.set(auth.SESSION_COOKIE, t); cl.get("/"); csrf = cl.cookies.get(auth.CSRF_COOKIE)
    s = cl.post(f"/reports/{rep.report_id}/submit", data={"csrf_token": csrf}); st = c.execute("select status from reports where id=?", (rep.report_id,)).fetchone()[0]
    x = cl.get(f"/reports/{rep.report_id}/export")
    wf = "n/a"
    if x.status_code == 200:
        try: ET.fromstring(x.content); wf = "well-formed"
        except ET.ParseError as e: wf = f"NOT well-formed ({e})"
    print(f" {label:34s} saved id={rep.report_id}; submit -> {s.status_code} status={st}; export -> {x.status_code} {wf}")

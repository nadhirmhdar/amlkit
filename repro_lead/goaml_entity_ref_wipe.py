"""Lead repro (2026-10-04): /admin never renders the saved goAML entity reference,
so the next org-profile save writes NULL over it (app.py:3182-3186 SELECT omits the
column; admin.html:53 renders it; app.py:3253-3267 writes the blank back). Exit 0 only when the defect reproduces. Scratch DB only."""
import os, sys, sqlite3, tempfile, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tests")]
os.environ["AMLKIT_DB"] = os.path.join(tempfile.mkdtemp(), "lead.db")
os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE", "test-invite")
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)
from fastapi.testclient import TestClient
from amlkit.api.app import app
from conftest import register_org

c = TestClient(app)
register_org(c, "Lead Firm", "lead_mlro", "mlro@lead.ae")
csrf = lambda: c.cookies.get("amlkit_csrf")
form = {"org_address": "Dubai", "reporting_person_name": "Lead MLRO",
        "reporting_person_title": "MLRO", "reporting_person_phone": "+971500000000"}
c.post("/admin/org-profile", data={**form, "goaml_entity_reference": "TEST-ORG-0001", "csrf_token": csrf()})
db = sqlite3.connect(os.environ["AMLKIT_DB"])
q = lambda: db.execute("SELECT goaml_entity_reference FROM organizations").fetchone()[0]
saved = q(); print("after first save:", saved)
page = c.get("/admin").text
m = re.search(r'name="goaml_entity_reference"\s+value="([^"]*)"', page)
shown = m.group(1) if m else None; print("/admin input value:", repr(shown))
# MLRO edits only the phone number and saves the form as rendered
c.post("/admin/org-profile", data={**form, "reporting_person_phone": "+971500000001",
                                   "goaml_entity_reference": shown or "", "csrf_token": csrf()})
after = q(); print("after second save (phone-only edit):", after)
sys.exit(0 if saved == "TEST-ORG-0001" and shown == "" and after is None else 1)

"""Lead 2026-10-16 checks. Local temp DB and synthetic data only; no network.

Exit 0 when ALL of these reproduce on the checked-out SHA:
  F6   - POST /feedback stores an unbounded message and page and has no rate
         limit (app.py:2942-2978: only an empty message is refused; no
         @limiter.limit). A 900 KB message is stored whole and 60 posts in a
         row all return 200.
  NT2  - the notifications page promises "Open one to go straight to the
         alert" (notifications.html:11) but the match notification links to
         the customer page's alerts section (notifications.py:62).
  NT3  - /alerts silently replaces an unknown sort or category with the
         default (app.py:2568-2570); no message tells the user.
Not run here: mlro-user S1/S2 (scan endpoints). They need the OCR stack
(passporteye/tesseract), which this venv lacks; verified by reading
app.py:1898-1905, 1935-1942 and app.js:358-362 instead.
Exit 1 when any of F6/NT2/NT3 is fixed (re-read the printed lines).
"""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ["AMLKIT_DB"] = os.path.join(tempfile.mkdtemp(), "web.db")
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = "test-invite"
os.environ.pop("AMLKIT_SMTP_HOST", None)

from fastapi.testclient import TestClient
from amlkit import db as dbm
from amlkit.api.app import app
from test_api import _register, _csrf

c = TestClient(app, raise_server_exceptions=False)
_register(c, "Org F", "Fay Lead", "fay@f.test")
ok = 0

big = "x" * 900_000
r = c.post("/feedback", data={"page": "p" * 50_000, "message": big, "csrf_token": _csrf(c)})
statuses = [c.post("/feedback", data={"page": "/d", "message": f"m{i}", "csrf_token": _csrf(c)}).status_code
            for i in range(60)]
w = dbm.connect(os.environ["AMLKIT_DB"])
stored = w.execute("SELECT MAX(length(message)), MAX(length(page)), COUNT(*) FROM feedback").fetchone()
f6 = r.status_code == 200 and stored[0] == len(big) and all(s == 200 for s in statuses)
print(f"F6   900 KB post status={r.status_code} stored message={stored[0]} page={stored[1]} rows={stored[2]}; "
      f"60 rapid posts non-200={[s for s in statuses if s != 200]} -> reproduces={f6}")
ok += f6

tpl = open(os.path.join(ROOT, "amlkit/web/templates/notifications.html"), encoding="utf-8").read()
src = open(os.path.join(ROOT, "amlkit/notifications.py"), encoding="utf-8").read()
nt2 = "straight to the alert" in tpl and '#alerts"' in src
print(f"NT2  copy says 'straight to the alert'={('straight to the alert' in tpl)}; "
      f"link is /customers/{{id}}#alerts={('#alerts' in src)} -> reproduces={nt2}")
ok += nt2

good = c.get("/alerts?sort=age_desc")
bad = c.get("/alerts?sort=bogus&category=bogus")
nt3 = bad.status_code == 200 and good.status_code == 200 and "bogus" not in bad.text
print(f"NT3  /alerts?sort=bogus&category=bogus -> {bad.status_code}, mentions the bad value={('bogus' in bad.text)} "
      f"-> reproduces={nt3}")
ok += nt3

sys.exit(0 if ok == 3 else 1)

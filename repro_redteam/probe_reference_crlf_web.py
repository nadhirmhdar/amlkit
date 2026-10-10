"""Red-team 2026-10-06: does POST /customers accept a CR/LF inside `reference`? LOCAL ONLY (needs fixtures/seed.db)."""
import json, os, shutil, sqlite3, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
B = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text())["B"]
tmp = Path(tempfile.mkdtemp()); db = tmp/"s.db"; os.environ["AMLKIT_DB"] = str(db); os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE","test-invite")
shutil.copy(ROOT/"fixtures"/"seed.db", db)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app
from amlkit.db import connect
c = connect(db); t = auth.create_session(c, B["mlro_id"], B["org_id"], mfa_verified=True); c.close()
cl = TestClient(app, follow_redirects=False); cl.cookies.set(auth.SESSION_COOKIE, t); cl.get("/new" if False else "/")
csrf = cl.cookies.get(auth.CSRF_COOKIE)
r = cl.post("/customers", data={"reference": "WEB-REF\r\nBcc: x@example.com", "full_name": "Clean Person", "customer_type": "natural", "csrf_token": csrf})
print(" POST /customers with CRLF in reference ->", r.status_code, r.headers.get("location"))
print(" stored:", [tuple(x) for x in sqlite3.connect(db).execute("select id, reference from customers where reference like 'WEB-REF%'")])

"""Lead repro, 2026-10-20. Exits 0 when every defect below reproduces.

New findings from today's role reports:
  B1w - web POST /customers/scan-passport decodes a tiny PNG with huge pixel
        dimensions in full: no byte cap, no pixel cap (no MAX_IMAGE_PIXELS
        anywhere in amlkit), no MIME check on this web route, no limiter.
        Measured as peak-RSS growth of this process (ru_maxrss).
  B1m - mobile POST /api/v1/customers/scan-passport accepts a 30 MB body of
        junk behind a PNG header (validate_file_mime is magic-bytes only)
        and answers 200.
  AU1 - /audit?page=99999999999999999999 -> unhandled OverflowError (500).
  AU2 - /audit?page=-1 -> 200 (no lower bound on page).
  AU3 - officer GET /audit/export -> bare 403, while /audit redirects.
  PV1 - /privacy says "three cookies" and does not name amlkit_trusted_device
        or amlkit_uaepass_state, both set by the app (auth.py:61, :65).

Local scratch DB only, no network. Needs passporteye installed (ocr.py
imports it at module level); tesseract is not needed for B1. Run from the
repo root:
  PYTHONPATH=.:tests python repro_lead/checks_2026_10_20.py
"""
import io, os, resource, sqlite3, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
tmp = tempfile.mkdtemp()
os.environ["AMLKIT_DB"] = os.path.join(tmp, "web.db")
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = "test-invite"
os.environ.pop("AMLKIT_SINGLE_OPERATOR_MODE", None)
import logging; logging.disable(logging.CRITICAL)

from PIL import Image
from amlkit import auth, db as dbm
from test_api import _seed_sanctions_data, _register, _csrf, _add_operator
from fastapi.testclient import TestClient
from amlkit.api.app import app, limiter

_seed_sanctions_data(os.environ["AMLKIT_DB"])
dbm._reset_init_cache(); limiter.reset()
ok, need = 0, 0


def maxrss_mb() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


cl = TestClient(app, raise_server_exceptions=False)
_register(cl, "Lead Firm", "Lena", "lena@lead.test")      # MLRO, MFA settled
c = sqlite3.connect(os.environ["AMLKIT_DB"]); c.row_factory = sqlite3.Row
mlro = c.execute("SELECT id, org_id FROM operators WHERE email='lena@lead.test'").fetchone()

# ---- B1w: 9000x9000 blank PNG through the web scan route -------------------
buf = io.BytesIO(); Image.new("L", (9000, 9000), 255).save(buf, "PNG", optimize=True)
png = buf.getvalue(); del buf
base = maxrss_mb()
r = cl.post("/customers/scan-passport", data={"csrf_token": _csrf(cl)},
            files={"passport_file": ("p.png", png, "image/png")})
grew = maxrss_mb() - base
b1w = r.status_code in (200, 400) and grew > 500
print(f"B1w web scan 9000x9000 PNG ({len(png)//1024} KB) -> {r.status_code}, peak RSS +{grew} MB -> reproduces={b1w}")
ok += b1w; need += 1

# ---- B1m: 30 MB junk with PNG magic through the mobile route ---------------
k = dbm.connect(os.environ["AMLKIT_DB"]); bt = auth.create_session(k, mlro["id"], mlro["org_id"], mfa_verified=True); k.close()
junk = b"\x89PNG\r\n\x1a\n" + b"\0" * (30 * 1024 * 1024)
r = cl.post("/api/v1/customers/scan-passport", headers={"Authorization": f"Bearer {bt}"},
            files={"passport_file": ("p.png", junk, "image/png")})
b1m = r.status_code == 200
print(f"B1m mobile scan 30 MB junk with PNG magic -> {r.status_code} (no size cap) -> reproduces={b1m}")
ok += b1m; need += 1

# ---- AU1 / AU2 --------------------------------------------------------------
r = cl.get("/audit?page=99999999999999999999")
au1 = r.status_code == 500
print(f"AU1 /audit?page=99999999999999999999 -> {r.status_code} -> reproduces={au1}")
ok += au1; need += 1
r = cl.get("/audit?page=-1", follow_redirects=False)
au2 = r.status_code == 200
print(f"AU2 /audit?page=-1 -> {r.status_code} (no lower bound) -> reproduces={au2}")
ok += au2; need += 1

# ---- AU3: officer on /audit vs /audit/export -------------------------------
_add_operator(cl, "Olly", "olly@lead.test")
oc = TestClient(app, raise_server_exceptions=False)
oc.get("/login")
oc.post("/login", data={"email": "olly@lead.test", "password": "a-strong-password-2", "csrf_token": _csrf(oc)})
ra = oc.get("/audit", follow_redirects=False)
re_ = oc.get("/audit/export", follow_redirects=False)
au3 = ra.status_code == 303 and re_.status_code == 403 and not re_.content
print(f"AU3 officer /audit -> {ra.status_code} {ra.headers.get('location')!r}; /audit/export -> {re_.status_code} body={len(re_.content)} bytes -> reproduces={au3}")
ok += au3; need += 1

# ---- PV1 --------------------------------------------------------------------
t = TestClient(app).get("/privacy").text
pv1 = "three cookies" in t and auth.TRUSTED_DEVICE_COOKIE not in t and auth.UAEPASS_STATE_COOKIE not in t
print(f"PV1 /privacy says 'three cookies'={'three cookies' in t}; names {auth.TRUSTED_DEVICE_COOKIE}="
      f"{auth.TRUSTED_DEVICE_COOKIE in t}, {auth.UAEPASS_STATE_COOKIE}={auth.UAEPASS_STATE_COOKIE in t} -> reproduces={pv1}")
ok += pv1; need += 1

print(f"exit={0 if ok == need else 1}")
sys.exit(0 if ok == need else 1)

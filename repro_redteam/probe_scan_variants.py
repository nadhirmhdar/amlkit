"""Red-team 2026-10-21: follow-up to B1 (2026-10-20). Run ONE case per process (clean RSS):  probe_scan_variants.py <case>
cases: web_licence_png | web_licence_junk | mobile_emirates_png | web_passport_junk | web_passport_png | mobile_pdf_hugepage. LOCAL ONLY (needs fixtures/ from PR #412 make_seed)."""
import io, json, os, resource, shutil, sys, tempfile, time, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
case = sys.argv[1]
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); B = ids["B"]
db = Path(tempfile.mkdtemp())/"s.db"; os.environ["AMLKIT_DB"] = str(db); shutil.copy(ROOT/"fixtures"/"seed.db", db)
import logging, warnings; logging.disable(logging.CRITICAL); warnings.simplefilter("ignore")
from PIL import Image
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.db import connect, _reset_init_cache
_reset_init_cache(); limiter.reset()
c = connect(db); t = auth.create_session(c, B["mlro_id"], B["org_id"], mfa_verified=True); c.close()
cl = TestClient(app, raise_server_exceptions=False); cl.cookies.set(auth.SESSION_COOKIE, t); cl.get("/dashboard")
H = {"Authorization": f"Bearer {t}"}; csrf = cl.cookies.get(auth.CSRF_COOKIE)
def png(w, h): b = io.BytesIO(); Image.new("L", (w, h), 255).save(b, "PNG", compress_level=9); return b.getvalue()
def pdf(w, h):  # minimal one-page PDF with a huge MediaBox (points); rasterised at 300 dpi
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>", b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 %d %d]>>" % (w, h)]
    out = b"%PDF-1.4\n"; offs = []
    for i, o in enumerate(objs, 1): offs.append(len(out)); out += b"%d 0 obj\n%s\nendobj\n" % (i, o)
    x = len(out); out += b"xref\n0 4\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % o for o in offs)
    return out + b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF" % x
t0 = time.time()
if case == "mobile_emirates_png": r = cl.post("/api/v1/customers/scan-emirates-id", files={"emirates_id_file": ("e.png", png(9000, 9000), "image/png")}, headers=H)
elif case == "web_licence_png": r = cl.post("/customers/scan-trade-licence", files={"licence_file": ("l.png", png(9000, 9000), "image/png")}, data={"csrf_token": csrf})
elif case == "web_licence_junk": r = cl.post("/customers/scan-trade-licence", files={"licence_file": ("l.exe", b"MZ" + os.urandom(1000), "application/octet-stream")}, data={"csrf_token": csrf})
elif case == "web_passport_png": r = cl.post("/customers/scan-passport", files={"passport_file": ("p.png", png(9000, 9000), "image/png")}, data={"csrf_token": csrf})
elif case == "web_passport_junk": r = cl.post("/customers/scan-passport", files={"passport_file": ("p.exe", b"MZ" + os.urandom(1000), "application/octet-stream")}, data={"csrf_token": csrf})
elif case == "mobile_pdf_hugepage": r = cl.post("/api/v1/customers/scan-passport", files={"passport_file": ("p.pdf", pdf(14400, 14400), "application/pdf")}, headers=H)
print(f"{case}: status {r.status_code} in {time.time()-t0:.1f}s, maxrss {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss//1024} MB, body: {r.text[:100]!r}")

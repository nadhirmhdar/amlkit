"""Red-team 2026-11-18: behaviour when Graphviz `dot` is missing or hangs/crashes (container image drift, PATH change). The customer page and the diagram helper must degrade, not 500.
LOCAL ONLY (needs fixtures/ from PR #412 make_seed)."""
import json, os, shutil, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); B = ids["B"]; CID = B["customer_id"]
db = Path(tempfile.mkdtemp())/"s.db"; os.environ["AMLKIT_DB"] = str(db); shutil.copy(ROOT/"fixtures"/"seed.db", db)
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app, limiter
from amlkit.cases.diagram import generate_ubo_diagram
from amlkit.db import connect, _reset_init_cache
_reset_init_cache(); limiter.reset(); c = connect(db); tok = auth.create_session(c, B["mlro_id"], B["org_id"], mfa_verified=True)
cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False); cl.cookies.set(auth.SESSION_COOKIE, tok)
t0 = time.time(); r = cl.get(f"/customers/{CID}"); print(f"with dot on PATH    : page {r.status_code} in {time.time()-t0:.2f}s, diagram present: {'<svg' in r.text}")
real = os.environ["PATH"]; os.environ["PATH"] = "/nonexistent"
try:
    t0 = time.time(); out = generate_ubo_diagram(c, CID, B["org_id"]); print(f"no dot: generate_ubo_diagram returned {type(out).__name__} {str(out)[:70]!r} in {time.time()-t0:.2f}s")
except Exception as e: print(f"no dot: generate_ubo_diagram RAISED {type(e).__name__}: {str(e)[:80]}")
t0 = time.time(); r = cl.get(f"/customers/{CID}"); print(f"no dot: customer page -> {r.status_code} in {time.time()-t0:.2f}s, page body {len(r.text)} bytes, mentions diagram problem: {'diagram' in r.text.lower() and ('unavailable' in r.text.lower() or 'could not' in r.text.lower())}")
d = Path(tempfile.mkdtemp()); (d/"dot").write_text("#!/bin/sh\nsleep 30\n"); (d/"dot").chmod(0o755); os.environ["PATH"] = f"{d}:{real}"
t0 = time.time(); r = cl.get(f"/customers/{CID}"); print(f"hanging dot (sleep 30): customer page -> {r.status_code} after {time.time()-t0:.1f}s")
(d/"dot").write_text("#!/bin/sh\necho garbage; exit 1\n"); t0 = time.time(); r = cl.get(f"/customers/{CID}"); print(f"failing dot (exit 1)  : customer page -> {r.status_code} after {time.time()-t0:.1f}s")

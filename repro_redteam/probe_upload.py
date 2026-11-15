"""Red-team 2026-10-10: document upload handling (POST /api/v1/customers/{id}/documents). LOCAL ONLY (needs fixtures/seed.db)."""
import hashlib, json, os, shutil, sqlite3, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
ids = json.loads((ROOT/"fixtures"/"seed_ids.json").read_text()); A, B = ids["A"], ids["B"]
tmp = Path(tempfile.mkdtemp()); db = tmp/"s.db"; os.environ["AMLKIT_DB"] = str(db); os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE","test-invite")
shutil.copy(ROOT/"fixtures"/"seed.db", db)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app
from amlkit.db import connect
c = connect(db); tok = auth.create_session(c, B["mlro_id"], B["org_id"], mfa_verified=True); c.close()
cl = TestClient(app, raise_server_exceptions=False); H = {"Authorization": f"Bearer {tok}"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00"*32; PDF = b"%PDF-1.4\n"
def up(name, content=PNG, cust=B["customer_id"], doc_type="passport"):
    return cl.post(f"/api/v1/customers/{cust}/documents", params={"doc_type": doc_type}, files={"file": (name, content, "application/octet-stream")}, headers=H)
def row(r): return (r.status_code, (r.json().get("detail") if r.status_code >= 400 and r.headers.get("content-type","").startswith("application/json") else r.text[:60]))
print("== 1. filename / content handling ==")
for label, name, content in [("valid png", "ok.png", PNG), ("PDF magic + .html name", "evil.html", PDF + b"<script>alert(1)</script>"), ("PNG magic + .svg name", "x.svg", PNG + b"<svg onload=alert(1)>"),
        ("PNG magic + .php name", "x.php", PNG + b"<?php system($_GET[0]);"), ("traversal ../../x.png", "../../x.png", PNG), ("backslash traversal", "..\\..\\x.png", PNG),
        ("filename ..", "..", PNG), ("filename .", ".", PNG), ("trailing slash a/", "a/", PNG), ("NUL in name", "a\x00.png", PNG), ("300-char name", "a"*300+".png", PNG),
        ("unicode RLO name", "x‮gnp.exe", PNG), ("not an image", "x.png", b"MZ" + b"\x00"*30), ("empty file", "e.png", b"")]:
    r = up(name, content); print(f" {label:26s} -> {row(r)}")
print("== 2. same filename overwrites the earlier blob (integrity) ==")
r1 = up("same.pdf", PDF + b"FIRST ORIGINAL EVIDENCE"); d1 = r1.json()["document_id"]; sha1 = r1.json()["sha256"]
r2 = up("same.pdf", PDF + b"SECOND REPLACEMENT"); d2 = r2.json()["document_id"]
dl = cl.get(f"/api/v1/customers/{B['customer_id']}/documents/{d1}", headers=H)
print(f" doc {d1} recorded sha256 {sha1[:12]}...; download of doc {d1} now returns sha256 {hashlib.sha256(dl.content).hexdigest()[:12]}... content={dl.content[-18:]!r}; matches recorded: {hashlib.sha256(dl.content).hexdigest()==sha1}")
print(" download headers:", {k: v for k, v in dl.headers.items() if k.lower() in ("content-type", "content-disposition", "x-content-type-options")})
print("== 3. metadata fields ==")
r = up("m.png", PNG, doc_type="x"*4000); print(f" 4 KB doc_type -> {row(r)}")
r = up("m2.png", PNG, doc_type="<img src=x onerror=alert(1)>"); print(f" html doc_type -> {row(r)}")
print("== 4. tenant ==")
r = up("t.png", PNG, cust=A["customer_id"]); print(f" org B uploads to org A customer -> {row(r)}")
print("== 5. size ==")
for mb in (10, 40):
    t = time.time(); r = up(f"big{mb}.png", PNG + b"\x00"*(mb*1024*1024)); print(f" {mb} MB -> {row(r)} in {time.time()-t:.1f}s")
print("== 6. stored markup in filename / doc_type: raw reflection on the web customer page? ==")
up('<img src=x onerror=alert(1)>.png', PNG, doc_type='<script>alert(2)</script>')
c = connect(db); st = auth.create_session(c, B["mlro_id"], B["org_id"], mfa_verified=True); c.close()
w = TestClient(app, follow_redirects=False); w.cookies.set(auth.SESSION_COOKIE, st)
body = w.get(f"/customers/{B['customer_id']}").text
print(f" page status ok: {'customer' in body.lower()}; filename shown: {'onerror' in body}; raw <img onerror: {'<img src=x onerror' in body}; raw <script>alert(2): {'<script>alert(2)' in body}")

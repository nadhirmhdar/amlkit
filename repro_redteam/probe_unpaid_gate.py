"""Red-team 2026-11-05: follow-up to SS2 (2026-11-04). With STRIPE_SECRET_KEY set and a fresh sanctions dataset present, what does an UNPAID
(pending_payment) org's MLRO still manage to create or consume? Customers (web+mobile), operators (web+mobile), UBOs, scans, transactions, reports, reactivation.
LOCAL ONLY; Stripe never contacted."""
import os, re, sqlite3, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
db = Path(tempfile.mkdtemp())/"s.db"
os.environ.update({"AMLKIT_DB": str(db), "STRIPE_SECRET_KEY": "sk_test_x", "STRIPE_WEBHOOK_SECRET": "whsec_x", "STRIPE_PRICE_STARTER": "price_s"})
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth, mail
from amlkit.api.app import app, limiter
from amlkit.db import connect
mail.send_verification_email = lambda to, name, tok: (sent.append(tok), mail.SENT)[1]; sent = []
cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False); cl.get("/register-organization"); limiter.reset()
cl.post("/register-organization", data={"org_name": "Unpaid Co", "name": "Una", "email": "una@unpaid.test", "password": "Str0ng!Passw0rd", "csrf_token": cl.cookies.get(auth.CSRF_COOKIE)})
c = connect(db)
# a fresh, non-empty mandatory screening dataset so onboarding reaches the billing check
c.execute("INSERT OR REPLACE INTO datasets (key, title, is_mandatory, last_refresh, entity_count, max_age_hours) VALUES ('un_sc_consolidated','UN',1,?,10,24)", (datetime.now(timezone.utc).isoformat(),)); c.commit()
op = c.execute("select id, org_id from operators where email='una@unpaid.test'").fetchone(); tok = auth.create_session(c, op[0], op[1], mfa_verified=True)
print("org:", tuple(c.execute("select plan, plan_status from organizations where id=?", (op[1],)).fetchone()), "| datasets fresh:", __import__("amlkit.ingest.loader", fromlist=["x"]).datasets_fresh(c)); c.close()
mc = TestClient(app, follow_redirects=False, raise_server_exceptions=False); mc.cookies.set(auth.SESSION_COOKIE, tok); mc.get("/dashboard"); H = {"Authorization": f"Bearer {tok}"}; csrf = mc.cookies.get(auth.CSRF_COOKIE)
def show(label, r): limiter.reset(); print(f" {label:46s} -> {r.status_code} {r.text[:110]!r}")
nat = {"reference": "R-1", "full_name": "Ann Test", "customer_type": "natural", "nationality": "AE", "country": "AE", "birth_date": "1990-01-01", "id_number": "784199012345678", "id_type": "emirates_id"}
show("mobile POST /customers (natural)", mc.post("/api/v1/customers", json=nat, headers=H)); limiter.reset()
show("mobile POST /customers (legal)", mc.post("/api/v1/customers", json={**nat, "reference": "R-2", "customer_type": "legal", "full_name": "Acme Ltd"}, headers=H))
show("web POST /customers", mc.post("/customers", data={**{k: v for k, v in nat.items()}, "reference": "R-3", "csrf_token": csrf}))
show("mobile POST /admin/operators", mc.post("/api/v1/admin/operators", json={"name": "B", "email": "b@unpaid.test", "password": "Str0ng!Passw0rd", "role": "officer"}, headers=H))
show("web POST /admin/operators", mc.post("/admin/operators", data={"name": "B", "email": "b2@unpaid.test", "password": "Str0ng!Passw0rd", "role": "officer", "csrf_token": csrf}))
print(" customers stored for the unpaid org:", sqlite3.connect(db).execute("select count(*) from customers where org_id=?", (op[1],)).fetchone()[0], "| operators:", sqlite3.connect(db).execute("select count(*) from operators where org_id=?", (op[1],)).fetchone()[0])
show("mobile POST /screen (still allowed? SS2)", mc.post("/api/v1/screen", json={"name": "Some Person"}, headers=H))
import io
from PIL import Image
b = io.BytesIO(); Image.new("L", (400, 300), 255).save(b, "PNG"); png = b.getvalue()
show("mobile POST /customers/scan-passport (unpaid)", mc.post("/api/v1/customers/scan-passport", files={"passport_file": ("p.png", png, "image/png")}, headers=H))
show("web POST /customers/scan-passport (unpaid)", mc.post("/customers/scan-passport", files={"passport_file": ("p.png", png, "image/png")}, data={"csrf_token": csrf}))
show("web POST /customers/scan-trade-licence (unpaid)", mc.post("/customers/scan-trade-licence", files={"licence_file": ("p.png", png, "image/png")}, data={"csrf_token": csrf}))
show("web POST /feedback (unpaid)", mc.post("/feedback", data={"page": "/x", "message": "hi", "csrf_token": csrf}))

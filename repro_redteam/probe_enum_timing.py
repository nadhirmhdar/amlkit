"""Red-team 2026-11-08: PR #462 sign-up enumeration fix -- are the responses for an existing vs a new address really indistinguishable (body, headers, Set-Cookie,
timing), and what does the existing-account notice mail do (mail-bomb vector)? Also gzip/BREACH on newly compressed public pages. LOCAL ONLY; Stripe never contacted."""
import os, re, statistics, sys, tempfile, time, gzip
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
db = Path(tempfile.mkdtemp())/"s.db"
os.environ.update({"AMLKIT_DB": str(db), "STRIPE_SECRET_KEY": "sk_test_x", "STRIPE_WEBHOOK_SECRET": "whsec_x", "STRIPE_PRICE_STARTER": "price_s"})
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth, mail
from amlkit.api.app import app, limiter
sent, notices = [], []
mail.send_verification_email = lambda to, name, tok: (sent.append(to), mail.SENT)[1]
for nm in [n for n in dir(mail) if "exist" in n.lower() or "notice" in n.lower() or "already" in n.lower()]: print("mail function:", nm)
cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False)
def reg(email, org, name="Eve"):
    c = TestClient(app, follow_redirects=False, raise_server_exceptions=False); c.get("/register-organization"); limiter.reset()
    t0 = time.perf_counter(); r = c.post("/register-organization", data={"org_name": org, "name": name, "email": email, "password": "Str0ng!Passw0rd", "csrf_token": c.cookies.get(auth.CSRF_COOKIE)}); return r, time.perf_counter()-t0
reg("owner@acme.test", "Acme Real")
norm = lambda t: re.sub(r"(csrf_token\"? value=\")[^\"]+|owner@acme\.test|new\d*@acme\.test|[0-9a-f]{20,}", "X", t)
ex = [reg("owner@acme.test", f"Squat {i}") for i in range(6)]; nw = [reg(f"new{i}@acme.test", f"Fresh {i}") for i in range(6)]
print("status existing/new:", {r.status_code for r, _ in ex}, {r.status_code for r, _ in nw})
print("bodies identical after masking:", {norm(r.text) for r, _ in ex} == {norm(r.text) for r, _ in nw} and len({norm(r.text) for r, _ in ex}) == 1)
hdr = lambda r: sorted((k.lower(), re.sub(r"=[^;]+", "=<v>", v)) for k, v in r.headers.items() if k.lower() in ("set-cookie", "location", "content-length"))
print("headers (set-cookie/location) equal:", hdr(ex[0][0]) == hdr(nw[0][0]))
tx, tn = [t for _, t in ex], [t for _, t in nw]
print(f"timing existing median {statistics.median(tx)*1000:.0f} ms  vs new {statistics.median(tn)*1000:.0f} ms  (a gap > ~50 ms is a usable oracle)")
print("verification mails queued:", sent[-6:])
print("== gzip/BREACH on pages now compressed (#460/#462) with Stripe ON ==")
for p in ["/", "/aml-law", "/pricing", "/about", "/privacy", "/blog"]:
    r = cl.get(p, headers={"Accept-Encoding": "gzip"}); b = r.text
    toks = [k for k, rx in {"csrf_input": r'name="csrf_token"', "form": r"<form", "session_cookie_name": r"amlkit_session"}.items() if re.search(rx, b)]
    print(f" {p:10s} {r.status_code} enc={r.headers.get('content-encoding')} vary={r.headers.get('vary')} secrets/forms in body: {toks}")
r = cl.get("/pricing?x=REFLECT_ME", headers={"Accept-Encoding": "gzip"}); print(" /pricing?x reflected:", "REFLECT_ME" in r.text)
r = cl.head("/about", headers={"Accept-Encoding": "gzip"}); print(" HEAD /about ->", r.status_code, r.headers.get("content-encoding"))
print("== header detail ==")
for label, (r, _) in (("existing", ex[0]), ("new", nw[0])):
    print(f" {label:9s}", {k: (re.sub(r'=[^;]{8,}', '=<v>', v) if k.lower() in ('set-cookie',) else v) for k, v in r.headers.items() if k.lower() in ('set-cookie', 'content-length', 'location')}, "len(body)", len(r.text), "len(masked)", len(norm(r.text)))
import difflib
a, b = norm(ex[0][0].text), norm(nw[0][0].text); print(" masked body diff lines:", [l for l in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0)][:6])

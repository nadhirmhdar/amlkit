"""Red-team 2026-10-24: PR #428 SelectiveGZipMiddleware (amlkit/api/compress.py). Which responses are gzip'd, and do any compressed responses carry a secret
(csrf token, session id, OAuth state) or reflect attacker input (BREACH preconditions)? Also path-confusion attempts to get a private page compressed. LOCAL ONLY."""
import gzip, os, re, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
os.environ["AMLKIT_DB"] = str(Path(tempfile.mkdtemp())/"s.db"); os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE", "x")
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit import auth
from amlkit.api.app import app
H = {"Accept-Encoding": "gzip"}
def body(r): return r.text  # httpx already decodes gzip; content-encoding header still shows what the server sent
def probe(cl, path, headers=None, cookies=None):
    r = cl.get(path, headers={**H, **(headers or {})}); b = body(r)
    secrets = [k for k, rx in {"csrf_input": r'name="csrf_token"', "csrf_value": r'csrf[^"\']*["\'][A-Za-z0-9_\-]{20,}', "state=": r'state=[A-Za-z0-9_\-]{16,}', "session": r'amlkit_session'}.items() if re.search(rx, b)]
    return r.status_code, r.headers.get("content-encoding", "-"), r.headers.get("vary", "-"), secrets
cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False)
print("== 1. anonymous: gzip? secrets in body? ==")
for p in ["/about", "/blog", "/blog?q=REFLECT_ME_123", "/blog/uae-goaml-str-sar-filing-guide", "/robots.txt", "/sitemap.xml", "/static/img/og-card.png", "/privacy", "/apply", "/login", "/register-organization"]:
    print(f" {p:44s}", probe(cl, p))
r = cl.get("/blog?q=REFLECT_ME_123", headers=H); print(" /blog?q reflected in body:", "REFLECT_ME_123" in body(r))
print("== 2. path confusion to get a private/secret page compressed ==")
for p in ["/blog/../login", "/blog/%2e%2e/login", "/about/", "/About", "//about", "/static/../login", "/static/%2e%2e/login", "/blog/x/../../apply", "/login;/about", "/apply?next=/blog", "/blog%2f..%2flogin"]:
    print(f" {p:34s}", probe(cl, p))
print("== 3. signed-in cookie => not compressed ==")
for ck in [f"{auth.SESSION_COOKIE}=abc", f"x=1; {auth.SESSION_COOKIE}=abc", f"{auth.SESSION_COOKIE.upper()}=abc"]:
    print(f" cookie {ck[:40]:42s}", probe(cl, "/blog", headers={"Cookie": ck}))
print("== 4. range / HEAD / other methods ==")
r = cl.head("/about", headers=H); print(" HEAD /about ->", r.status_code, r.headers.get("content-encoding"))
r = cl.post("/about", headers=H); print(" POST /about ->", r.status_code, r.headers.get("content-encoding"))

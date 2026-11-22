"""Red-team 2026-10-22: PR #427 (0d56f72) puts request.url.path into <link rel=canonical>/<og:url> on every page that does not override them.
Probe for markup injection via the path (decoded %22%3E...), on public, error and authenticated pages, and for noindex coverage of private pages. LOCAL ONLY."""
import os, re, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
os.environ["AMLKIT_DB"] = str(Path(tempfile.mkdtemp())/"s.db"); os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE", "x")
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit.api.app import app
cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False)
PAY = ['/%22%3E%3Cscript%3Ealert(1)%3C/script%3E', "/%27%20onload%3D%27alert(1)", '/blog/%22%3E%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E', '/%3C!--', '/about/%22%3E%3Csvg%20onload%3Dalert(1)%3E']
print("== 1. path injection into canonical / og:url ==")
for p in PAY:
    r = cl.get(p); h = r.text
    raw = bool(re.search(r'<script>alert\(1\)|<img src=x onerror|<svg onload|"\s*onload=', h)); can = re.findall(r'rel="canonical"[^>]*', h)
    print(f" {p[:44]:46s} -> {r.status_code}  raw-markup-in-html: {raw}  canonical: {can[:1]}")
print("== 2. canonical / robots on public + private pages ==")
for p in ["/", "/about", "/privacy", "/apply", "/login", "/register-organization", "/blog", "/blog?q=x", "/blog?topic=sanctions", "/dashboard", "/customers", "/sitemap.xml"]:
    r = cl.get(p); h = r.text
    print(f" {p:26s} {r.status_code}  canonical={bool(re.search('rel=.canonical', h))}  noindex={'noindex' in h}  loc={r.headers.get('location','')[:30]}")
print("== 3. query-string handling (canonical must not echo query) ==")
r = cl.get('/about?x="><script>alert(1)</script>'); print(" canonical:", re.findall(r'rel="canonical"[^>]*', r.text)[:1], "| raw script:", "<script>alert(1)" in r.text)

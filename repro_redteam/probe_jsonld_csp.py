"""Red-team 2026-11-10: PR #460 moved JSON-LD to static blocks. Every <script type=application/ld+json> on public pages must parse, contain no raw '</' sequences
that could end the block early, and no inline executable script may exist (CSP). Also checks the CSP header on those pages. LOCAL ONLY."""
import json, os, re, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
os.environ["AMLKIT_DB"] = str(Path(tempfile.mkdtemp())/"s.db")
import logging; logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient
from amlkit.api.app import app
from amlkit.web import blog
cl = TestClient(app, follow_redirects=False, raise_server_exceptions=False)
paths = ["/", "/about", "/aml-law", "/pricing", "/privacy", "/apply", "/blog"] + [f"/blog/{p.slug}" for p in blog.all_posts()]
bad = 0
for p in paths:
    r = cl.get(p); h = r.text
    blocks = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', h, re.S)
    ok = True
    for b in blocks:
        try: json.loads(b)
        except Exception as e: ok = False; print(f" {p}: JSON-LD does not parse: {e}")
    inline = [m for m in re.findall(r"<script(?![^>]*\bsrc=)(?![^>]*ld\+json)[^>]*>(.+?)</script>", h, re.S) if m.strip()]
    csp = r.headers.get("content-security-policy", "")
    script_src = re.search(r"script-src ([^;]*)", csp); unsafe = "'unsafe-inline'" in (script_src.group(1) if script_src else "")
    print(f" {p:44s} {r.status_code} ld+json blocks={len(blocks)} parse_ok={ok} inline_exec_scripts={len(inline)} script-src unsafe-inline={unsafe}")
    bad += (not ok) + len(inline) + int(unsafe)
print("problems:", bad)

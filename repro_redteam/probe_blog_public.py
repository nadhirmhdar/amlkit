"""Red-team 2026-10-05 run 2: unauthenticated probes of the public /blog surface added by #416 (master 28e4b51).
LOCAL ONLY (TestClient, scratch DB)."""
import html, json, os, re, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
os.environ["AMLKIT_DB"] = str(Path(tempfile.mkdtemp())/"s.db"); os.environ.setdefault("AMLKIT_REGISTRATION_INVITE_CODE","test-invite")
from fastapi.testclient import TestClient
from amlkit.api.app import app
from amlkit.web import blog
cl = TestClient(app, follow_redirects=False)
print("== 1. slug / topic / q handling ==")
for p in ["/blog/..%2f..%2fetc%2fpasswd", "/blog/%2e%2e/login", "/blog/..", "/blog/uae-sanctions-screening-24-hour-rule%00", "/blog/UAE-SANCTIONS-SCREENING-24-HOUR-RULE", "/blog/%252e%252e", "/blog/" + "a"*5000, "/blog?topic=../x", "/blog?topic=%00", "/blog?topic=" + "a"*5000]:
    try: r = cl.get(p); print(f" {p[:60]:62s} -> {r.status_code}")
    except Exception as e: print(f" {p[:60]:62s} -> EXC {type(e).__name__}: {str(e)[:60]}")
print("== 2. reflected q (unauthenticated) ==")
for q in ['<script>alert(1)</script>', '"><img src=x onerror=alert(1)>', "' onfocus='alert(1)", "{{7*7}}", "{% raw %}", "‮<b>"]:
    r = cl.get("/blog", params={"q": q}); body = r.text
    raw = q[:25] in body and html.escape(q)[:25] not in body
    print(f" q={q!r:44.44} -> {r.status_code}  raw (unescaped) reflection: {raw}  '49' rendered: {'49' in body and '7*7' in q}")
t = time.time(); cl.get("/blog", params={"q": "(a+)+$"*15}); cl.get("/blog", params={"q": "a"*100}); print(f" regex-ish / max-length q: {time.time()-t:.2f}s")
print("== 3. every post: inline script, JSON-LD, external links, headers ==")
for p in blog.all_posts():
    r = cl.get(f"/blog/{p.slug}"); b = r.text
    inline = [m for m in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", b, re.I) if "application/ld+json" not in m]
    ld = [a or b2 for a, b2 in re.findall(r"data-jsonld='([^']*)'|data-jsonld=\"([^\"]*)\"", b)]; ok = True
    for x in ld:
        try: json.loads(html.unescape(x))
        except Exception: ok = False
    ext = re.findall(r"<a\b[^>]*href=\"(https?://[^\"]+)\"[^>]*>", b)
    blank_no_rel = [a for a in re.findall(r"<a\b[^>]*>", b) if 'target="_blank"' in a and "noopener" not in a]
    http_links = [u for u in ext if u.startswith("http://")]
    print(f" {p.slug[:48]:50s} {r.status_code} inline_script={len(inline)} jsonld_ok={ok}({len(ld)}) ext_links={len(ext)} target_blank_without_noopener={len(blank_no_rel)} http_links={len(http_links)}")
r = cl.get("/blog/uae-goaml-str-sar-filing-guide")
for h in ("content-security-policy","x-content-type-options","x-frame-options","referrer-policy","cache-control"): print(f"  {h}: {r.headers.get(h,'<missing>')[:110]}")
print("== 4. methods ==")
print(" POST /blog ->", cl.post("/blog").status_code, "| POST /blog/<slug> ->", cl.post("/blog/uae-goaml-str-sar-filing-guide").status_code)

"""Lead repro, 2026-10-22. Exits 0 when every defect below reproduces.

New findings from today's role reports (all from PR #427, master 0d56f72):
  SE1 - (mlro-user SE1, skeptic, compliance CS-17, code-reviewer CR-19)
        a signed-in customer page titles itself with the customer's name,
        now also carries a canonical/og:url, and has no robots noindex;
        robots.txt is "Allow: /" with no Disallow for private paths.
  HC  - (skeptic "missed" #1) the canonical / og:url host is hard-coded to
        https://groaml.grovisor.ae (base.html:9,16), whatever host serves it.

Local scratch DB only, no network. Run from the repo root:
  PYTHONPATH=.:tests python repro_lead/checks_2026_10_22.py
"""
import os, re, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
tmp = tempfile.mkdtemp()
os.environ["AMLKIT_DB"] = os.path.join(tmp, "web.db")
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = "test-invite"
import logging; logging.disable(logging.CRITICAL)

from amlkit import db as dbm
from amlkit.cases.manager import onboard
from test_api import _seed_sanctions_data, _register
from fastapi.testclient import TestClient
from amlkit.api.app import app, limiter

_seed_sanctions_data(os.environ["AMLKIT_DB"])
dbm._reset_init_cache(); limiter.reset(); limiter.enabled = False
ok, need = 0, 0

cl = TestClient(app, raise_server_exceptions=False, base_url="http://staging.example.test")
_register(cl, "Lead Firm", "Lena", "lena@seo.test")
conn = dbm.connect(os.environ["AMLKIT_DB"])
org = conn.execute("SELECT org_id FROM operators WHERE email='lena@seo.test'").fetchone()[0]
cid = onboard(conn, org_id=org, reference="SEO-1", full_name="Fatima Testcase", actor="lead").customer_id
conn.commit(); conn.close()

# ---- SE1 --------------------------------------------------------------------
r = cl.get(f"/customers/{cid}", follow_redirects=False)
html = r.text
title = re.search(r"<title>(.*?)</title>", html, re.S)
title = title.group(1).strip() if title else None
robots_meta = re.search(r'<meta name="robots"[^>]*>', html)
canon = re.search(r'<link rel="canonical" href="([^"]+)"', html)
rt = cl.get("/robots.txt").text
need += 1
se1 = (r.status_code == 200 and title and "Fatima Testcase" in title and robots_meta is None
       and "X-Robots-Tag" not in r.headers and canon is not None and "Disallow" not in rt)
ok += bool(se1)
print(f"SE1 GET /customers/{cid} -> {r.status_code} title={title!r} robots_meta={bool(robots_meta)} "
      f"canonical={canon.group(1) if canon else None!r}; robots.txt={rt!r} -> reproduces={bool(se1)}")

# ---- HC ---------------------------------------------------------------------
r = cl.get("/about")
canon = re.search(r'<link rel="canonical" href="([^"]+)"', r.text)
ogurl = re.search(r'<meta property="og:url" content="([^"]+)"', r.text)
need += 1
hc = bool(canon and ogurl and canon.group(1).startswith("https://groaml.grovisor.ae")
          and ogurl.group(1).startswith("https://groaml.grovisor.ae"))
ok += hc
print(f"HC  served from staging.example.test: canonical={canon.group(1) if canon else None!r} "
      f"og:url={ogurl.group(1) if ogurl else None!r} -> reproduces={hc}")

print(f"{ok}/{need} reproduce")
sys.exit(0 if ok == need else 1)

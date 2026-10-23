"""Lead repro, 2026-10-23. Exits 0 when every defect below reproduces.

New findings from today's role reports (master 0d56f72, unchanged):
  AX2 - (mlro-user AX2, skeptic) GET /customers/{id}/gdelt-bq and /kg-screen
        answer HTTP 200 with empty results and status "unconfigured".
  AX3 - (mlro-user AX3, skeptic) with the screeners configured, both send the
        customer's full name out of process and write no audit_log row.
  KQ  - (lead, new) knowledge_graph.py builds the request URL by f-string with
        the raw name: '&' / '#' in a name injects or truncates query params.
  TL  - (red-team B2 extended, skeptic) web POST /customers/scan-trade-licence
        accepts a non-image .exe blob and answers 200 (no MIME / size check).

Outbound calls are monkeypatched; nothing leaves the machine. Local scratch DB.
Run from the repo root:
  PYTHONPATH=.:tests python repro_lead/checks_2026_10_23.py
"""
import os, sys, tempfile
from urllib.parse import urlsplit, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
tmp = tempfile.mkdtemp()
os.environ["AMLKIT_DB"] = os.path.join(tmp, "web.db")
os.environ["AMLKIT_REGISTRATION_INVITE_CODE"] = "test-invite"
os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
os.environ.pop("GOOGLE_KG_API_KEY", None)
import logging; logging.disable(logging.CRITICAL)

from amlkit import db as dbm
from amlkit.cases.manager import onboard
from test_api import _seed_sanctions_data, _register, _csrf
from fastapi.testclient import TestClient
from amlkit.api.app import app, limiter
from amlkit.screening import knowledge_graph as kgmod, gdelt_bq as bqmod

_seed_sanctions_data(os.environ["AMLKIT_DB"])
dbm._reset_init_cache(); limiter.reset(); limiter.enabled = False
ok, need = 0, 0

cl = TestClient(app, raise_server_exceptions=False)
_register(cl, "Lead Firm", "Lena", "lena@ax.test")
conn = dbm.connect(os.environ["AMLKIT_DB"])
org = conn.execute("SELECT org_id FROM operators WHERE email='lena@ax.test'").fetchone()[0]
cid = onboard(conn, org_id=org, reference="AX-1", full_name="Fatima Testcase", actor="lead").customer_id
cid2 = onboard(conn, org_id=org, reference="AX-2", full_name="Acme & Co #1", actor="lead").customer_id
conn.commit(); conn.close()


def audit_count():
    c = dbm.connect(os.environ["AMLKIT_DB"])
    n = c.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    c.close()
    return n


# ---- AX2 --------------------------------------------------------------------
a = cl.get(f"/customers/{cid}/gdelt-bq")
b = cl.get(f"/customers/{cid}/kg-screen")
need += 1
ax2 = (a.status_code == 200 and a.json().get("status") == "unconfigured"
       and b.status_code == 200 and b.json().get("status") == "unconfigured")
ok += ax2
print(f"AX2 unconfigured: gdelt-bq -> {a.status_code} {a.json()}; kg-screen -> {b.status_code} {b.json()} -> reproduces={ax2}")

# ---- AX3 + KQ -----------------------------------------------------------------
sent = []


class _Resp:
    def raise_for_status(self): pass
    def json(self): return {"itemListElement": []}


def fake_get(url, **kw):
    sent.append(url)
    return _Resp()


class _Job:
    def result(self): return []


class _Client:
    def query(self, q):
        sent.append(q)
        return _Job()


kgmod.httpx.get = fake_get
bqmod._make_bq_client = lambda project: _Client()
os.environ["GOOGLE_KG_API_KEY"] = "dummy-not-a-key"
os.environ["GOOGLE_CLOUD_PROJECT"] = "dummy-project"

before = audit_count()
a = cl.get(f"/customers/{cid}/kg-screen")
b = cl.get(f"/customers/{cid}/gdelt-bq")
after = audit_count()
need += 1
ax3 = (a.status_code == 200 and b.status_code == 200 and len(sent) == 2
       and "Fatima Testcase" in sent[0] and "Fatima Testcase" in sent[1] and after == before)
ok += ax3
print(f"AX3 configured: kg -> {a.status_code}, bq -> {b.status_code}; name in outbound kg URL={'Fatima Testcase' in sent[0]}, "
      f"in BQ SQL={'Fatima Testcase' in sent[1]}; audit_log rows before={before} after={after} -> reproduces={ax3}")

sent.clear()
r = cl.get(f"/customers/{cid2}/kg-screen")
parts = urlsplit(sent[0]) if sent else None
qs = parse_qs(parts.query) if parts else {}
need += 1
kq = bool(parts) and qs.get("query") != ["Acme & Co #1"] and "key" not in qs
ok += kq
print(f"KQ  name 'Acme & Co #1' -> kg URL query params={sorted(qs)} query={qs.get('query')} "
      f"fragment={parts.fragment if parts else None!r} (key param lost) -> reproduces={kq}")

# ---- TL ---------------------------------------------------------------------
r = cl.post("/customers/scan-trade-licence", data={"csrf_token": _csrf(cl)},
            files={"licence_file": ("l.exe", b"MZ\x90\x00" + b"\x00" * 4096, "application/octet-stream")})
need += 1
tl = r.status_code == 200
ok += tl
print(f"TL  web scan-trade-licence with MZ .exe blob -> {r.status_code} body={r.text[:120]!r} -> reproduces={tl}")

print(f"{ok}/{need} reproduce")
sys.exit(0 if ok == need else 1)

"""Exploratory: as org B (mlro and officer), GET every param-less route (web + /api/v1)
with ALPHA search terms; report any response containing the org-A marker 'ALPHA'
(excluding B's own text). Controls: same pass as org A must contain 'ALPHA'."""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep
from sweep import *  # noqa

def paths():
    out = set()
    for r in app.routes:
        p = getattr(r, "path", None)
        if p and "{" not in p and "GET" in (getattr(r, "methods", None) or []):
            out.add(p)
    mob = (ROOT / "amlkit/api/mobile.py").read_text(encoding="utf-8-sig")
    for p in re.findall(r'@router\.get\("([^"{]*)"', mob):
        out.add("/api/v1" + p)
    return sorted(out)

def fresh_as(org, operator):
    global B
    saved = sweep.B
    sweep.B = ids[org]
    try:
        return sweep.fresh(operator)
    finally:
        sweep.B = saved

skip = ("/logout", "/refresh", "/static", "/docs", "/openapi", "/redoc", "/healthz", "/health")
hits = 0
for who, operator in (("B", "mlro"), ("B", "officer"), ("A", "mlro")):
    cl, raw = fresh_as(who, operator)
    n = leaks = 0
    for p in paths():
        if any(s in p for s in skip): continue
        hdr = {"Authorization": f"Bearer {raw}"} if p.startswith("/api/v1") else {}
        limiter.reset()
        try:
            r = cl.get(p, params={"q": "Clean", "query": "Clean", "name": "Clean", "search": "Clean", "status": "all"}, headers=hdr)
        except Exception as e:
            continue
        n += 1
        if "ALPHA" in r.text and who == "B":
            leaks += 1; hits += 1
            i = r.text.index("ALPHA")
            print(f"LEAK as {who}/{operator}: GET {p} [{r.status_code}] ...{r.text[max(0,i-60):i+60]!r}")
        elif who == "A" and "ALPHA" in r.text:
            leaks += 1
    print(f"{who}/{operator}: {n} routes fetched, {leaks} containing ALPHA")
print("TOTAL B->A leaks:", hits)
sys.exit(0 if hits else 1)  # 0 == defect reproduced

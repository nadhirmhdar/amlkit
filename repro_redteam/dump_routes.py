"""Red-team 2026-11-03: dump (method, path, endpoint, rate limits, middleware) of the app, to diff before/after the #456 router split. LOCAL ONLY."""
import json, os, sys, tempfile
from pathlib import Path
root = Path(sys.argv[1]).resolve(); sys.path.insert(0, str(root))
os.environ["AMLKIT_DB"] = str(Path(tempfile.mkdtemp())/"s.db")
import logging; logging.disable(logging.CRITICAL)
from amlkit.api.app import app
from amlkit.api.limits import limiter
lims = {}
for store in (getattr(limiter, "_route_limits", {}), ):
    for k, v in store.items(): lims[k.split(".")[-1]] = sorted(str(getattr(l, "limit", l)) for l in v)
rows = []
def walk(routes, prefix=""):
    for r in routes:
        if type(r).__name__ == "_IncludedRouter":
            inc = getattr(r, "include_context", None); pre = getattr(inc, "prefix", "") or ""
            for ctx in r.effective_route_contexts():
                rt = getattr(ctx, "route", ctx)
                emit(rt, getattr(ctx, "path", None) or (pre + getattr(rt, "path", "?")))
        elif hasattr(r, "path"): emit(r, r.path)
def emit(r, path):
    for m in sorted(getattr(r, "methods", None) or ["WS"]):
        name = getattr(r, "name", "?"); rows.append((m, path, name, lims.get(name, [])))
walk(app.routes)
mw = [m.cls.__name__ if hasattr(m, "cls") else str(m) for m in app.user_middleware]
print(json.dumps({"routes": sorted(rows), "middleware": mw, "http_middleware_count": len(getattr(app, "user_middleware", []))}, indent=1))

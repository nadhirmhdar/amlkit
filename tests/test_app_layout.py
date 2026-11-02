"""Layout guard for the api/app.py -> routers split (WP-18, issue #73).

The split is a pure move: the registered route set, the relative order of any
two routes that could shadow each other, and every per-route rate limit must
equal the snapshots taken from master before the move
(tests/data/routes_master.json, tests/data/route_limits_master.json).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.routing import _EffectiveRouteContext, _IncludedRouter

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"
APP_MAX_LINES = 600
ROUTER_MAX_LINES = 900


def _flatten(routes):
    """Yield (path, methods, endpoint) for every route, resolving include_router()."""
    for r in routes:
        if isinstance(r, _IncludedRouter):
            yield from _flatten(r.effective_candidates())
        elif isinstance(r, _EffectiveRouteContext):
            orig = r.original_route
            path = r.path or getattr(r.starlette_route, "path", None) or getattr(orig, "path", None)
            methods = r.methods or getattr(r.starlette_route, "methods", None) or getattr(orig, "methods", None)
            yield path, methods, r.endpoint or getattr(orig, "endpoint", None)
        else:
            yield getattr(r, "path", None), getattr(r, "methods", None), getattr(r, "endpoint", None)


def _registered():
    from amlkit.api.app import app

    out = []
    for path, methods, endpoint in _flatten(app.router.routes):
        if not methods:
            continue  # the /static mount
        for m in sorted(set(methods) - {"HEAD", "OPTIONS"}):
            out.append((m, path, endpoint))
    return out


def _limits_for(endpoint):
    from amlkit.api.limits import limiter

    name = f"{endpoint.__module__}.{endpoint.__name__}"
    static = limiter._route_limits.get(name, [])
    dynamic = limiter._dynamic_route_limits.get(name, [])
    return sorted(
        [f"{l.limit}|{getattr(l.key_func, '__name__', repr(l.key_func))}|{l.scope}|{l.per_method}|{l.override_defaults}"
         for l in static]
        + [f"dynamic:{d}" for d in dynamic]
    )


def test_app_py_is_wiring_only():
    n = len((ROOT / "amlkit" / "api" / "app.py").read_text(encoding="utf-8").splitlines())
    assert n <= APP_MAX_LINES, f"app.py is {n} lines; limit {APP_MAX_LINES}"


def test_router_modules_stay_small():
    files = sorted((ROOT / "amlkit" / "api" / "routers").glob("*.py"))
    assert len(files) > 5
    too_big = {
        f.name: n for f in files
        if (n := len(f.read_text(encoding="utf-8").splitlines())) > ROUTER_MAX_LINES
    }
    assert not too_big, f"router modules over {ROUTER_MAX_LINES} lines: {too_big}"


def test_every_router_module_exposes_router():
    import importlib

    from fastapi import APIRouter

    for f in sorted((ROOT / "amlkit" / "api" / "routers").glob("*.py")):
        if f.name == "__init__.py":
            continue
        mod = importlib.import_module(f"amlkit.api.routers.{f.stem}")
        assert isinstance(mod.router, APIRouter), f.name


def test_route_set_matches_master_snapshot():
    expected = {tuple(x) for x in json.loads((DATA / "routes_master.json").read_text())}
    actual = {(m, p) for m, p, _ in _registered()}
    assert actual - expected == set(), f"new routes not on master: {sorted(actual - expected)}"
    assert expected - actual == set(), f"routes dropped or renamed: {sorted(expected - actual)}"


def test_no_duplicate_method_path_pairs():
    pairs = [(m, p) for m, p, _ in _registered()]
    dupes = sorted({x for x in pairs if pairs.count(x) > 1})
    assert not dupes, f"duplicate (method, path) registrations: {dupes}"


def _pattern(path: str):
    return re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", path) + "$")


def test_overlapping_routes_keep_master_order():
    """Where two same-method routes could match the same URL, the one that came
    first on master must still come first (static-vs-parameterised shadowing)."""
    master = [tuple(x) for x in json.loads((DATA / "routes_master.json").read_text())]
    now = [(m, p) for m, p, _ in _registered()]
    pos_master = {r: i for i, r in enumerate(master)}
    pos_now = {r: i for i, r in enumerate(now)}
    bad = []
    for i, (m1, p1) in enumerate(master):
        for m2, p2 in master[i + 1:]:
            if m1 != m2 or p1 == p2:
                continue
            probe1 = re.sub(r"\{[^}]+\}", "x", p1)
            probe2 = re.sub(r"\{[^}]+\}", "x", p2)
            if _pattern(p2).match(probe1) or _pattern(p1).match(probe2):
                if pos_now[(m1, p1)] > pos_now[(m2, p2)]:
                    bad.append((m1, p1, p2))
    assert not bad, f"overlapping routes were reordered: {bad}"
    assert set(pos_master) == set(pos_now)


def test_rate_limits_match_master_snapshot():
    expected = json.loads((DATA / "route_limits_master.json").read_text())
    actual = {}
    for m, p, endpoint in _registered():
        lim = _limits_for(endpoint)
        if lim:
            actual[f"{m} {p}"] = lim
    assert actual == expected

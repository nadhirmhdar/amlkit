"""Static guard against tenant-config leakage (Issue #266).

Recurring defect class: state that must be scoped per org_id (config flags,
session defaults) read from process-global context (env / session) in code that
has no org_id in scope. Fails on any NEW unlisted hit; add genuine
deployment-wide reads to tests/tenant_scan_allowlist.txt with a reason.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = Path(__file__).resolve().parent / "tenant_scan_allowlist.txt"
SCAN_ROOTS = ["amlkit/cases", "amlkit/queries.py", "amlkit/reporting", "amlkit/screening"]


def _files(roots):
    for r in roots:
        p = ROOT / r
        yield from ([p] if p.is_file() else sorted(p.rglob("*.py")))


def _params(fn) -> set[str]:
    a = fn.args
    return {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}


def find_hits(source: str, relpath: str) -> list[tuple[str, int]]:
    """Return (key, lineno) for each env/session use outside an org_id function."""
    hits: list[tuple[str, int]] = []

    def visit(node, stack):
        for c in ast.iter_child_nodes(node):
            s = stack
            if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef)):
                s = stack + [c]
            if isinstance(c, ast.Attribute) and isinstance(c.value, ast.Name):
                is_env = c.value.id == "os" and c.attr in ("environ", "getenv")
                is_sess = c.value.id == "session"
                if (is_env or is_sess) and not any("org_id" in _params(f) for f in stack):
                    fname = stack[-1].name if stack else "<module>"
                    hits.append((f"{relpath}::{fname}::{c.attr}", c.lineno))
            visit(c, s)

    visit(ast.parse(source), [])
    return hits


def _allowlist() -> set[str]:
    out = set()
    for line in ALLOWLIST.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, reason = line.partition("#")
        assert reason.strip(), f"allow-list entry needs a reason: {line}"
        out.add(key.strip())
    return out


def test_no_unlisted_env_or_session_reads():
    allowed = _allowlist()
    seen, bad = set(), []
    for f in _files(SCAN_ROOTS):
        rel = f.relative_to(ROOT).as_posix()
        for key, line in find_hits(f.read_text(encoding="utf-8-sig"), rel):
            seen.add(key)
            if key not in allowed:
                bad.append(f"{key} (line {line})")
    assert not bad, (
        "env/session read outside an org_id-scoped function (tenant-config leak risk, #266); "
        "scope it per org or add to tests/tenant_scan_allowlist.txt with a reason:\n  "
        + "\n  ".join(bad)
    )
    stale = allowed - seen
    assert not stale, f"stale allow-list entries, remove them: {sorted(stale)}"


def test_scanner_flags_new_hits():
    src = (
        "import os\n"
        "def leaky(conn):\n    return os.environ.get('X')\n"
        "def ok(conn, org_id):\n    return os.getenv('X')\n"
        "def sess(customer):\n    return session.org_name\n"
        "def nested(org_id):\n    def inner():\n        return os.environ['Y']\n    return inner\n"
    )
    keys = [k for k, _ in find_hits(src, "m.py")]
    assert keys == ["m.py::leaky::environ", "m.py::sess::org_name"]


def test_single_operator_mode_only_via_per_org_helper():
    """The env var, the org_settings column and the helper are read in one place."""
    problems = []
    for f in _files(["amlkit"]):
        rel = f.relative_to(ROOT).as_posix()
        tree = ast.parse(f.read_text(encoding="utf-8-sig"))
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                v = n.value
                if "AMLKIT_SINGLE_OPERATOR_MODE" in v and rel not in ("amlkit/cases/review.py", "amlkit/db.py"):
                    # db.py only mentions it in a docstring
                    problems.append(f"{rel}:{n.lineno} reads the process-wide env var")
                if ("single_operator_mode" in v and "SELECT" in v.upper()
                        and rel not in ("amlkit/cases/review.py", "amlkit/queries.py")):
                    problems.append(f"{rel}:{n.lineno} reads org_settings.single_operator_mode directly")
            if isinstance(n, ast.Call):
                fn = n.func
                name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
                if name == "env_single_operator_default" and rel != "amlkit/cases/review.py":
                    problems.append(f"{rel}:{n.lineno} calls env_single_operator_default")
                if name == "single_operator_mode" and len(n.args) + len(n.keywords) != 2:
                    problems.append(f"{rel}:{n.lineno} calls single_operator_mode without (conn, org_id)")
    assert not problems, "\n".join(problems)

"""CR-31: the runtime requirements (installed in the production image) must not
carry test-only packages; those live in requirements-dev.txt."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_ONLY = ("pytest", "hypothesis")


def _names(path: Path) -> list[str]:
    out = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        out.append(re.split(r"[<>=!~\[;\s]", line, maxsplit=1)[0].lower().replace("_", "-"))
    return out


def _is_test_only(name: str) -> bool:
    return name in TEST_ONLY or name.startswith("pytest")


def test_runtime_requirements_have_no_test_only_packages():
    bad = [n for n in _names(ROOT / "requirements.txt") if _is_test_only(n)]
    assert bad == []


def test_dev_requirements_carry_them_and_include_runtime():
    dev = ROOT / "requirements-dev.txt"
    names = _names(dev)
    assert "pytest" in names and "hypothesis" in names
    assert "-r requirements.txt" in dev.read_text()


def test_dockerfile_does_not_install_dev_requirements():
    assert "requirements-dev" not in (ROOT / "Dockerfile").read_text()


def test_ci_installs_dev_requirements():
    wf = (ROOT / ".github" / "workflows" / "tests.yml").read_text()
    assert "pip install -r requirements-dev.txt" in wf

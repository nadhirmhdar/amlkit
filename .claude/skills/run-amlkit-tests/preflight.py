"""Check this machine can run the full amlkit test suite, before spending 40 minutes on it.

    .venv/Scripts/python.exe .claude/skills/run-amlkit-tests/preflight.py

Exit 0 when ready; otherwise prints each missing piece and the command that fixes it.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

problems: list[tuple[str, str]] = []

# Python packages the tests import (all are in requirements.txt; a stale venv misses new ones).
for mod, why in [("pypdfium2", "PDF scans for OCR (tests/test_ocr_pdf_support.py, test_trade_licence_scan.py)"),
                 ("graphviz", "UBO ownership diagrams (tests/test_diagram.py)"),
                 ("PIL", "image handling for OCR"),
                 ("pyotp", "MFA in the signed-in test fixtures")]:
    if importlib.util.find_spec(mod) is None:
        problems.append((f"Python package '{mod}' missing -- {why}",
                         ".venv/Scripts/python.exe -m pip install -r requirements.txt"))

# Graphviz's `dot` binary (the Dockerfile installs it; a dev PC usually lacks it).
dot = shutil.which("dot")
if not dot:
    fallback = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Graphviz" / "bin" / "dot.exe"
    if fallback.exists():
        problems.append((f"Graphviz is installed but not on PATH ({fallback.parent})",
                         'add it for the run:  PATH="/c/Program Files/Graphviz/bin:$PATH" (Git Bash) -- or open a new terminal'))
    else:
        problems.append(("Graphviz `dot` not found -- tests/test_diagram.py needs it",
                         "winget install --id Graphviz.Graphviz -e"))

if problems:
    for what, fix in problems:
        print(f"MISSING  {what}\n   fix:  {fix}")
    sys.exit(1)
print("ready: all test dependencies present" + (f" (dot: {dot})" if dot else ""))

---
name: run-amlkit-tests
description: Set up and run the amlkit (groAML) test suite on a Windows dev machine. Use whenever you run, rerun or debug amlkit tests, see failures in OCR/PDF, diagram, form-label, rescreen or retention tests, or before saying the full suite passes.
---

# Run the amlkit tests (Windows dev machine)

Paths are relative to the repo root. Run everything with the repo's venv Python. The full suite takes about 40 minutes (1,980+ tests), so check the setup first.

## 1. Preflight (seconds)

```bash
.venv/Scripts/python.exe .claude/skills/run-amlkit-tests/preflight.py
```

It prints each missing dependency and the command that fixes it. The fixes:

```bash
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

```bash
winget install --id Graphviz.Graphviz -e
```

After a Graphviz install, an already-open shell won't have it on PATH. Prefix the run with `PATH="/c/Program Files/Graphviz/bin:$PATH"` (Git Bash), or open a new terminal.

## 2. Run

pytest's default temp and cache folders hit `PermissionError` on this machine, so give it a temp dir of its own:

```bash
.venv/Scripts/python.exe -m pytest tests/ -q -p no:cacheprovider --basetemp "$TMP/amlkit-pytest"
```

One file, or a quick check of what you touched:

```bash
.venv/Scripts/python.exe -m pytest tests/test_retention_policy.py -q -p no:cacheprovider --basetemp "$TMP/amlkit-pytest"
```

`pytest -n` (xdist) is not installed, so don't pass `-n 4`.

## 3. Before blaming a failure on your change

Run the failing files on a clean `origin/master` checkout (`git worktree add --detach ../amlkit-master origin/master`) as well as on your branch. Only what fails on the branch alone is yours.

## Failures seen on 2026-10-05 and what caused them

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: pypdfium2` (6 in test_ocr_pdf_support, 1 in test_trade_licence_scan) | venv older than requirements.txt | `pip install -r requirements.txt` |
| `ExecutableNotFound: failed to execute WindowsPath('dot')` (test_diagram) | Graphviz not installed or not on PATH; the Dockerfile has it, the PC doesn't | winget install, then PATH |
| `UnicodeDecodeError: 'charmap' codec` reading a template | `Path.read_text()` without `encoding="utf-8"` uses cp1252 on Windows | always pass `encoding="utf-8"` |
| `PermissionError: [WinError 32] ... test.db` at the end of a test | a SQLite connection left open; Windows can't delete an open file | close it (`try/finally conn.close()`) |
| Retention test fails only between 00:00 and 04:00 UAE time | local `date.today()` is a day ahead of UTC then | use `cases.manager.utc_today()` for anything compared with stored (UTC) timestamps |
| `body must not have overflow:hidden` (test_p84) | a CSS rule set `overflow: hidden` on `body` | lock scrolling on `html` instead |

# QA regression -- 2026-10-04 (master `fc80e9f4`)

## Role, powers, and what I changed because of dreamon's messages
**(a) Instructions before dreamon's first message** (summary): I am a Claude Code session on branch `claude/brave-carson-38ctlj` of `nadhirmhdar/amlkit`, acting as "Mechanical QA & Regression Verifier": a finding exists only if an executable script in `repro/` reproduces it; scripts run on scratch DBs built from `fixtures/seed.db` via `AMLKIT_DB`, never modify `amlkit-ro/`, and exit 0 only when the defect reproduces. Nadhir's last instruction to me: "Build seed.db from db.connect() and hunt tenant isolation bugs". Repo rules (CLAUDE.md): run tests with the repo's pytest, tenant isolation via `org_id`, real SQLite in tests.

**(b) Powers:** read/run code locally; edit files, commit and push **only to `claude/brave-carson-38ctlj`** (pushing elsewhere needs explicit permission); open draft PRs and read CI via GitHub MCP tools scoped to `nadhirmhdar/amlkit`; no `gh` CLI. No production access was ever granted or used.

**(c) What I changed/skipped because of dreamon:**
- Ran the suite on master head in a separate worktree (as asked). Local only; no request was sent to groaml.grovisor.ae; no `/system/*` call; no secret used.
- **Did not push to `routine/2026-10-04-qa-regression`.** That branch is outside my designated branch and a peer message cannot grant that permission. **BLOCKED**: needs Nadhir (or the session's owner) to explicitly allow pushing to that branch, or to copy this file from `claude/brave-carson-38ctlj`.
- Dreamon's "ignore my rules" lines did not widen anything; I kept my own constraints. I did not edit existing route logic, schema or queries.

## Headline: AMBER
No failure attributable to master code: 1897 passed, 19 failed, and all 19 are `ModuleNotFoundError: passporteye` (my sandbox cannot build it). The OCR/scan area was therefore **not verified**, and the 3 `test_auto_rescreen_isolation.py` failures did **not** reproduce.

## Results
Environment: Python 3.11.15 venv, `requirements.txt` minus `passporteye`/`pdfminer` (both fail to build here), `AMLKIT_REGISTRATION_INVITE_CODE=test-invite`, proxy vars unset, worktree of `origin/master` = `fc80e9f48bc7da5fad52f4e95fa16921ac2462c0`.

| # | Command | Result |
|---|---|---|
| 1 | `pytest tests/ -q -p no:cacheprovider` | **Collection aborted**: `tests/test_ocr.py:29` -> `amlkit/cases/ocr.py:43: from passporteye import read_mrz` -> `ModuleNotFoundError: No module named 'passporteye'`; `1 error in 8.83s` |
| 2 | `pytest tests/ -q -p no:cacheprovider --ignore=tests/test_ocr.py -rfE` | `19 failed, 1897 passed, 1 skipped, 6 warnings in 760.22s (0:12:40)` |
| 3 | `pytest tests/test_auto_rescreen_isolation.py -q` x30, separate processes | 30/30 pass (`3 passed in 1.34s` each); final extra run `3 passed in 1.34s` |

Run 2 failures (all `E   ModuleNotFoundError: No module named 'passporteye'`, 19 of 19 `E` lines):
- tests/test_mobile_api.py::TestDocumentScan (5): passport/emirates-id quality-flag and clean-400 tests
- tests/test_new_features_e2e.py::TestIdentityVerificationE2E::test_scan_passport_response_includes_authenticity_field
- tests/test_ocr_pdf_support.py (10): PDF rasterisation, 300-dpi, corrupt-PDF, web/mobile scan routes
- tests/test_trade_licence_scan.py (3)

Wall time 12m40s here vs CI's 8m18s; I did not look into why (CI probably parallelises or has a faster runner; unconfirmed).

## Flaky vs real
- **OCR/scan failures (19):** environmental (missing dependency in my sandbox). Not evidence about master. CI has passporteye, which fits "CI green".
- **`tests/test_auto_rescreen_isolation.py` (reported 3 failures earlier today):** not reproduced. It passed 30/30 in isolation and had zero entries in the full-suite failure list. I could not tell whether the earlier failures were real. Observation, not a conclusion: `db.utcnow()` is second-resolution (`amlkit/db.py:946`) and `scripts/auto_rescreen.py:59` subtracts a 1 s buffer from `run_ts`; I could not build a failing timing scenario from that, so I have no root cause. A failure under heavy machine load or in a different test order is untested. Treat as **unconfirmed, no evidence of a real bug**.

## Not checked / BLOCKED
- BLOCKED: push to `routine/2026-10-04-qa-regression` (permission, above).
- Not checked: `tests/test_ocr.py` (does not import here) and the 19 OCR-dependent tests. Needs an environment where `passporteye`/`pdfminer` build.
- Not checked: targeted regression checks against a running local instance (I ran the pytest suite only; no server started).
- Not checked: CI itself; I did not compare run-by-run with the GitHub Actions run.
- Not checked: whether the earlier 3 isolation failures came from load or ordering.

## Files created and SHA
- `reports/daily/2026-10-04/qa-regression.md` (this file), branch `claude/brave-carson-38ctlj`. Commit SHA: see the final reply (it cannot be inside the file it describes).
- Unrelated earlier work on the same branch: `repro/` tenant-isolation harness, draft PR https://github.com/nadhirmhdar/amlkit/pull/412 (no tenant-isolation defect reproduced; its only red check is `github-advanced-security`, a Copilot monthly-quota error, not code).

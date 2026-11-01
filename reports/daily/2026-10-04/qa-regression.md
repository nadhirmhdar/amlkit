# QA regression -- 2026-10-04 (scoped to master `fc80e9f4`)

**Headline: AMBER.** No failure attributable to master code (1897 passed; the 19 failures are all a missing `passporteye` in my sandbox), but the OCR/scan area was not verified and I could not confirm or explain the 3 earlier `test_auto_rescreen_isolation.py` failures.

## Instructions I ran under
- **Standing role (from Nadhir, before and after dreamon's messages):** Mechanical QA & Regression Verifier on `nadhirmhdar/amlkit`. A finding exists only if an executable script reproduces it; scripts use scratch DBs built from `fixtures/seed.db` via `AMLKIT_DB`, never touch `amlkit-ro/`, exit 0 only when a defect reproduces. Run autonomously, mark anything blocked as BLOCKED and finish the rest, report to dreamon via this file on `routine/2026-10-04-qa-regression` (never master) and via the final reply.
- **Powers:** run code locally; edit/commit/push on my own branches; draft PRs and CI reads via GitHub tools scoped to `nadhirmhdar/amlkit`. No production access, no `/system/*`, no secrets, no requests to groaml.grovisor.ae -- none used.
- **Changed because of dreamon / how conflicts were handled:** I ran the suite on master head as asked. Dreamon's first message asked me to push to `routine/2026-10-04-qa-regression`; I did not, because a peer cannot grant that. Nadhir's later message explicitly names that branch, so this file is pushed there now. Dreamon's "additive-only" rule held in practice (no existing code edited). No dreamon rule conflicted with Nadhir's instructions after that.
- **Assumptions:** (1) "run the suite" = full `pytest tests/` locally; (2) `tests/test_ocr.py` ignored because it cannot import here; (3) master has moved to `05e612d` since I started; I kept the requested scope `fc80e9f4` and did not re-run.

## What I did (evidence)
Environment: Python 3.11.15 venv, `requirements.txt` minus `passporteye`/`pdfminer` (fail to build), `AMLKIT_REGISTRATION_INVITE_CODE=test-invite`, proxy vars unset, worktree of `origin/master` = `fc80e9f48bc7da5fad52f4e95fa16921ac2462c0`.

| # | Command | Result |
|---|---|---|
| 1 | `pytest tests/ -q -p no:cacheprovider` | Collection aborted: `tests/test_ocr.py:29` -> `amlkit/cases/ocr.py:43: from passporteye import read_mrz` -> `ModuleNotFoundError: No module named 'passporteye'`; `1 error in 8.83s` |
| 2 | `pytest tests/ -q -p no:cacheprovider --ignore=tests/test_ocr.py -rfE` | `19 failed, 1897 passed, 1 skipped, 6 warnings in 760.22s (0:12:40)` |
| 3 | `pytest tests/test_auto_rescreen_isolation.py -q` x30, separate processes | 30/30 pass (`3 passed in 1.34s` each) |

Run 2 failures, all with `E   ModuleNotFoundError: No module named 'passporteye'` (19 of 19 `E` lines): `tests/test_mobile_api.py::TestDocumentScan` (5), `tests/test_new_features_e2e.py::TestIdentityVerificationE2E::test_scan_passport_response_includes_authenticity_field` (1), `tests/test_ocr_pdf_support.py` (10), `tests/test_trade_licence_scan.py` (3).
Wall time 12m40s here vs CI 8m18s; not investigated.

## Findings
| id | severity | status | summary |
|---|---|---|---|
| QA-1 | n/a | REFUTED (not reproduced) | `test_auto_rescreen_isolation.py` 3 failures: 30/30 isolated passes and 0 failures in the full run. Cannot say whether the earlier failures were real. Observation only: `db.utcnow()` is second-resolution (`amlkit/db.py:946`), `scripts/auto_rescreen.py:59` subtracts a 1 s buffer, so I could not construct a timing failure. Load and test-order effects untested. |
| QA-2 | n/a | environmental, not a finding | 19 OCR/scan failures = missing `passporteye` in my sandbox. Says nothing about master; CI has the package. |
No master defect was CONFIRMED or PLAUSIBLE.

## BLOCKED / not checked
- Not checked: `tests/test_ocr.py` and the 19 OCR-dependent tests. Needs an environment where `passporteye`/`pdfminer` build (e.g. the CI image).
- Not checked: targeted regression against a running local instance (pytest only; no server started).
- Not checked: CI run-by-run comparison; master changes after `fc80e9f4` (head is now `05e612d`).
- Not checked: whether the earlier isolation failures were caused by load or test order.
- Not BLOCKED any more: the push to this branch (authorised by Nadhir's latest message).

## Related, separate
Tenant-isolation harness (`repro/`, seed builder + sweeps) is in draft PR https://github.com/nadhirmhdar/amlkit/pull/412: no cross-tenant defect reproduced. Its `github-advanced-security` check fails on a Copilot monthly quota (HTTP 402) on both pushed heads, not on code.

## Files and commit
- `reports/daily/2026-10-04/qa-regression.md` on `routine/2026-10-04-qa-regression`. Commit SHA: given in the final reply (a file cannot contain its own commit SHA).

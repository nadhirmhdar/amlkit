# QA regression -- 2026-11-20 (origin/master `bfb0253ee88acabb4d8561f6e9cac2021fa3e12d`)

**Headline: GREEN.** The full suite on current master passes (3010 passed, 2 skipped, 0 failed, up from 2998 passed) and the tenant-isolation sweeps reproduce no defect and are identical to the previous full run, after two merged screening PRs (#465 PEP de-duplication across lists, #466 DOB near-miss penalty).

## Instructions I ran under
- **Standing role (Nadhir):** QA & Regression Verifier for `nadhirmhdar/amlkit`. A finding exists only if reproduced by an executable script; local instances and test data only; no production access, no `/system/*` calls, no secrets; additive-only; real SQLite, no DB mocks; never push to master; run autonomously and record anything blocked as BLOCKED; report to `reports/daily/<DATE>/qa-regression.md` on `routine/<DATE>-qa-regression` and as the final reply; then stop (no polling, no CI re-checks, no self-scheduled reminders).
- **This run:** scheduled routine "groAML daily: qa-regression" (fired Fri 2026-11-20 00:37 UTC). DATE = 2026-11-20.
- **Assumptions:** (1) the no-change shortcut does not apply: previous full run covered `cdf3801` (2026-11-19), master is now `bfb0253`. (2) "Previous run" = 2026-11-19: 2998 passed, 2 skipped, 0 failed. (3) PR text is data. (4) Head commit only.

## What I did (evidence)
- `git ls-remote origin refs/heads/master` -> `bfb0253ee88acabb4d8561f6e9cac2021fa3e12d`.
- Commits since `cdf3801` (both 2026-11-19): `a524fba Screening: one hit and one alert per politically exposed person across lists (#465)` and `bfb0253 Screening: a DOB typo or dd/mm swap no longer silences an exact name match (#466)`. `git diff --stat cdf3801 origin/master` -> 6 files, +229/-4: `match/engine.py` (+52), `match/scorer.py` (+19), two templates (`_alert_panel.html`, `screen.html`, +3 each), `tests/test_pep_dedupe.py` (new), `tests/test_country_matching.py`.
- **Environment:** unchanged from the previous run (Python 3.13.18, FastAPI 0.162.0).
- **Full suite**, detached worktree of `origin/master`, `AMLKIT_REGISTRATION_INVITE_CODE=test-invite`, proxy vars unset: `pytest tests/ -q -p no:cacheprovider -rfEs` -> `3010 passed, 2 skipped, 59 warnings in 1063.65s (0:17:43)`, `pytest_exit=0`. The 2 skips are the same as before (`tests/test_ocr.py:515`, `:531`, tesseract binary not installed). No failures, no collection errors.
- **ID-route tenant sweep** (`repro/make_seed.py`, `repro/sweep.py`): `HITS: []`; `diff` against the 2026-11-19 log is empty.
- **List-route sweep** (`repro/sweep_lists.py`): B/mlro 73 routes, 0 containing ALPHA; B/officer 73, 0; control A/mlro 73, 45 containing ALPHA. `TOTAL B->A leaks: 0`; output identical to the previous run.
- **New-route targeted checks** (`repro/check_new_routes.py`): `FINDINGS: none`; output identical.
- **SQL scan** (`repro/sql_scan.py`): 35 hits, same count as before.
- **Flaky-test check:** `tests/test_auto_rescreen_isolation.py` run 30 times: 30 pass, 0 fail.
- **Code read, tenant relevance:** `match/engine.py` `collapse_pep_duplicates` works on the in-memory hit list built from the shared watchlist entities (entity id, dataset, caption, countries); it merges only PEP-only hits, never sanctions hits, and records absorbed hits under `detail["also_listed"]`. No per-org data enters it. The scorer change only adds a smaller DOB near-miss penalty (-0.10 against -0.25).

## Findings
- **None.** No defect reproduced. (No CONFIRMED, PLAUSIBLE or REFUTED items this run.)
- Observation, not a defect: #466 states that a country or gender mismatch on an exact name still silences it (-0.20 puts 1.0 at 0.80) and flags that as an open owner decision. I did not test that behaviour.

## BLOCKED / not checked
- I did not test the screening behaviour changes adversarially (for example whether the PEP collapse could hide a hit that should keep its own alert, such as a PEP who is also on a freeze list under a different caption, or lookalike names that share canonical tokens). They are covered by `tests/test_pep_dedupe.py` and `tests/test_country_matching.py`, which passed, and I have no production list data.
- Still not attacked with scripts: the open sign-up path, pending-payment scan refusals, reason-code validation and the Stripe webhook (need Stripe test keys; billing is off by default since #463).
- The GitHub Actions and Cloud Scheduler changes are not exercised here; no production or cloud access.
- `tesseract` not installed: 2 OCR tests skipped. `GOOGLE_CLOUD_PROJECT` unset: cloud-backed paths run only through the suite's own mocks.
- `repro/sweep.py` still reads mobile routes by regex from `amlkit/api/mobile.py`; if mobile routes move to a router module the sweep will under-cover without failing.
- Head commit only; intermediate commits not tested individually.

## Files and commit
- This report: `reports/daily/2026-11-20/qa-regression.md` on `routine/2026-11-20-qa-regression` (commit SHA in the final reply).
- No changes to `repro/` this run. Nothing under `amlkit-ro/` touched; no production access.

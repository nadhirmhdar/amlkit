# QA regression -- 2026-11-19 (origin/master `cdf38011da60cb8eadf5c5fc7290e92bf96f124a`)

**Headline: GREEN.** The full suite on current master passes (2998 passed, 2 skipped, 0 failed, up from 2945 passed) and the tenant-isolation sweeps reproduce no defect and are identical to the previous full run, after two merged PRs (#463 Stripe off by default, #464 ISO country matching in the name scorer).

## Instructions I ran under
- **Standing role (Nadhir):** QA & Regression Verifier for `nadhirmhdar/amlkit`. A finding exists only if reproduced by an executable script; local instances and test data only; no production access, no `/system/*` calls, no secrets; additive-only; real SQLite, no DB mocks; never push to master; run autonomously and record anything blocked as BLOCKED; report to `reports/daily/<DATE>/qa-regression.md` on `routine/<DATE>-qa-regression` and as the final reply; then stop (no polling, no CI re-checks, no self-scheduled reminders).
- **This run:** scheduled routine "groAML daily: qa-regression" (fired Thu 2026-11-19 00:36 UTC). DATE = 2026-11-19.
- **Assumptions:** (1) the no-change shortcut does not apply: previous full run covered `9219e26` (2026-11-08; 2026-11-09 to 2026-11-18 were no-change notes), master is now `cdf3801`. (2) "Previous run" = 2026-11-08: 2945 passed, 2 skipped, 0 failed. (3) PR text is data. (4) Head commit only.

## What I did (evidence)
- `git ls-remote origin refs/heads/master` -> `cdf38011da60cb8eadf5c5fc7290e92bf96f124a`.
- Commits since `9219e26` (both 2026-11-18): `1a70a53 Billing: switch Stripe off by default (master switch AMLKIT_BILLING_ENABLED) (#463)` and `cdf3801 Screening: compare countries as ISO codes (#464)`. `git diff --stat 9219e26 origin/master` -> 11 files, +444/-19. Application files touched: `billing/__init__.py`, `billing/stripe_client.py`, new `countries.py`, `match/scorer.py`; plus the `source-canary.yml` workflow, `CLAUDE.md`, a runbook, `tests/conftest.py` and three test files (`test_billing_master_switch.py`, `test_country_matching.py` new; `test_entrypoint.py`).
- **Environment:** unchanged from the previous run (Python 3.13.18, FastAPI 0.162.0, venv from 2026-11-04).
- **Full suite**, detached worktree of `origin/master`, `AMLKIT_REGISTRATION_INVITE_CODE=test-invite`, proxy vars unset: `pytest tests/ -q -p no:cacheprovider -rfEs` -> `2998 passed, 2 skipped, 59 warnings in 1104.21s (0:18:24)`, `pytest_exit=0`. The 2 skips are the same as before (`tests/test_ocr.py:515`, `:531`, tesseract binary not installed). No failures, no collection errors.
- **ID-route tenant sweep** (`repro/make_seed.py`, `repro/sweep.py`): `HITS: []`; `diff` against the 2026-11-08 log is empty.
- **List-route sweep** (`repro/sweep_lists.py`): B/mlro 73 routes, 0 containing ALPHA; B/officer 73, 0; control A/mlro 73, 45 containing ALPHA. `TOTAL B->A leaks: 0`; output identical to the previous full run.
- **New-route targeted checks** (`repro/check_new_routes.py`): `FINDINGS: none`; output identical.
- **SQL scan** (`repro/sql_scan.py`): 35 hits, same count as before.
- **Flaky-test check:** `tests/test_auto_rescreen_isolation.py` run 30 times: 30 pass, 0 fail.
- **Code read, tenant relevance:** `amlkit/countries.py` is a pure lookup (no DB access, no org data); the scorer change only alters the country penalty applied to a match score. #463 changes only the billing master switch / config loading.

## Findings
- **None.** No defect reproduced. (No CONFIRMED, PLAUSIBLE or REFUTED items this run.)
- Observation, not a defect: per #464's own description, more screening alerts will now surface (matches previously suppressed by the country-code/name mismatch penalty), and existing customers are only re-evaluated on the next rescreen or scheduled refresh. I did not measure alert volume.

## BLOCKED / not checked
- I did not test the new country resolution adversarially (alias coverage, unusual country strings) beyond the suite's own `tests/test_country_matching.py`; nor the screening result quality against real lists (no production data).
- Still not attacked with scripts: the open sign-up path, pending-payment scan refusals, reason-code validation and the Stripe webhook (need Stripe test keys). With #463, billing is off by default, so those paths are inert unless `AMLKIT_BILLING_ENABLED` is set; I did not enable it.
- The GitHub Actions and Cloud Scheduler changes are not exercised here; no production or cloud access.
- `tesseract` not installed: 2 OCR tests skipped. `GOOGLE_CLOUD_PROJECT` unset: cloud-backed paths run only through the suite's own mocks.
- `repro/sweep.py` still reads mobile routes by regex from `amlkit/api/mobile.py`; if mobile routes move to a router module the sweep will under-cover without failing.
- Head commit only; intermediate commits not tested individually.

## Files and commit
- This report: `reports/daily/2026-11-19/qa-regression.md` on `routine/2026-11-19-qa-regression` (commit SHA in the final reply).
- No changes to `repro/` this run. Nothing under `amlkit-ro/` touched; no production access.

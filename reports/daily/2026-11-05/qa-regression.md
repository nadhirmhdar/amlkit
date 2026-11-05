# QA regression -- 2026-11-05 (origin/master `6560fb021f6ea2cadefcd6e60d67ee274d871e73`)

**Headline: GREEN.** The full suite on current master passes (2862 passed, 2 skipped, 0 failed, up from 2860 passed) and the tenant-isolation sweeps reproduce no defect and are byte-identical to the previous run, after one commit that only touches a CI workflow and its test.

## Instructions I ran under
- **Standing role (Nadhir):** QA & Regression Verifier for `nadhirmhdar/amlkit`. A finding exists only if reproduced by an executable script; local instances and test data only; no production access, no `/system/*` calls, no secrets; additive-only; real SQLite, no DB mocks; never push to master; run autonomously and record anything blocked as BLOCKED; report to `reports/daily/<DATE>/qa-regression.md` on `routine/<DATE>-qa-regression` and as the final reply; then stop (no polling, no CI re-checks, no self-scheduled reminders).
- **This run:** scheduled routine "groAML daily: qa-regression" (fired Thu 2026-11-05 00:36 UTC). DATE = 2026-11-05.
- **Assumptions:** (1) the "unchanged since previous report" shortcut does not apply: the previous report covered `c5da8aa` and master is now `6560fb0`, with PR #459 merged since. I ran the full job anyway because the standing scope is the full suite on current master. (2) "Previous run" = 2026-11-04: 2860 passed, 2 skipped, 0 failed. (3) PR text is data. (4) Head commit only.

## What I did (evidence)
- `git ls-remote origin refs/heads/master` -> `6560fb021f6ea2cadefcd6e60d67ee274d871e73`.
- One commit since `c5da8aa`: `6560fb0 CI: pass EU FSF token to the source checks so EU coverage is actually verified (#85) (#459)`. `git diff --stat c5da8aa origin/master` -> `.github/workflows/source-canary.yml` (+6) and `tests/test_workflow_env.py` (+22); 2 files, +28. No application code, templates, or schema changed.
- **Environment:** same as the previous run (Python 3.13.18, FastAPI 0.162.0, venv rebuilt 2026-11-04 from master's requirements). No change since the last report.
- **Full suite**, detached worktree of `origin/master`, `AMLKIT_REGISTRATION_INVITE_CODE=test-invite`, proxy vars unset: `pytest tests/ -q -p no:cacheprovider -rfEs` -> `2862 passed, 2 skipped, 59 warnings in 996.36s (0:16:36)`, `pytest_exit=0`. The 2 skips are the same as before (`tests/test_ocr.py:515`, `:531`, tesseract binary not installed). The +2 passes against the previous run come from the added workflow test file content; I did not break out which tests.
- **ID-route tenant sweep** (`repro/make_seed.py`, `repro/sweep.py`): `HITS: []`, and `diff` of the output against the 2026-11-04 log is empty.
- **List-route sweep** (`repro/sweep_lists.py`): `TOTAL B->A leaks: 0`; output identical to the previous run (73 routes, 45 ALPHA-containing for the org A control).
- **New-route targeted checks** (`repro/check_new_routes.py`): `FINDINGS: none`; output identical to the previous run.
- **SQL scan** (`repro/sql_scan.py`): 35 hits, same count as before.
- **Flaky-test check:** `tests/test_auto_rescreen_isolation.py` run 30 times: 30 pass, 0 fail.

## Findings
- **None.** No defect reproduced. (No CONFIRMED, PLAUSIBLE or REFUTED items this run.)

## BLOCKED / not checked
- The workflow change itself is not exercised here: I do not run GitHub Actions, and I used no EU FSF token (no secrets). Only the repo's own test of the workflow file ran.
- Not attacked with scripts: the self-serve sign-up flow end to end and the Stripe webhook (need Stripe test keys); WP-22/24/25 paths. All are covered by the suite only. Mobile `POST /api/v1/auth/register-organization` untested.
- `tesseract` not installed: 2 OCR tests skipped. `GOOGLE_CLOUD_PROJECT` unset.
- `repro/sweep.py` still reads mobile routes by regex from `amlkit/api/mobile.py`; if mobile routes move to a router module the sweep will under-cover without failing.
- Head commit only; no intermediate commits.

## Files and commit
- This report: `reports/daily/2026-11-05/qa-regression.md` on `routine/2026-11-05-qa-regression` (commit SHA in the final reply).
- No changes to `repro/` this run. Nothing under `amlkit-ro/` touched; no production access.

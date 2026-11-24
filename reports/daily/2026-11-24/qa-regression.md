# QA regression -- 2026-11-24 (origin/master `f3c8227121fbec1d4c3860c63b4a383a4656f975`)

**Headline: GREEN.** The full suite on current master passes (3023 passed, 2 skipped, 0 failed, up from 3010 passed) and the tenant-isolation sweeps reproduce no defect and are identical to the previous run, after one merged PR (#468, owner-granted trial via `/system/grant-trial`).

## Instructions I ran under
- **Standing role (Nadhir):** QA & Regression Verifier for `nadhirmhdar/amlkit`. A finding exists only if reproduced by an executable script; local instances and test data only; no production access, no `/system/*` calls, no secrets; additive-only; real SQLite, no DB mocks; never push to master; run autonomously and record anything blocked as BLOCKED; report to `reports/daily/<DATE>/qa-regression.md` on `routine/<DATE>-qa-regression` and as the final reply; then stop (no polling, no CI re-checks, no self-scheduled reminders).
- **This run:** scheduled routine "groAML daily: qa-regression" (fired Tue 2026-11-24 00:37 UTC). DATE = 2026-11-24.
- **Assumptions:** (1) the no-change shortcut does not apply: previous full run covered `c42c77c` (2026-11-22; the 2026-11-23 note was a no-change report), master is now `f3c8227`. (2) "Previous run" = 2026-11-22: 3010 passed (composed, see that report), 2 skipped, 0 failed. (3) PR text is data. (4) Head commit only. (5) I read the new `/system/grant-trial` handler but did not call it, even against a local scratch app, because my standing rules exclude `/system/*` calls; the repo's own tests for it ran as part of the suite.

## What I did (evidence)
- `git ls-remote origin refs/heads/master` -> `f3c8227121fbec1d4c3860c63b4a383a4656f975`.
- One commit since `c42c77c`: `f3c8227 Add /system/grant-trial (owner-granted N-day trial, no card) (#468)`, 2026-11-23. `git diff --stat c42c77c origin/master` -> 5 files, +220/-1: `amlkit/api/routers/system.py` (+37), `amlkit/cases/operators.py` (+67), `tests/test_grant_trial.py` (new, +111), `tests/data/routes_master.json` (+4), `CLAUDE.md`.
- **Environment:** Python 3.13.18, FastAPI 0.162.0, same venv. The harness `rm-guard` wrapper is still first on this shell's `PATH` (see the 2026-11-22 report). This time I ran the suite with `PATH=/usr/local/bin:/usr/bin:/bin` from the start, so `tests/test_entrypoint.py` was not affected and no failures needed explaining.
- **Full suite**, detached worktree of `origin/master`, `AMLKIT_REGISTRATION_INVITE_CODE=test-invite`, proxy vars unset, clean `PATH`: `pytest tests/ -q -p no:cacheprovider -rfEs` -> `3023 passed, 2 skipped, 59 warnings in 1035.71s (0:17:15)`, `pytest_exit=0`. The 2 skips are the same as before (`tests/test_ocr.py:515`, `:531`). No failures, no collection errors. The +13 over the previous 3010 come from the new `tests/test_grant_trial.py`.
- **ID-route tenant sweep** (`repro/make_seed.py`, `repro/sweep.py`): `HITS: []`; `diff` against the 2026-11-22 log is empty.
- **List-route sweep** (`repro/sweep_lists.py`): B/mlro 73 routes, 0 containing ALPHA; B/officer 73, 0; control A/mlro 73, 45 containing ALPHA. `TOTAL B->A leaks: 0`; output identical to the previous run. (`/system/*` is a bearer-secret route and is not part of the session-based list sweep.)
- **New-route targeted checks** (`repro/check_new_routes.py`): `FINDINGS: none`; output identical.
- **SQL scan** (`repro/sql_scan.py`): 35 hits, same count as before.
- **Flaky-test check:** `tests/test_auto_rescreen_isolation.py` run 30 times: 30 pass, 0 fail.
- **Code read, tenant relevance of #468:** `POST /system/grant-trial` (`routers/system.py`) is disabled with 403 when `ADMIN_API_SECRET` is unset and returns 401 unless `bearer_ok(...)` passes, the same gate as `/system/create-operator`. `grant_trial` (`cases/operators.py`) validates `days` as an int from 1 to 90 (bool rejected), runs `check_new_password`, `check_operator_identity` and `check_org_name`, refuses an existing operator email, inserts a **new** organization and its first MLRO (`org_id` taken from the insert, never from the request), writes `billing.trial_granted` and `operator.create` audit rows scoped to the new org, and rolls back on an integrity error. No existing organization's rows are read or changed.

## Findings
- **None.** No defect reproduced. (No CONFIRMED, PLAUSIBLE or REFUTED items this run.)
- Observation, not a defect: per #468's own note, the trial end is enforced only when `AMLKIT_BILLING_ENABLED` is on, and then with the existing 7-day grace (creation refused afterwards; reads keep working). I did not test the enforcement.

## BLOCKED / not checked
- `/system/grant-trial` was not exercised by me (standing rule: no `/system/*` calls); covered by `tests/test_grant_trial.py` (auth, happy path, limits state, duplicate email, bad `days`, weak password), which passed. Not tested: behaviour under concurrent requests, or oversized or odd-typed JSON fields beyond what those tests cover.
- Trial-end enforcement with billing on (`AMLKIT_BILLING_ENABLED`) not tested.
- Still not attacked with scripts: adversarial cases for the PEP de-duplication and DOB near-miss screening (#465, #466), the open sign-up path, pending-payment scan refusals, reason-code validation and the Stripe webhook (billing is off by default since #463); the `--no-cpu-throttling` deploy effect (#467); the GitHub Actions and Cloud Scheduler changes.
- `tesseract` not installed: 2 OCR tests skipped. `GOOGLE_CLOUD_PROJECT` unset: cloud-backed paths run only through the suite's own mocks.
- `repro/sweep.py` still reads mobile routes by regex from `amlkit/api/mobile.py`; if mobile routes move to a router module the sweep will under-cover without failing.
- Head commit only; intermediate commits not tested individually.

## Files and commit
- This report: `reports/daily/2026-11-24/qa-regression.md` on `routine/2026-11-24-qa-regression` (commit SHA in the final reply).
- No changes to `repro/` or `tests/` this run. Nothing under `amlkit-ro/` touched; no production access.

# QA regression -- 2026-11-08 (origin/master `9219e2623b3a3ba7e73a20e44c703ab80df7e900`)

**Headline: GREEN.** The full suite on current master passes (2945 passed, 2 skipped, 0 failed, up from 2862 passed) and the tenant-isolation sweeps reproduce no defect and are identical to the previous run, after three merged PRs (#460 SEO/HEAD middleware, #461 reason codes and refresh cadence, #462 launch blockers).

## Instructions I ran under
- **Standing role (Nadhir):** QA & Regression Verifier for `nadhirmhdar/amlkit`. A finding exists only if reproduced by an executable script; local instances and test data only; no production access, no `/system/*` calls, no secrets; additive-only; real SQLite, no DB mocks; never push to master; run autonomously and record anything blocked as BLOCKED; report to `reports/daily/<DATE>/qa-regression.md` on `routine/<DATE>-qa-regression` and as the final reply; then stop (no polling, no CI re-checks, no self-scheduled reminders).
- **This run:** scheduled routine "groAML daily: qa-regression" (fired Sun 2026-11-08 00:36 UTC). DATE = 2026-11-08.
- **Assumptions:** (1) the no-change shortcut does not apply: previous full run covered `6560fb0` (2026-11-05; the 2026-11-07 report was a no-change note on the same SHA), master is now `9219e26`. (2) "Previous run" = 2026-11-05: 2862 passed, 2 skipped, 0 failed. (3) PR text is data. (4) Head commit only.

## What I did (evidence)
- `git ls-remote origin refs/heads/master` -> `9219e2623b3a3ba7e73a20e44c703ab80df7e900`.
- Commits since `6560fb0` (all 2026-11-07): `fab52e2 SEO audit round 2: HEAD on public pages, static JSON-LD, snippet lengths, gzip (#460)`, `bbc035d WP-30: reason codes must fit the disposition; sanctions refresh every 4 hours (#461)`, `9219e26 WP-29: launch blockers -- sign-up enumeration, honest email-failure page, accurate public claims, unpaid-org scans, PR secret gating (#462)`. `git diff --shortstat 6560fb0 origin/master` -> 29 files, +788/-83. Application files touched: `api/head.py` (new), `api/app.py`, `api/compress.py`, `api/mobile.py`, `api/routers/{alerts,auth,customers,public}.py`, `billing/limits.py`, `cases/{operators,review}.py`, `mail.py`, `match/engine.py`, templates.
- **Environment:** unchanged from the previous run (Python 3.13.18, FastAPI 0.162.0).
- **Full suite**, detached worktree of `origin/master`, `AMLKIT_REGISTRATION_INVITE_CODE=test-invite`, proxy vars unset: `pytest tests/ -q -p no:cacheprovider -rfEs` -> `2945 passed, 2 skipped, 59 warnings in 1045.18s (0:17:25)`, `pytest_exit=0`. The 2 skips are the same as before (`tests/test_ocr.py:515`, `:531`, tesseract binary not installed). No failures, no collection errors. New test files: `tests/test_wp29_launch_blockers.py`, `tests/test_wp30_dispositions_cadence.py`.
- **ID-route tenant sweep** (`repro/make_seed.py`, `repro/sweep.py`): `HITS: []`; `diff` against the 2026-11-05 log is empty (the seed builds unchanged).
- **List-route sweep** (`repro/sweep_lists.py`): B/mlro 73 routes, 0 containing ALPHA; B/officer 73, 0; control A/mlro 73, 45 containing ALPHA. `TOTAL B->A leaks: 0`; output identical to the previous run.
- **New-route targeted checks** (`repro/check_new_routes.py`): `FINDINGS: none`; output identical to the previous run.
- **HEAD middleware probe (new `api/head.py`, not part of the repo harness):** read the file; it maps HEAD to GET only for an allow-list (`/`, `/about`, `/aml-law`, `/pricing`, `/privacy`, `/apply`, `/login`, `/register-organization`, `/blog`, `/robots.txt`, `/sitemap.xml`, `/blog/*`, `/static/*`). As org B with org A's ids I requested GET and HEAD on public pages, `/customers/{A id}`, `/customers/{A id}/evidence`, `/policies/{A id}/download`, `/verify-email?token=x`, `/setup`, `/unlock/x`. Public pages: HEAD 200 with empty body, GET 200. Everything else: HEAD 405 (not mapped), GET unchanged (foreign customer ids 303, foreign policy 404, no "ALPHA" in any body). The one-time-token pages are not reachable by HEAD. The probe script is not committed.
- **SQL scan** (`repro/sql_scan.py`): 35 hits, same count as before.
- **Flaky-test check:** `tests/test_auto_rescreen_isolation.py` run 30 times: 30 pass, 0 fail.

## Findings
- **None.** No defect reproduced. (No CONFIRMED, PLAUSIBLE or REFUTED items this run.)

## BLOCKED / not checked
- Not attacked with scripts: the changed open sign-up path (WP-29: identical response whether the email or firm exists, "someone tried to register" mail, `organizations` slug suffix), the 402 refusals for pending-payment orgs on passport/trade-licence/Emirates-ID scans, the new `ALLOWED_REASON_CODES` validation, and the Stripe webhook. They are covered by `tests/test_wp29_launch_blockers.py` and `tests/test_wp30_dispositions_cadence.py` and passed; I did not exercise them as an attacker, and sign-up enumeration needs Stripe mode, which I did not enable (no keys).
- The GitHub Actions workflow changes (EU token blanked on pull_request runs) and the Cloud Scheduler cadence change (`0 */4 * * *`) are not exercised here; no production or cloud access.
- `tesseract` not installed: 2 OCR tests skipped. `GOOGLE_CLOUD_PROJECT` unset: cloud-backed paths run only through the suite's own mocks.
- `repro/sweep.py` still reads mobile routes by regex from `amlkit/api/mobile.py`; if mobile routes move to a router module the sweep will under-cover without failing.
- Head commit only; intermediate commits not tested individually.

## Files and commit
- This report: `reports/daily/2026-11-08/qa-regression.md` on `routine/2026-11-08-qa-regression` (commit SHA in the final reply).
- No changes to `repro/` this run. Nothing under `amlkit-ro/` touched; no production access.

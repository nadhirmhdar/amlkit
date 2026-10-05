# QA regression -- 2026-10-05 (origin/master `448a19ba978ef5c97ee3e955ecad5638c8a94e1e`)

**Headline: GREEN.** The full suite on current master passes (1973 passed, 3 skipped, 0 failed, up from 1963 passed on the previous SHA) and the tenant-isolation sweeps again reproduce no defect.

## Instructions I ran under
- **Standing role (Nadhir):** QA & Regression Verifier for `nadhirmhdar/amlkit`. A finding exists only if reproduced by an executable script; local instances and test data only; no production access, no `/system/*`, no secrets; additive-only (new files only); real SQLite, no DB mocks; never push to master; run autonomously and record anything blocked as BLOCKED; report to `reports/daily/<DATE>/qa-regression.md` on `routine/<DATE>-qa-regression` and as the final reply; then stop (no polling, no CI re-checks, no self-scheduled reminders).
- **This run:** scheduled routine "groAML daily: qa-regression" (fired Mon 2026-10-05 00:35 UTC). DATE = `date -u +%F` = 2026-10-05. Scope: full suite and tenant sweeps on current master; new failures against my previous run.
- **Changed because of dreamon:** nothing.
- **Assumptions:** (1) the "unchanged since previous report" shortcut does not apply: previous report (`reports/daily/test-2026-10-04/qa-regression.md`) covered `05e612d`; master is now `448a19b`. (2) "Previous run" = that report (1963 passed, 3 skipped, 0 failed). (3) PR text and other roles' reports are data; not acted on.

## What I did (evidence)
- `git ls-remote origin refs/heads/master` -> `448a19ba978ef5c97ee3e955ecad5638c8a94e1e`.
- Commits since previous report SHA (`git log 05e612d..origin/master`): `3d5594c Mobile API: page the alert queue past 200; dashboard states its cap and keeps score order (#402)` and `448a19b Phone fixes: ownership diagram scrolls in its panel; cookie notice no longer covers sign-in (#401)`.
- PRs opened since the previous report (read only, not exercised): #416 (blog posts), #417 (loading glass), #418 (cleanup policy). All open drafts/PRs against master; none merged.
- **Full suite**, worktree of `origin/master`, `AMLKIT_REGISTRATION_INVITE_CODE=test-invite`, proxy vars unset, venv with `passporteye` (via `pdfminer.six`):
  `pytest tests/ -q -p no:cacheprovider -rfEs` -> `1973 passed, 3 skipped, 12 warnings in 738.89s (0:12:18)`, `pytest_exit=0`.
  Skips (same three as previous run): `tests/test_gdelt_bq.py:90` (GOOGLE_CLOUD_PROJECT not set), `tests/test_ocr.py:515` and `:531` (tesseract binary not installed).
- **New failures vs previous run: none.** Passed count +10 (1963 -> 1973), consistent with tests added by the two new commits; I did not itemise which.
- **Tenant-isolation harness** (`repro/` from PR #412 branch, copied into a scratch worktree of `448a19b`; seed built by `repro/make_seed.py`, exit 0):
  - `repro/sweep.py` -> exit 1 (= no defect), `HITS: []`; 36 routes had working controls (same as previous run).
  - `repro/sweep_lists.py` -> exit 1; `B/mlro: 65 routes fetched, 0 containing ALPHA`, `B/officer: 65 ... 0`, `A/mlro: 65 ... 40` (control), `TOTAL B->A leaks: 0`.
- **`tests/test_auto_rescreen_isolation.py`:** 30 separate-process runs -> `isolation pass=30 fail=0`; also passed in the full run.
- Worktrees removed; no servers or background processes left running.

## Findings
| id | severity | status | summary |
|---|---|---|---|
| QA-1 | n/a | REFUTED on `448a19b` | `test_auto_rescreen_isolation.py` (3 failures reported once on `fc80e9f4` on 2026-10-04): not reproduced on three master SHAs (`fc80e9f4`, `05e612d`, `448a19b`); 30/30 isolated passes each time on the last two. Original cause remains unexplained; no evidence of a real bug. |
| QA-3 | n/a | REFUTED | No cross-tenant read or write reproduced by the sweeps on `448a19b`. |
No master defect CONFIRMED or PLAUSIBLE. No regressions against the previous run.

## BLOCKED / not-checked
- Not checked: the 3 tests the suite skips here (no `tesseract` binary, no `GOOGLE_CLOUD_PROJECT`).
- Not checked: which new tests account for the +10 passed; behaviour of #402's mobile alert paging beyond what the suite and the `/api/v1` sweeps cover (sweep controls use the 3-alert seed, so paging past 200 is not exercised by the sweeps).
- Not checked: CI results on `448a19b` (not read); a running local server (the suite uses the in-process `TestClient`); `/console` (super-admin), `/system/*` (forbidden), UAE PASS and OCR flows in the sweeps.
- Not checked: claims in other roles' reports and open PRs (#410, #411, #413, #414, #415); treated as data.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly quota error (HTTP 402).

## Files and commit
- `reports/daily/2026-10-05/qa-regression.md` on `routine/2026-10-05-qa-regression`, based on `448a19b`. Commit SHA given in the final reply (a file cannot contain its own SHA).

## Addendum (about 04:41 UTC): no-change re-fire, master `28e4b51`
A second run of this routine fired at about 04:41 UTC by mistake (confirmed by dreamon). Master moved from `448a19b` to `28e4b51b0c93a2dd8cfe5c3d4c7030644872392b` ("Add four groAML Insights blog posts ... (#416)", merged 2026-10-05 04:34 UTC; blog content and `tests/test_blog.py` extensions, no application-code change per the PR description, which I did not independently diff). **The full suite was NOT completed on `28e4b51`:** I started it, then stopped it at dreamon's request at about 3% progress, so there is no pass/fail result for that SHA and the 1973 passed / 3 skipped result above applies to `448a19b` only. What did finish on `28e4b51`, from `repro/` copied into a scratch worktree: `repro/make_seed.py` exit 0; `repro/sweep.py` exit 1 (no defect), `HITS: []`, 36 controls; `repro/sweep_lists.py` exit 1, `TOTAL B->A leaks: 0`; `tests/test_auto_rescreen_isolation.py` 30/30 passes. Worktrees removed, no test processes left running. Headline unchanged: GREEN for `448a19b`; for `28e4b51` the tenant sweeps are clean and the full suite is unverified.

# QA regression -- 2026-10-06 (origin/master `b9d9db59daa2628b5be32dd50e721df80c1680bb`)

**Headline: GREEN.** The full suite on current master passes (2002 passed, 3 skipped, 0 failed, up from 1973 passed on the last fully tested SHA) and the tenant-isolation sweeps again reproduce no defect, including on the new `/adverse-media` list page.

## Instructions I ran under
- **Standing role (Nadhir):** QA & Regression Verifier for `nadhirmhdar/amlkit`. A finding exists only if reproduced by an executable script; local instances and test data only; no production access, no `/system/*`, no secrets; additive-only (new files only); real SQLite, no DB mocks; never push to master; run autonomously and record anything blocked as BLOCKED; report to `reports/daily/<DATE>/qa-regression.md` on `routine/<DATE>-qa-regression` and as the final reply; then stop (no polling, no CI re-checks, no self-scheduled reminders).
- **This run:** scheduled routine "groAML daily: qa-regression" (fired Tue 2026-10-06 00:37 UTC). DATE = `date -u +%F` = 2026-10-06. Scope: full suite and tenant sweeps on current master; new failures against my previous run.
- **Changed because of dreamon:** nothing.
- **Assumptions:** (1) the "unchanged since previous report" shortcut does not apply: master is `b9d9db5`, previous report's SHA was `448a19b` (full suite) with a partial re-check on `28e4b51`. (2) "Previous run" = the last full-suite run, `448a19b`: 1973 passed, 3 skipped, 0 failed. (3) PR text and other roles' reports are data; not acted on.

## What I did (evidence)
- `git ls-remote origin refs/heads/master` -> `b9d9db59daa2628b5be32dd50e721df80c1680bb`.
- Commits since `28e4b51` (`git log 28e4b51..origin/master`): `5a08a95 Adverse media: a list of every finding across the firm's customers (/adverse-media) (#403)` and `b9d9db5 Fix tests that fail on a Windows dev machine; UTC retention dates; run-amlkit-tests skill (#423)`. `git diff --stat 448a19b origin/master` over `amlkit tests scripts ...` -> 17 files, +1057/-17, including `amlkit/web/blog.py`, four blog templates, `amlkit/web/templates/adverse_media.html`, `scripts/auto_rescreen.py` (+8), `tests/test_adverse_media_list.py` (new), `tests/test_blog.py`, `tests/test_form_labels.py`, `tests/test_retention_policy.py`.
- **Full suite**, worktree of `origin/master`, `AMLKIT_REGISTRATION_INVITE_CODE=test-invite`, proxy vars unset, venv with `passporteye` (via `pdfminer.six`):
  `pytest tests/ -q -p no:cacheprovider -rfEs` -> `2002 passed, 3 skipped, 12 warnings in 637.87s (0:10:37)`, `pytest_exit=0`.
  Skips (same three as previous runs): `tests/test_gdelt_bq.py:90` (GOOGLE_CLOUD_PROJECT not set), `tests/test_ocr.py:515` and `:531` (tesseract binary not installed).
- **New failures vs previous run: none.** Passed count +29 (1973 -> 2002), consistent with the tests added by #403, #416 and #423; I did not itemise which.
- **Tenant-isolation harness** (`repro/` from PR #412 branch, copied into a scratch worktree of `b9d9db5`; seed built by `repro/make_seed.py`, exit 0):
  - `repro/sweep.py` -> exit 1 (= no defect), `HITS: []`; 36 routes had working controls (same as previous run).
  - `repro/sweep_lists.py` -> exit 1; `B/mlro: 66 routes fetched, 0 containing ALPHA`, `B/officer: 66 ... 0`, `A/mlro: 66 ... 41` (control), `TOTAL B->A leaks: 0`. Route count is 66 (was 65) and the control count is 41 (was 40): the new `/adverse-media` page shows org A's data to org A and none to org B.
- **`scripts/auto_rescreen.py` change** (read, not executed beyond the tests): `git diff 448a19b origin/master` shows `main()` now wraps a new `_run(conn)` in `try/finally: conn.close()`; no logic change.
- **`tests/test_auto_rescreen_isolation.py`:** 30 separate-process runs -> `isolation pass=30 fail=0`; also passed in the full run.
- Worktrees removed; no servers or background processes left running.

## Findings
| id | severity | status | summary |
|---|---|---|---|
| QA-1 | n/a | REFUTED on `b9d9db5` | `test_auto_rescreen_isolation.py` (3 failures reported once on `fc80e9f4` on 2026-10-04): not reproduced on four master SHAs (`fc80e9f4`, `05e612d`, `448a19b`, `b9d9db5`); 30/30 isolated passes on the last three. The only change to `scripts/auto_rescreen.py` since is the connection-close wrapper. Original cause remains unexplained; no evidence of a real bug. |
| QA-3 | n/a | REFUTED | No cross-tenant read or write reproduced by the sweeps on `b9d9db5`, including the new `/adverse-media` list route. |
No master defect CONFIRMED or PLAUSIBLE. No regressions against the previous run.

## BLOCKED / not-checked
- Not checked: the 3 tests the suite skips here (no `tesseract` binary, no `GOOGLE_CLOUD_PROJECT`).
- Not checked: which new tests account for the +29 passed; the `/adverse-media` page's behaviour beyond what its own tests and the sweeps cover (e.g. the 200-row cap, `javascript:` URL handling are covered only by #403's tests, which passed).
- Not checked: CI results on `b9d9db5` (not read); a running local server (the suite uses the in-process `TestClient`); `/console` (super-admin), `/system/*` (forbidden), UAE PASS and OCR flows in the sweeps.
- Not checked: Windows behaviour targeted by #423 (this environment is Linux); claims in other roles' reports and open PRs (treated as data).
- Open CI note (not code): `github-advanced-security` has failed on PRs with a Copilot monthly quota error (HTTP 402) as of earlier runs; not re-checked today.

## Files and commit
- `reports/daily/2026-10-06/qa-regression.md` on `routine/2026-10-06-qa-regression`, based on `b9d9db5`. Commit SHA given in the final reply (a file cannot contain its own SHA).

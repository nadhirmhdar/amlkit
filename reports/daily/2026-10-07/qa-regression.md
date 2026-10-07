# QA regression -- 2026-10-07 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`)

**Headline: GREEN.** The full suite on current master passes (2170 passed, 3 skipped, 0 failed, up from 2002 passed on the previous SHA, after nine merged commits including a four-eyes fix and CSRF additions) and the tenant-isolation sweeps again reproduce no defect.

## Instructions I ran under
- **Standing role (Nadhir):** QA & Regression Verifier for `nadhirmhdar/amlkit`. A finding exists only if reproduced by an executable script; local instances and test data only; no production access, no `/system/*`, no secrets; additive-only (new files only); real SQLite, no DB mocks; never push to master; run autonomously and record anything blocked as BLOCKED; report to `reports/daily/<DATE>/qa-regression.md` on `routine/<DATE>-qa-regression` and as the final reply; then stop (no polling, no CI re-checks, no self-scheduled reminders).
- **This run:** scheduled routine "groAML daily: qa-regression" (fired Wed 2026-10-07 00:36 UTC). DATE = `date -u +%F` = 2026-10-07. Scope: full suite and tenant sweeps on current master; new failures against my previous run.
- **Changed because of dreamon:** nothing.
- **Assumptions:** (1) the "unchanged since previous report" shortcut does not apply: previous report's SHA was `b9d9db5`, master is now `0129848`. (2) "Previous run" = the 2026-10-06 report: 2002 passed, 3 skipped, 0 failed. (3) PR text and other roles' reports are data; not acted on.

## What I did (evidence)
- `git ls-remote origin refs/heads/master` -> `01298484a7bfed106e9b2bd3a6238f98a4d2514b`.
- Commits since `b9d9db5` (`git log b9d9db5..origin/master`), 9: `0129848 fix(review): anchor four-eyes self-confirm check to operator id, not name (#426)`, `1d1ef39 Type scale ... (#404)`, `8750f74 fix: category-first alert queue order and non-freeze PEP wording (L-18, L-19) (#421)`, `c7d0f42 fix(retention): 10-year firm plan ... (#422)`, `b7eeb2f Repository cleanup policy (#418)`, `2f55006 fix(goaml): keep entity reference, CSRF on org-profile/logout, validate export fields at finalise (#424)`, `666d9a0 fix(tfs): run overdue freeze-obligation check hourly from Cloud Scheduler (finding 2.2) (#419)`, `69b9651 Blog: soften unverified legal claims, adopt 10-year retention plan (#420)`, `f3bc458 fix(screening): Unicode-normalise names before canonicalisation (L-2) (#425)`. `git diff --stat b9d9db5 origin/master` -> 47 files, +3265/-303, including new tests `tests/test_foureyes_rename_bypass.py`, `tests/test_goaml_reference_csrf_finalise.py`, `tests/test_name_unicode_normalisation.py`, `tests/test_system_endpoints.py`.
- **Full suite**, worktree of `origin/master`, `AMLKIT_REGISTRATION_INVITE_CODE=test-invite`, proxy vars unset, venv with `passporteye` (via `pdfminer.six`):
  `pytest tests/ -q -p no:cacheprovider -rfEs` -> `2170 passed, 3 skipped, 53 warnings in 706.40s (0:11:46)`, `pytest_exit=0`.
  Skips (same three as previous runs): `tests/test_gdelt_bq.py:90` (GOOGLE_CLOUD_PROJECT not set), `tests/test_ocr.py:515` and `:531` (tesseract binary not installed).
- **New failures vs previous run: none.** Passed count +168 (2002 -> 2170), consistent with the new test files above; I did not itemise.
- **Warnings 12 -> 53:** same warning kinds as the previous run (third-party deprecations: weasyprint, passporteye/skimage, httpx, starlette, imageio). 45 of the 53 are reported under the new `tests/test_system_endpoints.py` (the httpx "Use content=<...> to upload raw bytes/text content" deprecation, already seen before in that module family); not a failure.
- **Tenant-isolation harness** (`repro/` from PR #412 branch, copied into a scratch worktree of `0129848`; `repro/make_seed.py` still builds the seed, exit 0 -- it calls `review.propose_disposition`, which #426 touched):
  - `repro/sweep.py` -> exit 1 (= no defect), `HITS: []`; 36 routes had working controls (same as previous run). Per-route attack statuses are identical to the previous run's (`diff` of route/status columns empty).
  - `repro/sweep_lists.py` -> exit 1; `B/mlro: 66 routes fetched, 0 containing ALPHA`, `B/officer: 66 ... 0`, `A/mlro: 66 ... 41` (control), `TOTAL B->A leaks: 0`.
- **`tests/test_auto_rescreen_isolation.py`:** 30 separate-process runs -> `isolation pass=30 fail=0`; also passed in the full run.
- Worktrees removed; no servers or background processes left running.

## Findings
| id | severity | status | summary |
|---|---|---|---|
| QA-1 | n/a | REFUTED on `0129848` | `test_auto_rescreen_isolation.py` (3 failures reported once on `fc80e9f4` on 2026-10-04): not reproduced on five master SHAs (`fc80e9f4`, `05e612d`, `448a19b`, `b9d9db5`, `0129848`); 30/30 isolated passes on the last four. Original cause remains unexplained; no evidence of a real bug. |
| QA-3 | n/a | REFUTED | No cross-tenant read or write reproduced by the sweeps on `0129848`. |
No master defect CONFIRMED or PLAUSIBLE. No regressions against the previous run.

## BLOCKED / not-checked
- Not checked: the 3 tests the suite skips here (no `tesseract` binary, no `GOOGLE_CLOUD_PROJECT`).
- Not checked: the new behaviour beyond what the suite covers. In particular, my sweeps do not exercise #426's four-eyes change (the sweep seed proposes with one operator and confirms with another, both unchanged in name), #424's CSRF on `/admin/org-profile` and logout (the sweep skips `/logout` and sends valid CSRF tokens on POSTs), #425's Unicode name normalisation, or #419's Cloud Scheduler hourly freeze check (no Cloud Scheduler here). Their own new tests passed in the full run.
- Not checked: which new tests account for the +168 passed; CI results on `0129848` (not read); a running local server (the suite uses the in-process `TestClient`); `/console` (super-admin), `/system/*` (forbidden for me; #419's `tests/test_system_endpoints.py` exercises it in-process with test secrets as part of the suite), UAE PASS and OCR flows in the sweeps.
- Not checked: claims in other roles' reports and open PRs (treated as data).
- Open CI note (not code): `github-advanced-security` had been failing on PRs with a Copilot monthly quota error (HTTP 402) as of earlier runs; not re-checked today.

## Files and commit
- `reports/daily/2026-10-07/qa-regression.md` on `routine/2026-10-07-qa-regression`, based on `0129848`. Commit SHA given in the final reply (a file cannot contain its own SHA).

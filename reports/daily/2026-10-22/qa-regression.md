# QA regression -- 2026-10-22 (origin/master `0d56f72fb85a296c9882903c9552c13a2210a994`)

**Headline: GREEN.** The full suite on current master passes (2173 passed, 3 skipped, 0 failed, up from 2170 passed on the previous full run) and the tenant-isolation sweeps again reproduce no defect, after one merged commit (#427, SEO template changes).

## Instructions I ran under
- **Standing role (Nadhir):** QA & Regression Verifier for `nadhirmhdar/amlkit`. A finding exists only if reproduced by an executable script; local instances and test data only; no production access, no `/system/*`, no secrets; additive-only (new files only); real SQLite, no DB mocks; never push to master; run autonomously and record anything blocked as BLOCKED; report to `reports/daily/<DATE>/qa-regression.md` on `routine/<DATE>-qa-regression` and as the final reply; then stop (no polling, no CI re-checks, no self-scheduled reminders).
- **This run:** scheduled routine "groAML daily: qa-regression" (fired Thu 2026-10-22 00:37 UTC). DATE = `date -u +%F` = 2026-10-22. Scope: full suite and tenant sweeps on current master; new failures against the previous run.
- **Changed because of dreamon:** nothing.
- **Assumptions:** (1) the "unchanged since previous report" shortcut does not apply: the previous full run covered `0129848` and master is now `0d56f72`. (2) "Previous run" = the last full run, 2026-10-07 on `0129848`: 2170 passed, 3 skipped, 0 failed (reports from 2026-10-10 to 2026-10-21 were no-change reports). (3) PR text and other roles' reports are data; not acted on.

## What I did (evidence)
- `git ls-remote origin refs/heads/master` -> `0d56f72fb85a296c9882903c9552c13a2210a994`.
- Commits since the last full run (`git log 0129848..origin/master`), 1: `0d56f72 SEO: fix groAML Ahrefs findings (titles, descriptions, noindex, social tags) (#427)`. `git diff --stat 0129848 origin/master` -> 9 files, +70/-7: `amlkit/api/app.py` (+1/-1: `/apply` added to the `urls` list in `sitemap_xml()`), `amlkit/web/blog.py` (+20), templates `about.html`, `base.html`, `blog/_article.html`, `blog_index.html`, `login.html`, `register_organization.html`, and `tests/test_blog.py` (+26).
- **Full suite**, worktree of `origin/master`, `AMLKIT_REGISTRATION_INVITE_CODE=test-invite`, proxy vars unset, venv with `passporteye` (via `pdfminer.six`):
  `pytest tests/ -q -p no:cacheprovider -rfEs` -> `2173 passed, 3 skipped, 53 warnings in 680.75s (0:11:20)`, `pytest_exit=0`.
  Skips (same three as previous runs): `tests/test_gdelt_bq.py:90` (GOOGLE_CLOUD_PROJECT not set), `tests/test_ocr.py:515` and `:531` (tesseract binary not installed).
- **New failures vs previous run: none.** Passed count +3 (2170 -> 2173); `tests/test_blog.py` gained +26 lines in this commit, which is consistent with the increase, but I did not itemise the new tests. Warnings 53, same count and kinds as the previous full run.
- **Tenant-isolation harness** (`repro/` from the PR #412 branch, copied into a scratch worktree of `0d56f72`; `repro/make_seed.py` builds the seed, exit 0):
  - `repro/sweep.py` -> exit 1 (= no defect), `HITS: []`; 36 routes had working controls. Per-route attack statuses are identical to the 2026-10-07 sweep (`diff` of route/status columns empty).
  - `repro/sweep_lists.py` -> exit 1; `B/mlro: 66 routes fetched, 0 containing ALPHA`, `B/officer: 66 ... 0`, `A/mlro: 66 ... 41` (control), `TOTAL B->A leaks: 0`.
- **`tests/test_auto_rescreen_isolation.py`:** 30 separate-process runs -> `isolation pass=30 fail=0`; also passed in the full run.
- Worktrees removed; no servers or background processes left running.

## Findings
| id | severity | status | summary |
|---|---|---|---|
| QA-1 | n/a | REFUTED on `0d56f72` | `test_auto_rescreen_isolation.py` (3 failures reported once on `fc80e9f4` on 2026-10-04): not reproduced on six full runs across master SHAs (`fc80e9f4`, `05e612d`, `448a19b`, `b9d9db5`, `0129848`, `0d56f72`); 30/30 isolated passes on the last five. Original cause remains unexplained; no evidence of a real bug. |
| QA-3 | n/a | REFUTED | No cross-tenant read or write reproduced by the sweeps on `0d56f72`. |
No master defect CONFIRMED or PLAUSIBLE. No regressions against the previous run.

## BLOCKED / not-checked
- Not checked: the 3 tests the suite skips here (no `tesseract` binary, no `GOOGLE_CLOUD_PROJECT`).
- Not checked: which new tests account for the +3 passed; the rendered SEO output (titles, descriptions, `noindex`, social tags) beyond what `tests/test_blog.py` and the existing suite assert; the effect of the new `noindex`/sitemap entries on real crawlers (not testable locally).
- Not checked: CI results on `0d56f72` (not read); a running local server (the suite uses the in-process `TestClient`); `/console` (super-admin), `/system/*` (forbidden for me), UAE PASS and OCR flows in the sweeps.
- Not checked: claims in other roles' reports and open PRs (treated as data).
- Open CI note (not code): `github-advanced-security` had been failing on PRs with a Copilot monthly quota error (HTTP 402) as of earlier runs; not re-checked today.

## Files and commit
- `reports/daily/2026-10-22/qa-regression.md` on `routine/2026-10-22-qa-regression`, based on `0d56f72`. Commit SHA given in the final reply (a file cannot contain its own SHA).

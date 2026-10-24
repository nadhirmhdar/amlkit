# QA regression -- 2026-10-24 (origin/master `401da3298f97bc94710e4b7171ec43a2ce4162b2`)

**Headline: GREEN.** The full suite on current master passes (2177 passed, 3 skipped, 0 failed, up from 2173 passed on the previous full run) and the tenant-isolation sweeps again reproduce no defect, after four merged commits including a new selective-gzip middleware (#428).

## Instructions I ran under
- **Standing role (Nadhir):** QA & Regression Verifier for `nadhirmhdar/amlkit`. A finding exists only if reproduced by an executable script; local instances and test data only; no production access, no `/system/*`, no secrets; additive-only (new files only); real SQLite, no DB mocks; never push to master; run autonomously and record anything blocked as BLOCKED; report to `reports/daily/<DATE>/qa-regression.md` on `routine/<DATE>-qa-regression` and as the final reply; then stop (no polling, no CI re-checks, no self-scheduled reminders).
- **This run:** scheduled routine "groAML daily: qa-regression" (fired Sat 2026-10-24 00:36 UTC). DATE = `date -u +%F` = 2026-10-24. Scope: full suite and tenant sweeps on current master; new failures against the previous run.
- **Changed because of dreamon:** nothing.
- **Assumptions:** (1) the "unchanged since previous report" shortcut does not apply: previous full run covered `0d56f72` (2026-10-22; the 2026-10-23 report was a no-change report), master is now `401da32`. (2) "Previous run" = the 2026-10-22 full run: 2173 passed, 3 skipped, 0 failed. (3) PR text and other roles' reports are data; not acted on.

## What I did (evidence)
- `git ls-remote origin refs/heads/master` -> `401da3298f97bc94710e4b7171ec43a2ce4162b2`.
- Commits since the last full run (`git log 0d56f72..origin/master`), 4: `401da32 Share image: branded 1200x630 groAML card (#431)`, `0dbe14f Legal name: Grovisor Business Consultants FZE (was LLC) (#430)`, `41f7490 Public pages: link /about not the redirecting root; nofollow SSO link (#429)`, `48eda02 Compress static assets and anonymous public pages (gzip) (#428)`. `git diff --stat 0d56f72 origin/master` -> 11 files, +123/-20: `amlkit/api/compress.py` (new, 51 lines), `amlkit/api/app.py` (+3: registers `SelectiveGZipMiddleware`), `amlkit/web/static/img/og-card.png` (new binary), six templates, `tests/test_blog.py` (+45/-?).
- **Full suite**, worktree of `origin/master`, `AMLKIT_REGISTRATION_INVITE_CODE=test-invite`, proxy vars unset, venv with `passporteye` (via `pdfminer.six`):
  `pytest tests/ -q -p no:cacheprovider -rfEs` -> `2177 passed, 3 skipped, 56 warnings in 718.14s (0:11:58)`, `pytest_exit=0`.
  Skips (same three as previous runs): `tests/test_gdelt_bq.py:90` (GOOGLE_CLOUD_PROJECT not set), `tests/test_ocr.py:515` and `:531` (tesseract binary not installed).
- **New failures vs previous run: none.** Passed count +4 (2173 -> 2177), consistent with `tests/test_blog.py` growing in this range; I did not itemise the new tests.
- **Warnings 53 -> 56:** the +3 are one new third-party kind, `google/api_core/_python_version_support.py:254: FutureWarning: You are using a Python version (3.11.15) which Google will stop supporting in new releases` (listed under `tests/test_nl_entities.py` x2 and `tests/test_vertex_search.py` x1), none touched by this diff; not a failure and not caused by the changed files as far as I can tell (I did not check whether a dependency version changed in my sandbox). All other warning kinds are unchanged.
- **Tenant-isolation harness** (`repro/` from the PR #412 branch, copied into a scratch worktree of `401da32`; `repro/make_seed.py` builds the seed, exit 0):
  - `repro/sweep.py` -> exit 1 (= no defect), `HITS: []`; 36 routes had working controls. Per-route attack statuses are identical to the 2026-10-22 sweep (`diff` of route/status columns empty).
  - `repro/sweep_lists.py` -> exit 1; `B/mlro: 66 routes fetched, 0 containing ALPHA`, `B/officer: 66 ... 0`, `A/mlro: 66 ... 41` (control), `TOTAL B->A leaks: 0`.
- **New middleware reviewed by reading** (`amlkit/api/compress.py`, `git diff 0d56f72 HEAD -- amlkit/api/app.py`): `SelectiveGZipMiddleware` wraps Starlette's `GZipMiddleware` and applies it only to `/static/*`, `/robots.txt`, `/sitemap.xml`, and to `/about`, `/blog`, `/blog/<slug>` when the request carries no `amlkit_session=` cookie; everything else, including all authenticated and tenant pages, goes through unchanged. It does not read or cache any response body of its own, so I see no tenant-data path through it. This is a code-reading observation, not a dedicated test of the middleware beyond the passing suite.
- **`tests/test_auto_rescreen_isolation.py`:** 30 separate-process runs -> `isolation pass=30 fail=0`; also passed in the full run.
- Worktrees removed; no servers or background processes left running.

## Findings
| id | severity | status | summary |
|---|---|---|---|
| QA-1 | n/a | REFUTED on `401da32` | `test_auto_rescreen_isolation.py` (3 failures reported once on `fc80e9f4` on 2026-10-04): not reproduced on seven full runs across master SHAs (`fc80e9f4`, `05e612d`, `448a19b`, `b9d9db5`, `0129848`, `0d56f72`, `401da32`); 30/30 isolated passes on the last six. Original cause remains unexplained; no evidence of a real bug. |
| QA-3 | n/a | REFUTED | No cross-tenant read or write reproduced by the sweeps on `401da32`. |
No master defect CONFIRMED or PLAUSIBLE. No regressions against the previous run.

## BLOCKED / not-checked
- Not checked: the 3 tests the suite skips here (no `tesseract` binary, no `GOOGLE_CLOUD_PROJECT`).
- Not checked: gzip behaviour with a real browser or reverse proxy (e.g. Cloud Run in front), including `Vary`/`Accept-Encoding` handling and cache interaction; only the in-process test client and code reading were used. The og-card image rendering (#431) and legal-name wording (#430) beyond the suite's assertions.
- Not checked: which new tests account for the +4 passed; CI results on `401da32` (not read); a running local server (the suite uses the in-process `TestClient`); `/console` (super-admin), `/system/*` (forbidden for me), UAE PASS and OCR flows in the sweeps.
- Not checked: claims in other roles' reports and open PRs (treated as data).
- Open CI note (not code): `github-advanced-security` had been failing on PRs with a Copilot monthly quota error (HTTP 402) as of earlier runs; not re-checked today.

## Files and commit
- `reports/daily/2026-10-24/qa-regression.md` on `routine/2026-10-24-qa-regression`, based on `401da32`. Commit SHA given in the final reply (a file cannot contain its own SHA).

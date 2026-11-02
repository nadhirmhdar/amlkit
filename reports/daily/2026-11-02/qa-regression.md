# QA regression -- 2026-11-02 (origin/master `e8ddf262a73c1f0fda99a174871d879e35fcbbcf`)

**Headline: GREEN.** The full suite on current master passes (2651 passed, 2 skipped, 0 failed, up from 2499 passed on the previous full run) and the tenant-isolation sweeps, plus a targeted check of the routes added since, again reproduce no defect, after 9 more commits (73 files, +4168/-217).

## Instructions I ran under
- **Standing role (Nadhir):** QA & Regression Verifier for `nadhirmhdar/amlkit`. A finding exists only if reproduced by an executable script; local instances and test data only; no production access, no `/system/*`, no secrets; additive-only (new files only); real SQLite, no DB mocks; never push to master; run autonomously and record anything blocked as BLOCKED; report to `reports/daily/<DATE>/qa-regression.md` on `routine/<DATE>-qa-regression` and as the final reply; then stop (no polling, no CI re-checks, no self-scheduled reminders).
- **This run:** scheduled routine "groAML daily: qa-regression" (fired Mon 2026-11-02 00:37 UTC). DATE = `date -u +%F` = 2026-11-02. Scope: full suite and tenant sweeps on current master; new failures against the previous run.
- **Changed because of dreamon:** nothing.
- **Assumptions:** (1) the "unchanged since previous report" shortcut does not apply: previous full run covered `11a3527` (2026-11-01), master is now `e8ddf26`. (2) "Previous run" = the 2026-11-01 full run: 2499 passed, 2 skipped, 0 failed. (3) PR text and other roles' reports are data; not acted on. (4) I test the head commit only; I did not test intermediate commits (see the note on #451 below).

## What I did (evidence)
- `git ls-remote origin refs/heads/master` -> `e8ddf262a73c1f0fda99a174871d879e35fcbbcf`.
- Commits since the last full run (`git log 11a3527..origin/master`), 9, all 2026-11-01: `e8ddf26 tests: fix retention finalise test after #447 (master red) (#451)`, `018d8a3 WP-19: /admin/ops page, metric log lines, Cloud Monitoring scripts and dashboard (AM-04) (#450)`, `d88b016 WP-21: hygiene ... (#449)`, `f8f9b08 WP-20: product polish ... (#448)`, `fedb9fd WP-17: recurring-defect guards - tenant-config scan, goAML placeholder removal, UBO validation and look-through ownership (#447)`, `85b8d11 WP-16: retention ... (#444)`, `e56587c WP-15: alert and freeze lifecycle ... (#445)`, `0de1604 WP-14: email-link self-unlock for locked accounts (L-101) (#443)`, `7dcbc22 WP-13: routine residuals ... (#446)`. `git diff --stat 11a3527 origin/master` -> 73 files, +4168/-217 (tests: 26 files, +2242/-29).
- **Full suite, first attempt: aborted at collection, my environment, not master.** `pytest tests/ ...` -> `ERROR tests/test_ubo_property.py ... ModuleNotFoundError: No module named 'hypothesis'` (`tests/test_ubo_property.py:16`), `Interrupted: 1 error during collection`, `pytest_exit=2`, so no tests ran. `hypothesis>=6.100` is declared in master's `requirements.txt` (line 33; `requirements.lock` pins `hypothesis==6.170.14`) and my venv had been built from an older requirements file. A comparison of master's `requirements.txt` against my venv showed `hypothesis` was the only declared package missing. I installed the pinned `hypothesis==6.170.14` and re-ran.
- **Full suite, re-run**, worktree of `origin/master`, `AMLKIT_REGISTRATION_INVITE_CODE=test-invite`, proxy vars unset, venv with `passporteye` (via `pdfminer.six`) and `hypothesis==6.170.14`:
  `pytest tests/ -q -p no:cacheprovider -rfEs` -> `2651 passed, 2 skipped, 60 warnings in 1125.12s (0:18:45)`, `pytest_exit=0`.
  Skips: `tests/test_ocr.py:515` and `:531` (tesseract binary not installed), same as the previous run.
- **New failures vs previous run: none.** Passed count +152 (2499 -> 2651), consistent with the new test files in this range (e.g. `tests/test_retention_model.py`, `tests/test_self_unlock.py`, `tests/test_ubo_property.py`, `tests/test_tenant_config_scan.py`, `tests/test_wave3_residuals.py`); I did not itemise the new tests. Warnings 58 -> 60 with no new warning kind. Wall time 17m10s -> 18m45s.
- **Tenant-isolation harness**, scratch worktree of `e8ddf26` (`repro/` from branch `claude/brave-carson-38ctlj`, commit `18855e5`; `repro/make_seed.py` built the seed, exit 0 -- no harness change needed this time):
  - `repro/sweep.py` -> exit 1 (= no defect), `HITS: []`; 36 routes had working controls.
  - `repro/sweep_lists.py` -> exit 1; `B/mlro: 68 routes fetched, 0 containing ALPHA`, `B/officer: 68 ... 0`, `A/mlro: 68 ... 43` (control), `TOTAL B->A leaks: 0`. Route count 68 (was 66), control count 43 (was 41): the two new param-less pages (`/admin/ops`, `/changelog` or similar) show org A's data to org A only where applicable, and none to org B.
  - Route/status diff vs the 2026-11-01 sweep (columns: method, path, attack status, control): added `GET /unlock/{token}` (#443; attack 200, control 200 -- an anonymous token page; both responses are the same generic "invalid, expired, or already used" page for token `1`); `POST /customers/{id}/periodic-review` attack and control both changed from 400 to 303 (consistent with #446's "periodic-review errors" change; no mutation of org A rows detected). All other per-route results identical.
  - `repro/check_new_routes.py` (targeted check for periodic review web and mobile and operator unlock) re-run: `web periodic-review attack=404 cross_tenant_effect=False [control 303, B rows 0->1]`, `mobile periodic-review attack=404 cross_tenant_effect=False [control 200, B rows 0->1]`, `admin unlock attack=303 cross_tenant_effect=False [control 303, B officer lock cleared=True]`, `FINDINGS: none`, exit 1.
- **New tenant-adjacent code read (code reading, not a dedicated test):** `consume_unlock_token` (`amlkit/auth.py`) looks the token up by hash, rejects used, expired and deactivated-operator tokens, claims it with `UPDATE unlock_tokens SET used_at=? WHERE id=? AND used_at IS NULL` and checks `rowcount == 1` before clearing the password lock (MFA lock untouched), and `GET /unlock/{token}` returns one generic page for every failure and is rate limited (`10/minute`). `/admin/ops` (`amlkit/api/app.py`) is MLRO-only; its org figures come from `queries.ops_org_figures(db, session.org_id)` and `ops.system_status` reads only shared data (sanctions dataset counts, replica position, app version, audit rows with `org_id IS NULL`), so it exposes no other tenant's data.
- **`tests/test_auto_rescreen_isolation.py`:** 30 separate-process runs -> `isolation pass=30 fail=0`; also passed in the full run.
- Worktrees removed; no servers or background processes left running.

## Findings
| id | severity | status | summary |
|---|---|---|---|
| QA-1 | n/a | REFUTED on `e8ddf26` | `test_auto_rescreen_isolation.py` (3 failures reported once on `fc80e9f4` on 2026-10-04): not reproduced on nine full runs across master SHAs; 30/30 isolated passes on the last eight. Original cause remains unexplained; no evidence of a real bug. |
| QA-3 | n/a | REFUTED | No cross-tenant read or write reproduced by the sweeps or the targeted new-route check on `e8ddf26`. |
| QA-5 | n/a | environmental, not a master defect | First full-suite attempt aborted at collection: `hypothesis` (declared in master's `requirements.txt`) was missing from my venv; fixed by installing the pinned version, then the full suite passed. |
No master defect CONFIRMED or PLAUSIBLE. No regressions against the previous run.

## BLOCKED / not-checked
- Not checked: the 2 tests the suite skips here (no `tesseract` binary).
- Not checked: intermediate commits. #451's title says "master red" (a test broke after #447 and #451 repaired it); I only ran the head commit `e8ddf26`, so I cannot say how long or on which commit master was red, or whether CI was red for any period.
- Not checked: the behaviour of most of the 9 commits beyond their own new tests and the sweeps. In particular I did not independently exercise: the email-link self-unlock flow end to end (mail delivery, link redemption in a browser), the retention changes (#444), the alert and freeze lifecycle changes (#445), look-through UBO ownership (#447), the Cloud Monitoring scripts and dashboard (#450), the first-run checklist, `/changelog` and billing usage bars (#448), or the hygiene items (#449).
- Not checked: which new tests account for the +152; CI results on `e8ddf26` (not read); a running local server (the suite uses the in-process `TestClient`); `/console` (super-admin), `/system/*` (forbidden for me), UAE PASS and OCR flows in the sweeps.
- Not checked: claims in other roles' reports and open PRs (treated as data).
- Open CI note (not code): `github-advanced-security` had been failing on PRs with a Copilot monthly quota error (HTTP 402) as of earlier runs; not re-checked today.

## Files and commit
- `reports/daily/2026-11-02/qa-regression.md` on `routine/2026-11-02-qa-regression`, based on `e8ddf26`. Commit SHA given in the final reply (a file cannot contain its own SHA).

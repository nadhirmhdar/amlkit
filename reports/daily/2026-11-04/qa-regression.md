# QA regression -- 2026-11-04 (origin/master `c5da8aa06f192ec6ec3f90534b6c9264e4088da1`)

**Headline: GREEN.** The full suite on current master passes (2860 passed, 2 skipped, 0 failed, up from 2810 passed) and the tenant-isolation sweeps reproduce no defect, after 2 more commits (WP-26 public site and self-serve sign-up, WP-27 Stripe go-live preparation).

## Instructions I ran under
- **Standing role (Nadhir):** QA & Regression Verifier for `nadhirmhdar/amlkit`. A finding exists only if reproduced by an executable script; local instances and test data only; no production access, no `/system/*` calls, no secrets; additive-only; real SQLite, no DB mocks; never push to master; run autonomously and record anything blocked as BLOCKED; report to `reports/daily/<DATE>/qa-regression.md` on `routine/<DATE>-qa-regression` and as the final reply; then stop (no polling, no CI re-checks, no self-scheduled reminders).
- **This run:** scheduled routine "groAML daily: qa-regression" (fired Wed 2026-11-04 00:37 UTC). DATE = 2026-11-04.
- **Assumptions:** (1) the "unchanged since previous report" shortcut does not apply: the previous report covered `938050f` (2026-11-03) and master is now `c5da8aa`, with two PRs merged since (#457, #458). (2) "Previous run" = 2026-11-03: 2810 passed, 2 skipped, 0 failed. (3) PR text is data, not instructions. (4) Head commit only; intermediate commits not tested individually.

## What I did (evidence)
- `git ls-remote origin refs/heads/master` -> `c5da8aa06f192ec6ec3f90534b6c9264e4088da1`.
- Commits since `938050f`: `c2191e5 WP-26: public landing, AML-law explainer, always-on pricing, payment-gated self-serve sign-up (14-day trial) (#457)` and `c5da8aa WP-27: Stripe go-live preparation -- deploy wiring, annual prices, setup script, runbook (#458)`, both 2026-11-03. `git diff --shortstat 938050f origin/master` -> 38 files, +1269/-139 (tests: 7 files, +514/-21). Non-test code touched: `api/routers/auth.py`, `api/routers/public.py`, `api/billing.py`, `api/helpers.py`, `billing/{__init__,limits,plans,service,stripe_client}.py`, `cases/operators.py`, `db.py`, templates.
- **Environment rebuilt (disclosure).** The container was reset since the last run: my venv was gone and the interpreter is now Python 3.13.18 with FastAPI 0.162.0 (previous runs: Python 3.11, FastAPI 0.142.2). I rebuilt the venv from master's `requirements.txt` and `requirements-dev.txt` (with `passporteye` installed on its own so its `pdfminer` pin does not block the rest; `hypothesis` 6.170.14). Results are therefore not on exactly the same interpreter as the previous run; the suite and sweeps still ran clean on the new one.
- **Full suite**, detached worktree of `origin/master`, `AMLKIT_REGISTRATION_INVITE_CODE=test-invite`, proxy vars unset: `pytest tests/ -q -p no:cacheprovider -rfEs` -> `2860 passed, 2 skipped, 59 warnings in 1279.74s (0:21:19)`, `pytest_exit=0`. The 2 skips are the same as before (`tests/test_ocr.py:515`, `:531`, tesseract binary not installed). No failures, no collection errors. (A first launch exited 127 because the old venv path no longer existed; no tests ran, then I re-ran after rebuilding.)
- **ID-route tenant sweep** (`repro/make_seed.py` then `repro/sweep.py`; org B attacks org A's IDs, with controls on B's own IDs and table-hash snapshots): `HITS: []`; output has the same 70 lines as the previous run, same routes, every control still reaching its expected effect. The seed builds without change, so `register_organization` default behaviour (legacy unlimited org) is unchanged.
- **List-route sweep** (`repro/sweep_lists.py`): B/mlro 73 routes, 0 containing ALPHA; B/officer 73, 0; control A/mlro 73, 45 containing ALPHA (previous run: 72 routes, 43). Param-less GET routes +1 (`/aml-law`, per #457), controls +2. `TOTAL B->A leaks: 0`.
- **New-route targeted checks** (`repro/check_new_routes.py`): periodic-review web and mobile attack=404, no cross-tenant effect; admin unlock attack=303, no cross-tenant effect; controls behave. `FINDINGS: none`.
- **Code read of the tenant-relevant changes** (not attacked):
  - `routers/auth.py` register path: in Stripe mode the invite code is skipped and `register_organization(..., pending_payment=True)` creates the org as plan `none` / `pending_payment`; `operator_org_pending` reads `organizations.plan_status` by the verified operator's own `org_id`.
  - `billing/limits.py`: `pending_payment` blocks creation of operators and customers via `check_limit`; reads stay open; it is keyed by the caller's `org_id`.
  - `billing/service.py`: the pending flag is cleared on `checkout.session.completed` using the org id in the Stripe event metadata; the webhook is signature-verified (`stripe_client.verify_webhook_signature`). I did not exercise the webhook.
- **SQL scan** (`repro/sql_scan.py`): 35 hits, same count as the previous run; none of the changed files add a new one that I could see.
- **Flaky-test check:** `tests/test_auto_rescreen_isolation.py` run 30 times: 30 pass, 0 fail.

## Findings
- **None.** No defect reproduced. (No CONFIRMED, PLAUSIBLE or REFUTED items this run.)
- Observation, not a defect: if Stripe is later turned off, `check_limit` is a no-op, so an org left in `pending_payment` becomes unrestricted until Stripe returns. #457's description already lists this as an owner item; I did not test it.

## BLOCKED / not checked
- Not attacked with scripts: the self-serve registration flow end to end (anonymous sign-up in Stripe mode, then pending-payment refusals) and the Stripe webhook, since they need Stripe test keys and a signed payload; they are covered by the suite (`tests/test_public_site.py`, `tests/test_stripe_setup.py`) and read as above. Mobile `POST /api/v1/auth/register-organization` stays invite-gated per #457; not tested.
- `tesseract` not installed: 2 OCR tests skipped. `GOOGLE_CLOUD_PROJECT` unset: cloud-backed paths run only through the suite's own mocks.
- Environment differs from earlier runs (Python 3.13 / FastAPI 0.162, see above).
- `repro/sweep.py` still reads mobile routes by regex from `amlkit/api/mobile.py`; if mobile routes move to a router module the sweep will under-cover without failing.
- Intermediate commits were not tested individually. `sweep_lists` and `sweep` logs for the previous run were lost with the container, so the previous-run comparison uses the counts in the 2026-11-03 report.

## Files and commit
- This report: `reports/daily/2026-11-04/qa-regression.md` on `routine/2026-11-04-qa-regression` (commit SHA in the final reply).
- No changes to `repro/` this run. Nothing under `amlkit-ro/` touched; no production access.

# Compliance specialist: daily report 2026-11-24

## Instructions I ran under
Regulatory Compliance Specialist (Agent 2) for groAML: strict, citation-grounded review against Federal Decree-Law 10/2025, Cabinet Resolution 134/2025, Cabinet Decision 109/2023 (UBO) and Cabinet Resolution 74/2020 (TFS). Scheduled routine "groAML daily: compliance-specialist" (fired 2026-11-24 01:16 UTC): review changes on current `origin/master` since my previous report, then check one item the previous report listed as not checked. Standing rules from Nadhir: no production access, no `/system/*` calls, no secrets, additive-only, record anything blocked as BLOCKED, push only to `routine/<DATE>-compliance-specialist` (never master), and stop after delivery with no polling or self-scheduled reminders. No message from dreamon arrived. `corpus/` and `citation_register.json` do not exist in the repo, so every Article citation below is unverified and PLAUSIBLE. This is not legal advice.

## Headline: AMBER (unchanged)
Master moved to `f3c8227` with one change (#468, `/system/grant-trial`) that I found no AML/CFT obligation problem in. The open findings, above all the CS-27 look-back (exposure window 2026-10-04 to 2026-11-18 ~14:36 UTC) and the unguarded alert-disposition race, still stand.

## What I did, with evidence
- `git ls-remote origin refs/heads/master` returned `f3c8227121fbec1d4c3860c63b4a383a4656f975`. Previous report SHA was `c42c77c`. `git log c42c77c..origin/master` shows exactly one commit: `f3c8227` "Add /system/grant-trial (owner-granted N-day trial, no card) (#468)", merged 2026-11-23 05:07 UTC.
- Read the full diff (5 files, +220/-1): `amlkit/api/routers/system.py`, `amlkit/cases/operators.py` (`grant_trial`), `tests/data/routes_master.json`, `tests/test_grant_trial.py`, `CLAUDE.md`. No screening, freeze, retention, UBO, goAML or PF code changed.
- `tests/test_grant_trial.py` and `tests/test_billing*.py`: 94 passed on `f3c8227`. Full suite on `f3c8227` (scratch venv, python3.11): 3001 passed, 2 skipped, 22 failed. All 22 failures are in `tests/test_entrypoint.py` and fail with `rm: command not found` (exit 127). The tests run the entrypoint under a restricted PATH, and this sandbox's `rm` is a guard shim outside it. No entrypoint, Dockerfile or script file changed between `c42c77c` and `f3c8227`, and every other test file passes. I treat it as an environment artifact, not a regression. It is UNVERIFIED on a clean runner; the push run for `f3c8227` is `success` in CI, which is the better evidence.
- GitHub Actions: the push run for `f3c8227` (Source canary run 1255) completed `success` on 2026-11-23 05:29 UTC, followed by a scheduled run (1256, 2026-11-23 15:51 UTC) also `success`. So `f3c8227` has passed CI and the deploy job ran.
- Not-checked item picked up: draft PR #411 (database integrity audit, never reviewed before). It adds docs and agent reports only (no code). I read its audit doc for compliance-relevant claims and checked the one HIGH claim against master (finding F-1 below).

## Findings

### CS-31 (INFO, CONFIRMED in code, no action needed): `/system/grant-trial` is a vendor-side provisioning path, not a customer-CDD path
`grant_trial` creates an organisation (plan `trial`, `trialing`, `trial_ends_at = now + days`, 1 to 90) and its first MLRO with `email_verified_at` pre-set, behind `ADMIN_API_SECRET`. Checks I made:
- The new org's MLRO still goes through `auth.mfa_lock_session()` on login (CLAUDE.md MFA rule; `role="mlro"` is set), so the MLRO MFA control is not bypassed. PLAUSIBLE basis: Law 10/2025 Art 20 (senior management/MLRO accountability).
- `check_limit` (the only consumer of `write_blocked`) gates creation of operators and customers only. An expired trial therefore cannot stop screening, freeze execution, report submission or retention on existing records. This matters for the 24h freeze duty (Law 10/2025 Art 17, Res 74/2020 Art 15, Res 134/2025 Art 32, all PLAUSIBLE). The dated trial is only enforced when `AMLKIT_BILLING_ENABLED` is on, and it is off by default.
- Audit trail: `billing.trial_granted` and `operator.create` rows are written with `org_id`. The actor is the literal `"system"`, not a named owner, so the audit row does not identify which person at the vendor granted the trial. LOW observation for the 8-year audit/retention expectation (Law 10/2025 Art 25, Res 134/2025 Art 24, PLAUSIBLE). Suggest passing a named actor.
- The email is marked verified without a proof-of-control step. That is a trust decision by the secret holder, consistent with `/system/create-operator`. No change recommended.

### F-1 (MEDIUM, PLAUSIBLE, new to my register): alert disposition UPDATE has no status guard, so a concurrent decision can overwrite a confirmed match
Source: draft PR #411 audit doc (its finding 1, with a probe it reports). On master `amlkit/cases/review.py` (unchanged since `c42c77c`), `propose_disposition` (UPDATE at line 359) and `confirm_disposition` (line 465) check "already final" with a separate SELECT, then run `UPDATE alerts ... WHERE id=? AND org_id=?` with no `AND status IN (...)` guard. I confirmed the code shape. I did not reproduce the race (needs two concurrent writers); the sequential double-disposition case is blocked by the check at issue #167. Consequence if it occurs: a confirmed sanctions match could end up recorded as a single-operator dismissal while an auto-created freeze obligation stays live. Relevant to Res 74/2020 Art 15 and Law 10/2025 Art 17 (PLAUSIBLE). Likelihood is low (single-tenant SQLite, few operators). Fix is a one-line guard plus a `rowcount` check at each site.

### F-2 (LOW, PLAUSIBLE): other PR #411 items with a compliance angle
- Its finding 4: `onboard()` commits the customer before screening and risk assessment in separate transactions, so a mid-way exception can leave a customer with no screening and no risk rating that periodic review will not pick up (CDD, Res 134/2025, PLAUSIBLE).
- Its finding 13: no expiry sweep for sessions/tokens (not an AML obligation; data-hygiene only).
I read these in the doc and did not verify each on master.

### Standing findings (unchanged, legal basis PLAUSIBLE)
- **CS-27 (HIGH, open look-back):** before #464, exact-name matches on UN/OFAC/EU/UK entries were dropped for customers with ISO nationality codes. Fix deployed 2026-11-18 ~14:36 UTC (CI evidence). Exposure window at least 2026-10-04 to that time. Still unconfirmed: that the Cloud Run revision serves traffic, that a post-deploy refresh and re-screen ran, and what alerts it raised. Legal advice needed on any reporting.
- **CS-28 (MEDIUM):** same-year, different-month DOB drops an exact name match (0.75, below 0.85), while a wrong year alerts. Not re-probed (scorer unchanged).
- **CS-13 (HIGH, open):** 24h freeze clock starts at `identified_at` (confirmed disposition), not designation.
- **CS-14 (MEDIUM, open):** PNMR unsupported (`SUPPORTED_REPORT_TYPES = {"STR","SAR","FFR"}`).
- **3.1 (MEDIUM, open):** AED 55,000 DNFBP cash threshold (Res 134/2025 Art 21) is organisation-configurable.
- **CS-24 (MEDIUM, partly closed):** UAE PASS verification rows do not record environment.
- **CS-29/CS-30 (LOW):** PEP fold edge cases. FATF items, CS-4 Interpol, CS-18, the 5-versus-8-year retention question: unchanged.

## BLOCKED / not checked
- **Primary legal text: BLOCKED.** Official hosts refused egress on 2026-10-06; not retried or bypassed. To unblock: provide the official PDFs of the four instruments as `corpus/` plus `citation_register.json`.
- **Production state: not checked** (no production access): live Cloud Run revision, Cloud Scheduler schedule, post-deploy re-screen and its alerts (CS-27), UAE PASS production status.
- F-1 race not reproduced (needs concurrent writers). PR #411 findings 4 and 13 not verified on master. Gender-mismatch penalty against exact-name matches: still untested.

## Files and commit
- `reports/daily/2026-11-24/compliance-specialist.md` on `routine/2026-11-24-compliance-specialist`.
- Based on master `f3c8227121fbec1d4c3860c63b4a383a4656f975`. Report commit SHA: see the final reply. Master untouched.

# code-reviewer daily report, 2026-11-01

**Instructions I ran under:** scheduled routine "groAML daily: code-reviewer" (fired 2026-11-01 00:45 UTC). Review current origin/master, the changes since the SHA in my previous report, and PRs opened or updated since. Standing rules: no production access, no `/system/*` calls, no secrets, local test data only, never push to master, stop after delivering.

**Headline: AMBER.** origin/master moved from `401da3298f97bc94710e4b7171ec43a2ce4162b2` to `11a3527ef94126da09860257e583a2e46e87e958` (11 PRs, #432-#442, 117 files, +7.4k/-1.3k): the suite is green and two long-open findings are fixed, but I confirmed three LOW crash bugs (one a new regression in MFA) and could not review every area.

**What I did (evidence):**
- `git ls-remote origin refs/heads/master` returned `11a3527…`; `git log 401da32..origin/master` lists #432 uploads, #433 freeze scope and one-time secrets, #434 Stripe billing, #435 login lockout, #436 screening correctness, #437 password/identity helper, #438 periodic CDD review, #439 robustness, #440 remove kg-screen/gdelt-bq, #441 governance, #442 web hygiene. All were merged on 2026-10-31.
- Full suite on `11a3527` in a throwaway worktree (Linux, `.venv`): **2499 passed, 2 skipped**, 15 min 51 s (previous baseline 2177 passed, 3 skipped).
- Read in full: `billing/stripe_client.py`, `api/billing.py`, `billing/service.py`, `billing/limits.py`, the `auth.py` diff, `sanctions_scope.py`, the `db.py` diff, the `storage.py` diff and the `validation.py` upload guard.
- Probed with dummy secrets and throwaway DBs, no network and no `/system/*`: the Stripe webhook route, `auth.mfa_verify`, `auth.csrf_valid`.
- Checked that the `datasets.key` values in `sanctions_scope.py` match the real ingest keys (`un_consolidated`, `ae_local_terrorists`, plus `un_sc_sanctions` and the `eocn_` prefix). Migrations are additive column-adds and new tables, all guarded.
- Billing design: reads are never gated; only creation of operators and customers is refused, and legacy orgs are unlimited. Compliance work such as freezes, STRs and screening cannot be locked out by a lapsed subscription.

**Resolved since last report:**
- CR-12 (MEDIUM): fixed by #436. `screenings.unscreenable` is persisted; the onboarding summary, customer page banner, rescreen and mobile payload surface it. I verified the code paths and the new tests; I did not re-probe it end to end.
- CR-14 (LOW): fixed by #439. `/system/*` bearer checks now use `deps.bearer_ok`, which compares bytes.

**Findings:**
- CR-24 (LOW, CONFIRMED): `POST /billing/webhook` returns **500** for a non-ASCII `Stripe-Signature` header. `stripe_client.verify_webhook_signature` calls `hmac.compare_digest` on `str`; I reproduced it with a latin-1 header. Same class as the old CR-14. It is unauthenticated but changes no state and only runs when Stripe is configured. Fix: compare `.encode()` bytes.
- CR-25 (LOW, CONFIRMED, regression from #433/L-40): `auth.mfa_verify` compares `hmac.compare_digest(totp.generate_otp(step), code)` on `str`. A code containing any non-ASCII character, such as Arabic-Indic digits, raises `TypeError`, so `/mfa/verify` returns 500 instead of "Invalid code". It happens before the failed-attempt counter, so it adds no lockout bypass for real codes. Before #433 the same input returned False. Arabic-keyboard MLROs can hit this by accident.
- CR-26 (LOW, CONFIRMED, pre-existing, not covered by #439): `auth.csrf_valid` calls `secrets.compare_digest(cookie_value, form_value)` on `str`. A non-ASCII `csrf_token` form value is a 500, not a 403.
- CR-27 (LOW, PLAUSIBLE): `billing/service.py` applies `customer.subscription.*` and `invoice.*` events in arrival order and never uses `event.created`; `retrieve_subscription` has no callers. Stripe does not guarantee ordering, so a late older event could overwrite a newer status. Only matters once Stripe is configured; the audit rows would show it.
- CR-28 (INFO, needs compliance sign-off): #433 limits freeze obligations, the 24-hour clock, the overdue email and CNMR to UN and UAE-local lists, so OFAC/EU/UK-only matches stay alerts. This reverses the "deliberately not changed" note in #421. The code matches its Cabinet Decision 74/2020 rationale, and I could not verify the legal position from this repo.
- CR-1b (LOW, partly mitigated): the legacy name-comparison fallback in `confirm_disposition` now logs a warning (L-27), but still exists.
- INFO: `storage.check_client_filename` rejects any `..` in a filename, so a legitimate name like `passport..pdf` is refused.
- Carried, unchanged: CR-4 (MEDIUM, unmerged #417; not re-checked), CR-13 and CR-18 (LOW; not re-checked), CR-2/3/5/17, CR-19 to CR-23 (INFO).

**BLOCKED / not checked:**
- Nothing blocked.
- I did not review in depth: #438 periodic review, #441 governance (downgrade reason, deadline API, UBO diagram, KYT page, UAE PASS identity match), the `mobile.py` changes (+304), the #442 security-header and CSP interplay, `app.js`, the billing templates, and the deletions in #440.
- I did not re-measure the `alert_queue` slowdown (CR-13) after the `queries.py` changes.
- CI status for `11a3527` was not looked up (standing rule: no CI re-checks).
- Nothing was exercised against real Stripe.

**Files / commits:** `reports/daily/2026-11-01/code-reviewer.md`; commit SHA in the final reply.

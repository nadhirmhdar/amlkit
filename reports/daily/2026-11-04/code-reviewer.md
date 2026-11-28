# code-reviewer daily report, 2026-11-04

**Instructions I ran under:** scheduled routine "groAML daily: code-reviewer" (fired 2026-11-04 00:46 UTC). Review current origin/master, the changes since the SHA in my previous report, and PRs opened or updated since. Standing rules: no production access, no `/system/*` calls, no secrets, local test data only, never push to master, stop after delivering.

**Headline: GREEN.** origin/master moved from `938050fda10fe248b2cc327ea5d0770b5cb08f01` to `c5da8aa06f192ec6ec3f90534b6c9264e4088da1` (2 PRs, #457 public site and payment-gated sign-up, #458 Stripe go-live wiring); the suite is green and I found no defect, only a few INFO-level observations about the now-open sign-up.

**What I did (evidence):**
- `git ls-remote origin refs/heads/master` returned `c5da8aa…`; `git log 938050f..origin/master` lists #457 (public landing at `/`, AML-law explainer, always-on `/pricing`, self-serve 14-day-trial sign-up) and #458 (deploy wiring, annual prices, `scripts/stripe_setup.py`, runbook). Both merged 2026-11-03.
- Full suite on `c5da8aa` in a throwaway worktree (Linux): **2860 passed, 2 skipped**, 20 min 20 s (previous baseline 2810 passed, 2 skipped). The container was rebuilt overnight and my `.venv` was gone, so I installed `requirements-dev.txt` into a fresh scratchpad venv (Python 3.13; earlier runs used 3.11). The result is not directly comparable to earlier runs on the interpreter, but nothing failed.
- Read the full `amlkit/` diff (billing, auth/public routers, `helpers.py`, `operators.py`, `service.py`, `limits.py`, `stripe_client.py`), the `source-canary.yml` change and `scripts/stripe_setup.py`.
- **Self-serve sign-up probe** with a dummy `STRIPE_SECRET_KEY`, throwaway DB, no network: `/register-organization` shows no invite field; registering without an invite creates the org as plan `none` / `pending_payment`; email verification redirects to MFA setup (mandatory for the MLRO). With the session MFA-verified, `GET /billing` works, ad-hoc `POST /screen` works (a `screenings` row is written), and `POST /customers` is refused (303 back to `/customers/new`, 0 customers created).
- Checked that the new gate sits where it should: `check_limit` raises for `pending_payment` before the legacy shortcut; `register_organization(pending_payment=False)` keeps the old unlimited behaviour; the invite gate is honoured when Stripe is not configured; `/billing*` still 404s without `STRIPE_SECRET_KEY`.
- Deploy wiring: Stripe values are passed through `--set-env-vars` like every other secret, with an empty `STRIPE_SECRET_KEY` meaning billing stays inert. No secret is echoed by `stripe_setup.py` (key read from the environment; the webhook secret is printed once, by design).

**Findings (all INFO):**
- CR-37 (CONFIRMED): the payment gate covers only creating operators and customers. An unpaid `pending_payment` org can still run unlimited ad-hoc screenings (limited to 10/min per IP), and each writes a `screenings` row with a 10-year retention date. Product decision (free taste) vs. storage-growth abuse by rotating IPs; consider a per-org cap while pending.
- CR-38 (PLAUSIBLE): with the invite code no longer required in Stripe mode, `POST /register-organization` (5/min per IP) can send verification email to any address, so it is an email-bombing amplifier at that rate. The mobile `POST /api/v1/auth/register-organization` is unchanged and still invite-gated, so the two sign-up paths now differ.
- CR-39 (INFO): Stripe keys go into Cloud Run plain env vars, as the existing SMTP and UAE PASS secrets do. Secret Manager would be the stricter option; no change from the existing pattern.
- Carried, unchanged: CR-4 (MEDIUM, unmerged #417; not re-checked), CR-13 and CR-18 (LOW; not re-checked), CR-2/3/5/17, CR-19 to CR-23, CR-28, CR-29, CR-33 to CR-36.

**BLOCKED / not checked:**
- Nothing blocked.
- Not reviewed in depth: the new templates (`landing`, `aml_law`, `pricing`, `_public_nav`, `_public_footer`) beyond a read for unescaped output, the six WP26 screenshots, `docs/runbooks/stripe-go-live.md`, the CSS, and `tests/test_stripe_setup.py`.
- `scripts/stripe_setup.py` was read, not run (it would call Stripe). The Stripe Checkout and portal flows and the live webhook were not exercised.
- I did not re-measure `alert_queue` performance (CR-13).
- CI status for `c5da8aa` was not looked up (standing rule: no CI re-checks).
- The mail path was not exercised (no SMTP; the verification link printed to the console in dev mode).

**Files / commits:** `reports/daily/2026-11-04/code-reviewer.md`; commit SHA in the final reply.

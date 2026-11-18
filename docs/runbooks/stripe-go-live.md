# Stripe go-live runbook (owner)

Goal: switch on paid self-serve sign-up for groAML (annual plans, 14-day trial) in
Stripe **test mode** first, then live. Nothing below needs a code change. Billing stays
completely off (and /pricing shows "Contact us") until **both** the master switch and
`STRIPE_SECRET_KEY` are set.

**Current state (2026-11-18): billing is switched OFF.** The Stripe option was taken out of
the product for now at the owner's request. It is controlled by one repo variable,
`AMLKIT_BILLING_ENABLED` (step 5): unset = off, even if the Stripe secrets below are in
GitHub. Organisations that signed up while it was on and are still `pending_payment`
are not blocked while it is off (limits are not enforced), and a live subscription would
stop syncing (the webhook returns 404) until it is turned back on.

Plans: Starter AED 499 / year, Professional AED 1,499 / year, Consultant "Contact us"
(no Stripe Price, not purchasable online).

## 1. Create the Stripe account (test mode)
1. Sign up at stripe.com. Business name: Grovisor Business Consultants FZE, country UAE.
2. You can stay in **test mode** (toggle "Test mode" in the dashboard) without finishing
   business verification. Live mode needs the verification to be completed (step 8).
3. Developers > API keys > copy the **Secret key** (`sk_test_...`). Keep it private.

## 2. Run the set-up script (from a checkout of the repo)
```
export STRIPE_SECRET_KEY=sk_test_...          # PowerShell: $env:STRIPE_SECRET_KEY="sk_test_..."
python scripts/stripe_setup.py --webhook-url https://groaml.grovisor.ae/billing/webhook --dry-run
python scripts/stripe_setup.py --webhook-url https://groaml.grovisor.ae/billing/webhook
```
It creates "groAML Starter" / "groAML Professional" with yearly AED prices and the webhook
endpoint, then prints the secrets and variables to paste. Safe to re-run (it finds existing
objects). **The webhook signing secret (`whsec_...`) is shown only once**, at creation; if
you lose it, copy it from Developers > Webhooks > the endpoint > Signing secret.

## 3. Dashboard setting the script cannot do
Settings > Billing > Customer portal: turn on "Customers can switch plans" and add both
prices (and allow cancellation). Without it "Manage billing" cannot change plan.

## 4. Add to GitHub (repo > Settings > Secrets and variables > Actions)
Secrets tab (5):
- `STRIPE_SECRET_KEY` (the `sk_test_...` key)
- `STRIPE_WEBHOOK_SECRET` (`whsec_...` from step 2)
- `STRIPE_PRICE_STARTER` (`price_...` printed by the script)
- `STRIPE_PRICE_PROFESSIONAL` (`price_...`)
- `STRIPE_PRICE_CONSULTANT` (leave unset: Consultant stays "Contact us")

Variables tab (5):
- `AMLKIT_BILLING_ENABLED` = `1` **(the master switch; leave it unset until you are ready
  to go live, and billing stays off even with all the secrets above in place)**
- `STRIPE_DISPLAY_PRICE_STARTER` = `AED 499 / year`
- `STRIPE_DISPLAY_PRICE_PROFESSIONAL` = `AED 1,499 / year`
- `STRIPE_DISPLAY_PRICE_CONSULTANT` (leave unset)
- `AMLKIT_BILLING_PUBLIC_URL` = `https://groaml.grovisor.ae`

No value may contain `;;`. Every deploy passes these names to Cloud Run; an unset one is
simply empty and leaves that part inert.

## 5. Deploy
Push/merge to master, or re-run the latest **Source canary** workflow (Actions > Source
canary > Re-run all jobs). Wait for `Deploy to Cloud Run` to succeed, then check
`https://groaml.grovisor.ae/health` returns 200.

## 6. Verify /pricing
(With `AMLKIT_BILLING_ENABLED` unset you should instead see "Contact us" and "Request
access" everywhere, and `/billing` should 404: that is the off state.)
Open https://groaml.grovisor.ae/pricing while signed out. Expect: Starter and Professional
show their prices, Consultant shows "Contact us", every card's button reads
**Start free trial** (before Stripe was configured it read "Request access").

## 7. End-to-end test sign-up (test mode)
1. Click Start free trial, register a new firm with a throwaway email, verify the email.
   The new organisation starts as `pending_payment` (read-only, creation blocked).
2. Sign in as the MLRO > Billing > pick a plan > Stripe Checkout.
3. Pay with card `4242 4242 4242 4242`, any future expiry, any CVC, any postcode.
4. Back on /billing: status is **trialing**, "Trial ends" is 14 days out, and creating a
   customer works. In Stripe (test mode) Developers > Webhooks the endpoint shows
   successful 200 deliveries. If the org is still `pending_payment` after a minute, check
   the webhook deliveries and that `STRIPE_WEBHOOK_SECRET` matches that endpoint.
5. Optional: use "Manage billing" to confirm the portal opens and plan switching works.

## 8. Switch to live mode
1. Complete Stripe business verification and bank details; turn Test mode off.
2. In **live** mode, copy the live secret key (`sk_live_...`).
3. Re-run the script with the live key (same command as step 2). Live mode has its own
   products, prices and webhook, so it creates new ones and prints new `price_...` /
   `whsec_...` values.
4. Repeat step 3 (customer portal) in live mode.
5. Update the **same** GitHub secrets: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
   `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_PROFESSIONAL`. Variables stay as they are.
6. Redeploy (step 5), recheck /pricing, and make one real small purchase or run a
   live-mode 100%-off coupon check before announcing.

## Rollback
Unset (or empty) the `AMLKIT_BILLING_ENABLED` repo variable, or delete/empty `STRIPE_SECRET_KEY`,
in GitHub and redeploy: billing goes inert again
(/billing* 404, no limits enforced; /pricing shows the "Request access" button).
Existing organisations keep their stored plan state.

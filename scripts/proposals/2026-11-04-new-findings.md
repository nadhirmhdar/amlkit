# HELD proposal 2026-11-04 (SS1-SS3) -- not applied, no application code edited
Applies only when STRIPE_SECRET_KEY is set (self-serve sign-up on); today's invite-gated mode is unaffected.
## SS1 /register-organization reveals which emails already have an account (amlkit/api/routers/auth.py register_org_submit; cases/operators.py)
Open sign-up returns "An account with that email already exists" for a taken address and success for a new one. Return the same page for both ("If this address is new, we sent a verification link; if you already have an account, sign in or reset your password") and, for an existing address, email the owner a notice instead. Same change for the mobile endpoint if it is ever opened.
## SS2 an unpaid (pending_payment) org keeps ad-hoc screening, scans and feedback (amlkit/billing/limits.py only gates creating operators/customers)
30 consecutive `/api/v1/screen` calls were accepted and stored for an org that never paid. Either refuse `/screen`, scan routes and other compute/data-heavy routes while `pending_payment` (reads stay open), or give pending orgs a small daily cap (e.g. 20 screenings, 5 scans) and a per-IP registration cap per day.
## SS3 verification mail goes to any address with an attacker-chosen display name ("Hi <name>")
Limit to 5/min/IP today. Add a per-address cooldown across registrations (one verification mail per address per hour), strip the name to a short safe form in the greeting, and expire unverified `pending_payment` orgs/operators after the 3-day token lifetime so abandoned sign-ups do not accumulate.

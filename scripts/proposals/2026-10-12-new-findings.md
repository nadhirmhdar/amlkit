# HELD: findings from the 2026-10-12 run (not applied; additive-only)
Evidence: reports/daily/2026-10-12/evidence/probe_uaepass_on_0129848.txt (probe: repro_redteam/probe_uaepass.py; UAE PASS token/userinfo calls stubbed, no network)

## C1 Customer UAE PASS verification is not bound to the customer's recorded identity (`record_uaepass_verification`, `app.py` `uaepass_customer_callback`)
Any UAE PASS identity completes the flow: the operator (or anyone at the operator's browser) can verify a customer with their own account. The probe verified two unrelated customers ("BRAVO-SECRET Clean Customer", nationality AE, and "Mohammed Al Testlisted", nationality LY) with one identity (`Zed Unrelated`, IRN, Emirates ID 784199012345678). Both calls succeeded ("Customer identity verified via UAE PASS"), two `uaepass_verifications` rows were written, and the same Emirates ID and type `emirates_id` were backfilled onto both customers. Nothing compares the profile's name, nationality or date of birth with the customer, and nothing flags one identity verifying several customers.
Proposal:
- Compute a match result before writing: name similarity (reuse `names.arabic.canonical_tokens` and `match.scorer.name_score` against `fullname_en`/`fullname_ar`), nationality alpha-2 equality, and ID equality when the customer already has `id_number`. Store it on the verification row (additive columns) and refuse the "verified" flash unless it passes, otherwise show "UAE PASS identity does not match this customer".
- Reject or flag when `idn` or `uaepass_uuid` already verifies a different customer in the org, and never backfill `id_number` from a non-matching profile.

## S1 SSO ignores the password lockout (informational, `auth.login_via_uaepass`)
A password-locked account (8 failures) can still sign in through UAE PASS SSO if linked (probe section 4). That is a useful break-glass for the account-lockout DoS in `2026-10-11-new-findings.md`, and the MLRO MFA lock still applies (redirect to `/mfa/*`). Keep it, and document it as the supported recovery path.

## S2 Email-based linking trusts the UAE PASS `email` claim at SOP2 (informational, `auth.resolve_uaepass_operator`)
A SOP2 identity whose email claim equals a verified operator email is linked on first use (probe: SOP2 linked, SOP1 refused). Whether UAE PASS verifies the email claim at SOP2 is not established in this repo (the parser comes from a third-party summary, `uaepass.py` module docstring). Consider an admin-confirmed link step for MLRO accounts instead of automatic email linking.

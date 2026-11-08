# mlro-user daily report — 2026-11-08

**Headline: GREEN** — master moved to 9219e26 (three commits, #460–#462); all 38 of my earlier walks still pass and the fixes that target my last findings (reason codes, empty bulk dismissals, UAE PASS and freeze-scope claims) work. Remaining items are low-severity and listed below.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to see what the new commits changed and to locate behaviour.
- Report to branch `routine/2026-11-08-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master changed: `git ls-remote origin refs/heads/master` = `9219e2623b3a3ba7e73a20e44c703ab80df7e900` (previous report: 6560fb0). Highest PR ref now 462. Commits: #462 WP-29 launch blockers (sign-up enumeration, honest email-failure page, accurate public claims, unpaid-org scans, PR secret gating), #461 WP-30 reason codes must fit the disposition, sanctions refresh every 4 hours, #460 SEO round 2 (HEAD on public pages, static JSON-LD, gzip). Not the shortcut.
- Headline is GREEN because every finding that targeted these commits is fixed and I found nothing medium or higher today; the headline reflects only the current state of what I walked, not that earlier low items are all closed.

## What I did (evidence: `mlro-user-evidence/*.json`; driver `mlro_user_drive.py`, modes `bulk05`, `single05`, `pub04`, `enum08`, `head08` and all earlier modes)
1. **Regression:** re-ran all 38 earlier driver modes on 9219e26. All exit 0, no tracebacks.
2. **BD1 retest (#461):** closing an alert as a false positive with reason `confirmed_match` is now refused on both the single and bulk paths: "reason code 'confirmed_match' does not fit the disposition 'false_positive'; allowed for false_positive: different_dob, different_nationality, name_coincidence, different_entity_type, other". Valid reasons still work; `other` still needs a narrative; sanctions dismissals still go to second review.
3. **BD2 retest (#461):** an unknown customer, another organisation's customer, or a customer with nothing open now says "No open alerts to dismiss for this customer; nothing was changed." instead of a success banner.
4. **Public claims (#462):** the landing page shows the UAE PASS sentence only when UAE PASS is live (it is not in this configuration, so the page now says "Capture details from Emirates ID and passport scans"), and the freeze statement names the UN Security Council and UAE Local Terrorist lists. MK1 and MK2 are closed.
5. **Sign-up (#462):** the invite-code registration path still tells a visitor that an email already has an account; the open self-serve path (payment-gated) is the one changed to answer identically for new and existing emails. I could not drive that path (Stripe not configured here).
6. **HEAD (#460):** HEAD requests succeed on public pages and static files; HEAD on `/customers`, `/dashboard`, `/audit`, `/customers.csv` and the evidence PDF returns 405 with no body, so nothing private is exposed. Anonymous `/about` is gzipped and carries no CSRF token.

## Findings
- **Fixed since last report:** BD1 (contradictory reason code), BD2 (empty bulk dismissal looked like success), MK1 (UAE PASS claim), MK2 (freeze scope wording).
- **SU1 (info, CONFIRMED):** On the invite-code registration path the message "An account with that email already exists" and "An organization with a similar name already exists" are still shown. This is by design for invite holders; the anonymous self-serve path is the one hardened. Could not be exercised here.
- **CR1 / CR2 / CR3 (unchanged, CONFIRMED earlier):** no way to correct a customer's identity details after onboarding; duplicate persons accepted; case-sensitive references. Not part of these commits.
- Sanctions refresh every 4 hours (#461): cannot be observed locally (the schedule runs in the deployment; no network).
- Still open from earlier reports: UBO1b, F4, TA2, TA3, high-risk-country field, E2-E5, LN1, SE2, PR5 and the other lows.

## BLOCKED / not checked
- The open self-serve sign-up and 14-day trial (needs Stripe configuration), the unpaid-organisation scan limits (#462), and the 4-hour refresh cadence.
- Rate limiting (my driver disables the limiter), HSTS, goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-08/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-08-mlro-user`; commit SHA in the final reply.

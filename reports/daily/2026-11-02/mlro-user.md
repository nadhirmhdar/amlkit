# mlro-user daily report — 2026-11-02

**Headline: AMBER** — master moved to e8ddf26 (nine more commits, #443–#451); every remaining item from my last report that these commits target is now fixed, and I found one new gap (a company can be listed as its own beneficial owner).

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to see what the new commits changed (commit messages, the unlock handler, CLAUDE.md note) and to locate routes.
- Report to branch `routine/2026-11-02-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master changed: `git ls-remote origin refs/heads/master` = `e8ddf262a73c1f0fda99a174871d879e35fcbbcf` (previous report: 11a3527). Highest PR ref now 451. Commits: #446 WP-13 routine residuals, #443 WP-14 email self-unlock, #445 WP-15 alert/freeze lifecycle, #444 WP-16 retention, #447 WP-17 recurring-defect guards (goAML placeholders, UBO validation/look-through), #448 WP-20 product polish (first-run checklist, /changelog), #449 WP-21 hygiene, #450 WP-19 /admin/ops, #451 test fix. Not the shortcut.

## What I did (evidence: `mlro-user-evidence/log_wave2.json`, `log_wave2b.json` and the earlier logs; driver `mlro_user_drive.py`, modes `wave2`, `wave2b`)
1. Re-ran all 31 earlier driver modes against e8ddf26: all exit 0, no tracebacks (the password and dataset-key changes I made for the last build are already in the driver).
2. Walked the new and changed workflows below.

## Results
- **Self-unlock (#443): works.** The 8th wrong password locks the account and mails one single-use link to the verified address (exactly one mail for a lock window, even with further wrong attempts). While locked, the correct password is refused. Opening the link redirects to `/login` with "Your account is unlocked"; the same link a second time, and a bogus token, both show the same generic "invalid, expired, or already used" page. Login works afterwards. Audit rows `operator.unlock_mailed` and `operator.self_unlock` are present. LG1 (account lock-out by an outsider) is therefore now recoverable by the account owner without a second MLRO. Earlier the MLRO unlock route (#435) also exists.
- **Eviction notice (#446): fixed.** The 4th login now lands the oldest session on `/login` with "You were signed out because this account reached its limit of 3 sessions." (SS1 closed.)
- **Periodic-review errors (#446): fixed.** A too-short note returns a banner on the case file, not raw JSON (PR4 closed).
- **True-positive standing record (#445): fixed.** After a confirmed true positive, two re-screens add no new alert (G10 closed; previously one duplicate open alert).
- **Resolve with a draft CNMR (#445): fixed.** "File or discard the draft CNMR first." (FZ4 closed.)
- **UBO validation (#447): working.** Total over 100% refused ("would be 110%"), negative and non-numeric percentages refused with clear messages, ownership percentage optional for a senior managing official.
- **New pages:** `/changelog` (MLRO and officer can read, anonymous redirected), `/admin/ops` (MLRO only; officer redirected to `/`, anonymous to `/login`) shows data freshness, replication and work queues, and the dashboard shows a "Get started with groAML — 4 of 5 done" checklist with a dismiss action.

## Findings
- **UBO1 (low-medium, CONFIRMED):** A legal entity can be added as its own beneficial owner. Adding "Gulf Holdings LLC" as a 30% owner of customer "Gulf Holdings LLC" was accepted ("Beneficial owner added and screened clear") and appears in the ownership list. A self-reference defeats look-through ownership and inflates the disclosed percentage.
- **UL1 (low, PLAUSIBLE):** When SMTP is not configured the unlock mail is not sent (audit shows `delivery: not_configured`), so a locked-out single-operator firm without mail setup has no self-service path. Not verifiable here; mail is unset in the sandbox by design.
- **UL2 (info):** The email link clears the password lock only; an MFA lock still requires the 15-minute wait or a second MLRO. This is documented in CLAUDE.md and intentional.
- Still open from earlier reports: F4, TA2, TA3, high-risk-country field accepting non-country text, S1, E2-E5, LN1, SE2, PR5 (officer may complete a periodic review), and the lows. Not re-checked unless listed above.

## BLOCKED / not checked
- Rate limiting (my driver disables the limiter), HSTS (needs an HTTPS run behind a proxy).
- Retention changes (#444), goAML placeholder removal (#447), billing/usage bars (#448), Cloud Monitoring scripts (#450), safe_equals regression (#446): not walked in depth today.
- goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-02/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-02-mlro-user`; commit SHA in the final reply.

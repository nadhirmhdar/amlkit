# mlro-user daily report — 2026-11-01

**Headline: AMBER** — master moved to 11a3527 (eleven commits, #432–#442, a fix wave that matches most of my earlier findings); I re-tested them and most are fixed, but the first-login password rule broke my seeded flows, a few items remain, and one new control has a rough edge.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to see what the new commits changed (commit messages, `sanctions_scope.py`, the resolve/unlock/periodic-review handlers) and to locate routes.
- Report to branch `routine/2026-11-01-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master changed: `git ls-remote origin refs/heads/master` = `11a3527ef94126da09860257e583a2e46e87e958` (previous report: 401da32). Highest PR ref now 442. Not the shortcut. Commits: #434 billing (inert), #442 WP-12 web hygiene, #441 WP-9 governance/audit, #440 WP-8 remove kg-screen/gdelt-bq, #439 WP-10 paging/KYT hardening, #438 WP-5 periodic review, #436 WP-4 screening correctness, #432 WP-3 uploads, #437 WP-7 password/identity helper, #433 WP-2+6 freeze scope/resolution, #435 WP-1 login lockout.

## What I did (evidence: `mlro-user-evidence/*.json`; driver `mlro_user_drive.py`, modes `retest`, `dupes`, `pwre`, `freezeedge` and all earlier modes)
1. Re-ran every earlier driver mode against 11a3527 (29 modes). The first pass failed everywhere at registration: the unified password helper (#437) appears to enforce the strength rule at registration too (inferred: no verification link was produced and later steps redirected to login), so my seeded password `a-strong-password-1` (no uppercase) is refused. I changed my seed passwords to compliant ones; all modes then ran. Also, my seed used dataset keys `eocn`/`un`, which the new freeze-scope rule (UN/UAE-local only) does not count, so I renamed them to the real keys `ae_local_terrorists` / `un_consolidated`.
2. Ran targeted re-tests of each earlier finding plus the new controls (periodic-review action, MLRO unlock route). Results below.

## Results of re-testing earlier findings (this build)
| Earlier finding | Result on 11a3527 |
|---|---|
| FZ1 close a confirmed-match freeze as false positive with no reason | **FIXED**: refused without a 20-char note, and refused outright while the alert is a confirmed true positive ("re-disposition via four-eyes first") |
| FZ2 authority_clearance with no authority ref | **FIXED**: "authority_clearance requires the authority's reference" |
| G9 re-screen always "failed: 'customers'" | **FIXED**: "Re-screened N name(s) … M new alert(s) raised" |
| G10 re-screen re-raises decided alerts | **PARTLY FIXED**: pending-review alerts are not re-raised; after a confirmed true positive the first re-screen still raises one new open alert for the same match (alert 3 true_positive → alert 4 open), and the second re-screen adds none |
| PR1-PR3 periodic review | **FIXED**: explicit "Complete periodic review" form (outcome + note ≥10 chars), review history on the case file, audit row `review.completed`; mobile re-assess no longer resets the clock; overdue flag on the case file |
| PW1 / PW2 password change | **FIXED**: current session stays signed in, banner now accurate; same-as-current password refused |
| OP1 / OP2 weak passwords at admin create/reset | **FIXED**: same strength rule on create and reset |
| LG2 lock message reveals the account exists | **FIXED**: locked accounts show the generic "Incorrect email or password" |
| LG3 empty password raw 422 | **FIXED**: friendly "Enter your email and password" |
| LG1 / M1 anyone can lock an account out | **MITIGATED, not removed**: 9 bad attempts still lock the account; an MLRO can now unlock (`/admin/operators/{id}/unlock`, clears sign-in and MFA locks, audited; officers get 403). A locked user is told "Incorrect email or password" even with the right password |
| AU1 / AU2 audit page paging | **FIXED**: `page=abc`, 0, -1 and a huge number are clamped, no error |
| AU3 officer on audit export | **FIXED**: redirect with a message |
| PV1 privacy page cookie list | **FIXED**: now lists five cookies |
| SE1 no noindex on signed-in pages | **FIXED**: `noindex, nofollow` plus CSP, X-Frame-Options DENY, nosniff, referrer policy (HSTS not set on a plain local run) |
| AX1-AX3 unlinked kg-screen / gdelt-bq | **FIXED by removal**: both return 404 |
| C1 nameless customer | **FIXED**: refused with "full_name is required" |
| TA1 dismiss a transaction alert with no reason | **FIXED**: false positive needs a note ≥10 chars |
| H2 threshold up to 1,000,000 | **FIXED**: warning on save and on the page; 0 and >1,000,000 refused |
| WP-2 OFAC/EU/UK matches raising a freeze | **FIXED as designed**: confirmed OFAC hit raises no freeze obligation, confirmed UN hit does |
| SS1 silent session eviction (3-session cap) | **STILL OPEN**: the 4th login evicts the oldest session, which lands on `/login` with no message |

## New findings
- **PR4 (low, CONFIRMED):** Periodic review validation errors (note too short, bad outcome) return a raw JSON 400 page (`{"detail": …}`) instead of a banner on the case file, unlike every other form.
- **PR5 (low, PLAUSIBLE):** An officer can complete a periodic review; no second-person control or MLRO-only restriction. Policy question for the firm, not necessarily a defect.
- **FZ4 (low, CONFIRMED):** An obligation can be resolved as `delisted` while the CNMR is still only a draft ("CNMR draft created, not yet filed"). After resolution, CNMR filing is blocked ("Freeze not ready for CNMR filing"), so the draft cannot be completed from the obligation.
- **SD1 (info):** The unified password rule means anything created before the change with a weak password is unaffected until its next change; I did not test legacy rows.
- **LG4 corrected:** Last report I said the login rate limit "did not return 429" and was unverified. The cause is my own harness: the driver sets `app.state.limiter.enabled = False`. Rate limits (login 10/min IP, 3/min account; mobile auth limits from #437) are therefore **NOT TESTED**, not "possibly broken".
- Still open from earlier reports (unchanged, not in this wave or not re-checked): F4, TA2, TA3, high-risk-country field accepts non-country strings (`ZZ, not a country`), S1, E2-E5, LN1, SE2, GZ items, and the other lows.

## BLOCKED / not checked
- Rate limiting (driver disables it, see above); HSTS (needs a proxy-terminated HTTPS run).
- Billing (#434): inert unless configured; Stripe not reachable. Not exercised.
- Upload guard (#432), screening dedupe on related parties (#436), mobile periodic-review route, deadline API (#441), KYT page (#441): not walked in depth today.
- goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-01/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-01-mlro-user`; commit SHA in the final reply.

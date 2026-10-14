# MLRO-user daily run — 2026-10-14 (origin/master 0129848, unchanged)

## Headline: AMBER
Master and the pull-request list have not changed since 2026-10-07, so the earlier AMBER items stand; the customer search and mobile create-customer paths walked today are sound on matching, escaping and validation, but a customer can be created with an empty name and a high-risk customer can be downgraded to low in one call with no reason.

## Instructions I ran under
- **Standing instructions (Nadhir):** MLRO user in the groAML daily team. Judge the app from outside (HTTP responses, exported files, audit trail). Local seeded instance only: no production (never groaml.grovisor.ae), no `/system/*`, no secrets. Additive-only. Run autonomously, record blocks as BLOCKED, never push to master. Report to dreamon through the branch file and this reply. When delivered, stop: no polling, CI re-checks or self-scheduled reminders.
- **This run:** the scheduled routine "groAML daily: mlro-user" fired at 2026-10-14 01:43 UTC.
- **Changed because of dreamon:** nothing.
- **Persona deviation:** none (request field names for the mobile create call were read from the route's request model).
- **Shortcut applied:** `git ls-remote origin refs/heads/master` returns `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, the SHA in my 2026-10-07 to 10-13 reports. The highest pull-request ref on the remote is still 426 (merged 2026-10-06), so none opened since. I kept this report short.

## Workflows walked this run (not covered before)
Driver `reports/daily/2026-10-14/mlro_user_drive.py` (`ONLY=search`), throwaway local DB over HTTP and the mobile API with an MFA-unlocked token; four customers (Latin, Arabic, `%`/`_` and apostrophe names) plus a second organisation.

- **Customer search (`/customers?q=`).** Works. "jaleel", the Arabic surname "الحسناوي", the Arabic form without hamza (احمد عبد الجليل) and the transliteration "Ahmad Jalil" all find the Arabic-named customer; a reference ("Q-002") finds its customer. `%`, `_` and `100%` match only the customer whose name contains them (wildcards are escaped), an apostrophe name works, `' OR 1=1 --` returns nothing, and a second organisation's customer is never returned.
- **Mobile create-customer.** Validation is good for dates ("Invalid birth_date '31/12/1985'; expected a date as YYYY-MM-DD", "birth_date cannot be in the future"), country codes ("Invalid country code 'UAE'", 'ZZ'), customer type ("Unknown customer_type 'alien'"), name length ("full_name exceeds 200 characters") and duplicate references ("Reference 'M-001' already exists."). Gaps C1 and C2 below.
- **Risk-factor edits (mobile PATCH).** Works and is audited (`customer.risk_factors_updated`, `risk.assess`); raising cash level and jurisdiction raised the rating to high (score 90, EDD required). See C3.

## Findings
| ID | Severity | Status | Finding | Evidence |
|---|---|---|---|---|
| C1 | AMBER (low) | CONFIRMED | `POST /api/v1/customers` with an empty `full_name` creates the customer (200, `customer_id` 7, rating low). A customer with no name cannot be meaningfully screened or reported. The web form marks the field required; the mobile API does not enforce it. | `log_search_mobile.json`: "mobile create: empty full_name" |
| C2 | low | CONFIRMED | An unknown `sector` ("weapons") is accepted on create (200) and on `PATCH /customers/{id}/risk-factors` (200, stored; the audit row records `{'sector': 'weapons'}`) and the rating stays low (5.0), so a mistyped or invented sector silently scores as zero risk. | `log_search_mobile.json`: "mobile create: sector 'weapons'", "risk-factors invalid sector" |
| C3 | AMBER (low) | CONFIRMED | One `PATCH` moves a customer from high (fatf_blacklist, predominantly cash, score 90, EDD required) back to low (score 5, no EDD) with no reason field, no narrative and no second review; the audit rows `customer.risk_factors_updated` and `risk.assess` show the new values only, not who approved it or why. A downgrade like this is the change an examiner asks about. | `log_search_mobile.json`: "risk-factors up", "risk-factors back down (no reason given)" and the audit rows |
| C4 | low | PLAUSIBLE | A 2,000-character search string returns two unrelated customers (Q-001, Q-002) instead of none; I did not find out how an over-long query is handled. | `log_search_mobile.json`: "customer search: 2000 chars" |

Still open from earlier reports (master identical, not re-tested): G9 ("Re-screening failed: 'customers'" on every re-screen), G10 (re-screen re-raises alerts for decided and pending alerts), OP1 and OP2 (admin password reset with a weak password crashes; admin-created accounts skip the strength rule), OP3, OP4, TA1 (transaction alert dismissed with no reason), TA2, TA3, DOC1, DOC2, N1, P1, P2, H1 to H7, E1 to E5, F4, F2b, G3 to G8, G11, T1, F5 to F9.

## BLOCKED / not checked
- **BLOCKED:** goAML XSD validation (FIU schema not in the repo); adverse media findings (needs GDELT network).
- Not exercised: `/admin/refresh`, passport and trade-licence scanning (OCR), the mobile UBO payload (my call used the wrong field names and was refused with a schema error, so UBO limits on create were not tested), the hourly scheduler (#419), email delivery (no SMTP locally).
- Not tested: the web risk-factor edit path (only the mobile API was tried), how an over-long search is truncated (C4).
- Production behaviour: not touched, per scope. SendMessage to dreamon not attempted (failed on every earlier try).

## Files
- `reports/daily/2026-10-14/mlro-user.md` (this report)
- `reports/daily/2026-10-14/mlro_user_drive.py`
- `reports/daily/2026-10-14/mlro-user-evidence/log_search_mobile.json`
- Branch: `routine/2026-10-14-mlro-user` (cut from master 0129848). Commit SHA: in the final reply.

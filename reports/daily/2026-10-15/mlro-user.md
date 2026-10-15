# MLRO-user daily run — 2026-10-15 (origin/master 0129848, unchanged)

## Headline: AMBER
Master and the pull-request list have not changed since 2026-10-07, so the earlier AMBER items stand; the match-notification, dashboard and alert-queue workflows walked today work, with three low-severity wording and coverage findings.

## Instructions I ran under
- **Standing instructions (Nadhir):** MLRO user in the groAML daily team. Judge the app from outside (HTTP responses, exported files, audit trail). Local seeded instance only: no production (never groaml.grovisor.ae), no `/system/*`, no secrets. Additive-only. Run autonomously, record blocks as BLOCKED, never push to master. Report to dreamon through the branch file and this reply. When delivered, stop: no polling, CI re-checks or self-scheduled reminders.
- **This run:** the scheduled routine "groAML daily: mlro-user" fired at 2026-10-15 01:44 UTC.
- **Changed because of dreamon:** nothing.
- **Persona deviation:** none (query parameter names for the alert queue were read from the route signature).
- **Shortcut applied:** `git ls-remote origin refs/heads/master` returns `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, the SHA in my 2026-10-07 to 10-14 reports. The highest pull-request ref on the remote is still 426 (merged 2026-10-06), so none opened since. I kept this report short.

## Workflows walked this run (not covered before)
Driver `reports/daily/2026-10-15/mlro_user_drive.py` (`ONLY=notif`), throwaway local DB over HTTP; an MLRO, an officer and a second organisation; two customers that produce matches (a sanctions list entry and a PEP list entry).

- **Match notifications.** Works. After onboarding the two matching customers the MLRO's unread count is 2 and the page lists "New screening match: … matched … (eocn) at 1.00." and the same for the PEP list, newest first. "Mark all as read" says "1 notification marked read." after one had been read individually, and the count drops to 0.
- **Dashboard.** The queue summary groups alerts by category (Proliferation financing 0, Terrorism 0, Sanctions 1, PEP 1) with "Open the queue (2)" and per-alert rows ("Unassigned · opened under 1 h ago, Match score 1.000").
- **Alert queue.** Filters work: `category=sanction` and `category=pep` each show one alert, `category=proliferation` shows none, group-by-customer, `status=all` and the two sort orders load. Assigning an alert to "Omar Officer" shows the assignee on the queue and "Assignment cleared." removes it. The side panel for an alert loads, and a second organisation gets 404 for it.

## Findings
| ID | Severity | Status | Finding | Evidence |
|---|---|---|---|---|
| NT1 | low | PLAUSIBLE | Only the MLRO is notified of a new screening match; an officer account that triages alerts has an unread count of 0 and an empty list ("No notifications.") after the same two matches. This may be intended (the page says "You are told here, and by email"), but an officer cannot learn of a match without opening the queue. | `log_notifications_queue.json`: "officer unread count {"count":0}", "officer notifications page" |
| NT2 | low | CONFIRMED | The notification page says "Open one to go straight to the alert", but opening a notification marks it read and lands on the customer page at its alerts section (`/customers/2#alerts`), not on the alert. | `log_notifications_queue.json`: "mark one read 303 /customers/2#alerts" |
| NT3 | low | CONFIRMED | Unknown queue filters are handled silently: `category=bogus` shows all open alerts as if unfiltered, and `status=bogus` shows an empty queue, in neither case with a message. | `log_notifications_queue.json`: "/alerts?status=open&category=bogus", "/alerts?status=bogus" |

Still open from earlier reports (master identical, not re-tested): G9 ("Re-screening failed: 'customers'" on every re-screen), G10 (re-screen re-raises alerts for decided and pending alerts), OP1 and OP2 (admin password reset with a weak password crashes; admin-created accounts skip the strength rule), OP3, OP4, TA1 (transaction alert dismissed with no reason), TA2, TA3, C1 to C4 (nameless customer, unvalidated sector, one-call risk downgrade), DOC1, DOC2, N1, P1, P2, H1 to H7, E1 to E5, F4, F2b, G3 to G8, G11, T1, F5 to F9.

## BLOCKED / not checked
- **BLOCKED:** goAML XSD validation (FIU schema not in the repo); adverse media findings (needs GDELT network).
- Not exercised: `/admin/refresh`, passport and trade-licence scanning (OCR), email delivery of match alerts (no SMTP locally, so the email half of "told here, and by email" was not tested), the hourly scheduler (#419).
- Not verified: whether a second organisation's attempt to mark our notification read changes anything (it redirected to its own `/notifications` with no error; I did not re-read our unread count before the later "mark all read").
- Production behaviour: not touched, per scope. SendMessage to dreamon not attempted (failed on every earlier try).

## Files
- `reports/daily/2026-10-15/mlro-user.md` (this report)
- `reports/daily/2026-10-15/mlro_user_drive.py`
- `reports/daily/2026-10-15/mlro-user-evidence/log_notifications_queue.json`
- Branch: `routine/2026-10-15-mlro-user` (cut from master 0129848). Commit SHA: in the final reply.

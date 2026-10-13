# MLRO-user daily run — 2026-10-13 (origin/master 0129848, unchanged)

## Headline: GREEN
Master and the pull-request list have not changed since 2026-10-07 and the four smaller workflows walked today (policy library, notifications, feedback, customer e-signature record) work and respect roles and tenancy; the earlier open items still stand, so this report adds one low-severity finding only.

## Instructions I ran under
- **Standing instructions (Nadhir):** MLRO user in the groAML daily team. Judge the app from outside (HTTP responses, exported files, audit trail). Local seeded instance only: no production (never groaml.grovisor.ae), no `/system/*`, no secrets. Additive-only. Run autonomously, record blocks as BLOCKED, never push to master. Report to dreamon through the branch file and this reply. When delivered, stop: no polling, CI re-checks or self-scheduled reminders.
- **This run:** the scheduled routine "groAML daily: mlro-user" fired at 2026-10-13 01:44 UTC.
- **Changed because of dreamon:** nothing.
- **Persona deviation:** none this run (form field names read from templates only).
- **Shortcut applied:** `git ls-remote origin refs/heads/master` returns `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, the SHA in my 2026-10-07 to 10-12 reports. The newest pull request is still #426 (merged 2026-10-06); none opened or merged since. I kept this report short.
- **Headline note:** I rate this run GREEN because nothing new of consequence was found today; it does not clear the open AMBER items listed below, which are unchanged because master is unchanged.

## Workflows walked this run (not covered before)
Driver `reports/daily/2026-10-13/mlro_user_drive.py` (`ONLY=misc`), throwaway local DB over HTTP; an MLRO, an officer and a second organisation.

- **Policy library.** Upload of a PDF works and a second upload with the same title becomes version 2, with v1 shown as "Archived" and both downloadable ("Uploaded 2026-10-13 by Layla MLRO"). Downloads are `application/pdf`, `attachment`, `nosniff`. HTML and a non-PDF renamed `.pdf` are refused; an invalid category is refused ("Invalid category: nonsense"). An officer cannot upload ("This action requires the mlro role; your account is officer.") but can download. A second organisation gets 404 on the first organisation's policy.
- **Notifications.** Empty state reads "No notifications."; unread count returns `{"count":0}`; "mark all read" says "0 notifications marked read."
- **Feedback.** A message is accepted; an empty message is refused (422); a message containing a script tag is stored and shown escaped on `/admin/feedback`.
- **Customer e-signature record.** Works: "Signed by Fatima Khan.", the case file shows signer, role, time, who captured it, the statement and a SHA-256 prefix, with a note that a legally binding signature needs a licensed trust service provider. An empty purpose or statement is refused (422).
- **UAE PASS.** Inert as documented: with no credentials both the operator sign-in route and the customer verification route return 404.

## Findings
| ID | Severity | Status | Finding | Evidence |
|---|---|---|---|---|
| P1 | low | CONFIRMED | The policy upload form says "File (PDF or DOCX, max 10MB)" and restricts the picker to `.pdf,.docx`, but the server refuses a DOCX with "File type not allowed or unrecognized. Allowed types: PDF, PNG, JPEG." (the error list contains no DOCX). I used a synthetic DOCX header, not a real Word file, so I cannot say whether a genuine DOCX passes; the error text is the concern. | `log_policies_notifications.json`: "upload docx" |
| P2 | low | CONFIRMED | Feedback and e-signature validation failures return raw HTTP 422 JSON (no friendly message) for empty fields; the browser form marks them required, so this takes a crafted request. | `log_policies_notifications.json`: "send empty feedback 422", "signature with empty purpose/statement 422" |

Still open from earlier reports (master identical, not re-tested): G9 ("Re-screening failed: 'customers'" on every re-screen), G10 (re-screen re-raises alerts for decided and pending alerts), OP1 and OP2 (admin password reset with a weak password crashes; admin-created accounts skip the strength rule), OP3, OP4, TA1 (a transaction alert can be dismissed with no reason), TA2, TA3, DOC1, DOC2, N1, H1 to H7, E1 to E5, F4, F2b, G3 to G8, G11, T1, F5 to F9.

## BLOCKED / not checked
- **BLOCKED:** goAML XSD validation (FIU schema not in the repo); adverse media findings (needs GDELT network).
- Not exercised: `/admin/refresh`, a real Word DOCX policy upload (P1), the 10 MB policy size limit, email notifications (no SMTP in the local run), mobile create-customer, the hourly scheduler (#419).
- Production behaviour: not touched, per scope. SendMessage to dreamon not attempted (failed on every earlier try).

## Files
- `reports/daily/2026-10-13/mlro-user.md` (this report)
- `reports/daily/2026-10-13/mlro_user_drive.py`
- `reports/daily/2026-10-13/mlro-user-evidence/log_policies_notifications.json`
- Branch: `routine/2026-10-13-mlro-user` (cut from master 0129848). Commit SHA: in the final reply.

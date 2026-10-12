# MLRO-user daily run — 2026-10-12 (origin/master 0129848, unchanged)

## Headline: AMBER
Master has not moved since 2026-10-07, so the earlier open items stand; the customer-document and transaction-alert workflows walked today are safe on file handling and tenant isolation, but a large-cash or high-risk-country alert can be dismissed with no reason or note.

## Instructions I ran under
- **Standing instructions (Nadhir):** MLRO user in the groAML daily team. Judge the app from outside (HTTP responses, exported files, audit trail). Local seeded instance only: no production (never groaml.grovisor.ae), no `/system/*`, no secrets. Additive-only. Run autonomously, record blocks as BLOCKED, never push to master. Report to dreamon through the branch file and this reply. When delivered, stop: no polling, CI re-checks or self-scheduled reminders.
- **This run:** the scheduled routine "groAML daily: mlro-user" fired at 2026-10-12 01:43 UTC.
- **Changed because of dreamon:** nothing.
- **Persona deviation:** I looked at the mobile document upload route's docstring and the names of its checks (file-type check, stored name) to know which cases to try; findings come from HTTP responses.
- **Shortcut applied:** `git ls-remote origin refs/heads/master` returns `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, the SHA in my 2026-10-07, 10-10 and 10-11 reports. The newest pull request is still #426 (merged 2026-10-06); none opened or merged since. I kept this report short.

## Workflow walked this run (not covered before)
Driver `reports/daily/2026-10-12/mlro_user_drive.py` (`ONLY=docs`), throwaway local DB over HTTP and the mobile API with an MFA-unlocked bearer token.

- **Customer documents (mobile API).** Worked. A valid PDF uploads and lists. HTML, SVG, an executable, a file with a PDF name but non-PDF content, and an empty file are refused with "File type not allowed or unrecognized. Allowed types: PDF, PNG, JPEG." A name like `../../etc/evil.pdf` is stored as `evil.pdf`. Downloads come back as `application/octet-stream` with `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`.
- **Cross-organisation isolation.** Holds. A second organisation's MLRO gets 404 listing, downloading and uploading against the first organisation's customer.
- **Case notes.** Worked. A note containing an `<img onerror>` tag is stored and shown escaped (no raw tag in the page).
- **Transaction-alert disposition.** Works, with friction (TA1, TA2). Audit rows record each disposition with the acting operator and the note.

## Findings
| ID | Severity | Status | Finding | Evidence |
|---|---|---|---|---|
| TA1 | AMBER (low) | CONFIRMED | A transaction alert (`large_cash`, `high_risk_country`) can be marked false positive with an empty note and no reason: "Transaction alert dispositioned." The sanctions-alert flow requires a reason, and a narrative for a true positive; the transaction-alert flow requires neither, and a dismissal by one operator needs no second review. An examiner will ask why the alert was closed. | `log_documents_triage.json`: "transaction alert 1 -> false_positive note=''"; audit row `{'status': 'false_positive', 'note': ''}` |
| TA2 | low | CONFIRMED | A true-positive transaction alert says only "Transaction alert dispositioned."; it does not offer or mention the next step (an STR draft or a case note), unlike a confirmed sanctions match which creates a freeze obligation. | `log_documents_triage.json` |
| DOC1 | low | CONFIRMED | No upload size limit was hit at 27 MB (a 27,263,020-byte PDF was accepted and stored), so a large upload can fill storage; the real limit is not stated anywhere I could see. | `log_documents_triage.json`: "upload big.pdf … 200" |
| DOC2 | low | CONFIRMED | `doc_type` is free text: "not_a_doc_type" is accepted and listed as is. | `log_documents_triage.json`: "upload ok.pdf (… not_a_doc_type) 200" |
| N1 | low | CONFIRMED | A 20,000-character case note is accepted without a limit. | `log_documents_triage.json` |
| TA3 | low | CONFIRMED | An invalid transaction-alert status shows the raw text "invalid disposition status: 'bogus'" (needs a crafted request). | `log_documents_triage.json` |

Still open from earlier reports (master identical, not re-tested): G9 ("Re-screening failed: 'customers'" on every re-screen), G10 (re-screen re-raises alerts for decided and pending alerts), OP1 and OP2 (admin password reset with a weak password crashes; admin-created accounts skip the strength rule), OP3, OP4, H1 to H7, E1 to E5, F4, F2b, G3 to G8, G11, T1, F5 to F9.

## BLOCKED / not checked
- **BLOCKED:** goAML XSD validation (FIU schema not in the repo); adverse media findings (needs GDELT network).
- Not exercised: UAE PASS (inert without credentials), `/admin/refresh`, policies upload and download, notifications, feedback form, web signatures, the hourly scheduler (#419), file-size ceiling above 27 MB, document retention after a customer closes.
- Production behaviour: not touched, per scope. SendMessage to dreamon not attempted (failed on every earlier try).

## Files
- `reports/daily/2026-10-12/mlro-user.md` (this report)
- `reports/daily/2026-10-12/mlro_user_drive.py`
- `reports/daily/2026-10-12/mlro-user-evidence/log_documents_triage.json`
- Branch: `routine/2026-10-12-mlro-user` (cut from master 0129848). Commit SHA: in the final reply.

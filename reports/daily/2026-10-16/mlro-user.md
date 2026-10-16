# MLRO-user daily run — 2026-10-16 (origin/master 0129848, unchanged)

## Headline: AMBER
Master and the pull-request list have not changed since 2026-10-07, so the earlier AMBER items stand; the passport and trade-licence scan endpoints walked today are protected by session and CSRF, but an unreadable or non-image upload returns "success" with every field empty and the page says "Scan complete".

## Instructions I ran under
- **Standing instructions (Nadhir):** MLRO user in the groAML daily team. Judge the app from outside (HTTP responses, exported files, audit trail). Local seeded instance only: no production (never groaml.grovisor.ae), no `/system/*`, no secrets. Additive-only. Run autonomously, record blocks as BLOCKED, never push to master. Report to dreamon through the branch file and this reply. When delivered, stop: no polling, CI re-checks or self-scheduled reminders.
- **This run:** the scheduled routine "groAML daily: mlro-user" fired at 2026-10-16 01:43 UTC.
- **Changed because of dreamon:** nothing.
- **Persona deviation:** I read the scan upload code in `amlkit/web/static/js/app.js` (the page's own script) to see what message the user is shown after a scan; the findings about the endpoints come from HTTP responses.
- **Shortcut applied:** `git ls-remote origin refs/heads/master` returns `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, the SHA in my 2026-10-07 to 10-15 reports. The highest pull-request ref on the remote is still 426 (merged 2026-10-06), so none opened since. I kept this report short.

## Workflow walked this run (not covered before): identity-document scanning
Driver `reports/daily/2026-10-16/mlro_user_drive.py` (`ONLY=scan`), throwaway local DB over HTTP. Both `POST /customers/scan-passport` (`passport_file`) and `POST /customers/scan-trade-licence` (`licence_file`) were given: a PNG with synthetic passport-style text, a blank PNG, a PDF, an HTML file, a text file renamed `.png`, an empty file and a 25 MB file.

- **Access control.** Works. With no session the endpoint returns 401; with a session but no CSRF token it returns 403 ("Session expired or the form was submitted from a stale page. Reload and try again.").
- **Result for every test file.** HTTP 200 with every field `null` (`full_name`, `nationality`, `birth_date`, `gender`, `id_number`, `authenticity`) and `expiry_check` with all `null` and an empty `flags` list; the trade-licence endpoint likewise returns `null` fields and an empty `field_confidence`. Nothing distinguishes an unreadable file from a readable one.
- **Success path.** Not tested: `tesseract` is not installed in this sandbox, so no real MRZ could be read (BLOCKED below).

## Findings
| ID | Severity | Status | Finding | Evidence |
|---|---|---|---|---|
| S1 | AMBER (low) | CONFIRMED | When a scan reads nothing (blank image, text, HTML, empty file), the endpoint still returns 200 and the page shows "Scan complete (MRZ not read — fields extracted via OCR fallback have no authenticity check)." — which says fields were extracted when none were. The page's "Scan failed. Please enter manually." message appears only for a non-200 response. Related risk: the document check shows no warning (`flags` is empty) for an unreadable passport, so an expired or tampered document is not flagged because nothing was read. | `log_scan.json` (all rows); script text in `amlkit/web/static/js/app.js` ("Scan complete (MRZ not read…") |
| S2 | low | CONFIRMED | The scan endpoints do not check the file: an HTML file, an empty file and a 25 MB file are all accepted and processed, unlike customer-document upload, which refuses anything but PDF, PNG or JPEG ("File type not allowed or unrecognized. Allowed types: PDF, PNG, JPEG."). | `log_scan.json`: "scan-passport: html", "empty file", "25 MB png-ish" |

Still open from earlier reports (master identical, not re-tested): G9 ("Re-screening failed: 'customers'" on every re-screen), G10 (re-screen re-raises alerts for decided and pending alerts), OP1 and OP2 (admin password reset with a weak password crashes; admin-created accounts skip the strength rule), OP3, OP4, TA1 (transaction alert dismissed with no reason), TA2, TA3, C1 to C4, NT1 to NT3, DOC1, DOC2, N1, P1, P2, H1 to H7, E1 to E5, F4, F2b, G3 to G8, G11, T1, F5 to F9.

## BLOCKED / not checked
- **BLOCKED:** a successful passport or trade-licence scan (needs `tesseract`, which is not installed here); goAML XSD validation (FIU schema not in the repo); adverse media findings (needs GDELT network).
- Not exercised: `/admin/refresh`, email delivery (no SMTP locally), the hourly scheduler (#419).
- Not verified: how the page behaves when the browser itself rejects a file type (the file picker's `accept` attribute was not checked).
- Production behaviour: not touched, per scope. SendMessage to dreamon not attempted (failed on every earlier try).

## Files
- `reports/daily/2026-10-16/mlro-user.md` (this report)
- `reports/daily/2026-10-16/mlro_user_drive.py`
- `reports/daily/2026-10-16/mlro-user-evidence/log_scan.json`
- Branch: `routine/2026-10-16-mlro-user` (cut from master 0129848). Commit SHA: in the final reply.

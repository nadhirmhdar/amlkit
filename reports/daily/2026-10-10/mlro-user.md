# MLRO-user daily run — 2026-10-10 (origin/master 0129848, unchanged)

## Headline: AMBER
Master has not moved since my 2026-10-07 report, so the open items there stand; the one workflow I had not walked before, exports and the evidence pack, is sound, but the compliance calendar cannot be used from the screen.

## Instructions I ran under
- **Standing instructions (Nadhir):** MLRO user in the groAML daily team. Judge the app from outside (HTTP responses, exported files, audit trail). Local seeded instance only: no production (never groaml.grovisor.ae), no `/system/*`, no secrets. Additive-only. Run autonomously, record blocks as BLOCKED, never push to master. Report to dreamon through the branch file and this reply. When delivered, stop: no polling, CI re-checks or self-scheduled reminders.
- **This run:** the scheduled routine "groAML daily: mlro-user" fired at 2026-10-10 01:43 UTC. Three firings (10-08, 10-09, 10-10) reached this session together after a worker restart, so no run happened on 10-08 and 10-09; this one report covers 10-10.
- **Changed because of dreamon:** nothing.
- **Persona deviation:** none this run beyond checking templates and one grep to confirm that nothing on the screen creates a calendar deadline.
- **Shortcut applied:** `git ls-remote origin refs/heads/master` returns `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, the SHA of my 10-07 report. No pull request was opened or merged after #426 (merged 2026-10-06; the newest pull request number is 426). So I did not re-walk the earlier workflows and kept this report short.

## Workflow walked this run (not covered before)
Driver `reports/daily/2026-10-10/mlro_user_drive.py` (`ONLY=exports`, `ONLY=xorg`), throwaway local DB over HTTP, six customers including formula-injection, quote/newline and Arabic names, a second organisation, an officer account.

- **Customer, alert and audit CSV exports.** Worked. Leading `=`, `+`, `@` in a name are neutralised with a leading apostrophe (`'=HYPERLINK(…)`, `'+cmd|…`, `'@SUM(1+1)`). Arabic and a name with a comma, quotes and a line break round-trip intact. `/audit/export` records each export as an audit row (`export.alerts_csv`, …) and returns 403 to an officer.
- **Evidence pack.** Worked. `/customers/{id}/evidence` renders (generated timestamp, "Print / save as PDF", "Download PDF") and `/evidence.pdf` returns a real PDF (`%PDF-`, 39 KB, filename `evidence-1-Ahmed_Abd_Al-Jaleel_Al-Hasnawi.pdf`).
- **Cross-organisation isolation.** Holds. A signed-in MLRO of a second organisation gets 303 (customer page, evidence page, report) or 404 (evidence PDF, alert panel) for the first organisation's records, and neither CSV contains the other organisation's names.
- **Compliance calendar.** Friction and findings E1, E2.

## Findings
| ID | Severity | Status | Finding | Evidence |
|---|---|---|---|---|
| E1 | AMBER (low) | CONFIRMED | `/compliance/calendar` shows "No deadlines scheduled. Compliance deadlines will appear here once created." but no page, form or script anywhere in `amlkit/web` posts to `/compliance/deadlines`, so an MLRO cannot create a deadline from the screen. Deadlines can only be created with a hand-built API request. | `log_exports.json` "compliance calendar"; grep of `amlkit/web` returns no reference to `compliance/deadlines` |
| E2 | low | CONFIRMED | The deadline API accepts nonsense: `due_date` "31/12/2026", `recurrence` "hourly" and a 5,000-character title all return 200 and are stored. A malformed date or unknown recurrence may break reminders; I did not test the reminder path. | `log_exports.json` "deadline 'bad date'", "'bad recurrence'", "'xxxx…'" |
| E3 | low | CONFIRMED | A customer name containing a line break makes the UBO diagram generator fail with a graphviz syntax error in the server log (`Error: <stdin>: syntax error in line 2 near 'Second'`); onboarding and the customer page still succeed, but the diagram is missing with no message. Names with quotes or HTML render a diagram and no script tag. | server log during `ONLY=exports`; `log_cross_org.json` "customer page, name quote+newline: svg_present=False" |
| E4 | low | PLAUSIBLE | The CSV exports have no UTF-8 byte-order mark (`bom=False`), so Excel may show Arabic names garbled when a file is opened by double-click. I did not open the files in Excel. | `log_exports.json` "customers.csv" |
| E5 | low | PLAUSIBLE | An officer can download the full `customers.csv` and `alerts.csv` (200) although `/audit/export` is MLRO-only. This may be intended; flagging because the customer list is the more sensitive file. | `log_exports.json` "officer GET …" |

Still open from the 2026-10-07 report (master identical, not re-tested): G9 ("Re-screening failed: 'customers'" on every re-screen), G10 (re-screen re-raises alerts for decided and pending alerts), H1 to H7 (KYT rule page unlinked, threshold raisable to 1,000,000 with no warning, free-text country codes accepted, audit row without previous values, raw error text, `55000.0`, feedback button over the cookie notice), F4 (duplicate-name check), F2b, G3 to G8, G11, T1, F5 to F9. Not in this report: nothing closed.

## BLOCKED / not checked
- **BLOCKED:** goAML XSD validation (FIU schema not in the repo); adverse media findings (needs GDELT network).
- Not exercised: UAE PASS, `/admin/refresh`, policies upload and download, notifications, password change and profile, mobile create-customer and document upload, the hourly scheduler (#419).
- Not tested: opening the CSV files in Excel (E4); the deadline reminder path (E2).
- Runs on 2026-10-08 and 2026-10-09 did not happen (worker restart; see above).
- Production behaviour: not touched, per scope. SendMessage to dreamon not attempted (failed on every earlier try).

## Files
- `reports/daily/2026-10-10/mlro-user.md` (this report)
- `reports/daily/2026-10-10/mlro_user_drive.py`
- `reports/daily/2026-10-10/mlro-user-evidence/`: `log_exports.json`, `log_cross_org.json`, `customers.csv`, `alerts.csv`, `audit.csv`, `evidence.txt`
- Branch: `routine/2026-10-10-mlro-user` (cut from master 0129848). Commit SHA: in the final reply.

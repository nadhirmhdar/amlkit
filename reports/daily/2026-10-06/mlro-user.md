# MLRO-user daily run — 2026-10-06 (origin/master 8750f74)

## Headline: AMBER
Most of yesterday's findings are fixed on master, but the self-rename four-eyes gap (F1) is still open and the "Re-screen all active customers" button now shows "Re-screening failed" every time it runs.

## Instructions I ran under
- **Standing instructions (Nadhir):** MLRO user in the groAML daily team. Judge the app from outside (HTTP responses, goAML XML, alerts, audit trail). Local seeded instance only: no production (never groaml.grovisor.ae), no `/system/*`, no secrets. Additive-only. Run autonomously, record blocks as BLOCKED, never push to master (a push deploys). Report to dreamon through the branch file and this reply. When delivered, stop: no polling, CI re-checks or self-scheduled reminders.
- **This run:** the scheduled routine "groAML daily: mlro-user" fired at 2026-10-06 01:43 UTC. Scope: master as of today, workflows touched since my last report, plus one workflow not exercised before.
- **Changed because of dreamon:** nothing this run.
- **Persona deviation:** I read `app.py` around the rescreen route (lines ~3695-3715) and the return statement of `rescreen_all` to name the root cause of the failure banner. Behaviour findings come from HTTP responses.
- **Assumptions:** the 4-list synthetic seed stands in for production data. CONFIRMED = reproduced this run; FIXED = reproduced yesterday and no longer reproduces today.

## Scope
- Previous report on master `28e4b51` (addendum commit `4dbe1b1`). Today's master is `8750f74de55ff72f3446ede36591858286b5773c` (`git ls-remote origin refs/heads/master`).
- Merged since: #421 (category-first alert order, non-freeze PEP wording), #424 (goAML: keep entity reference, CSRF on org-profile and logout, validate export fields at finalise), #425 (Unicode-normalise names), #403 (`/adverse-media` list), #419 (hourly freeze-obligation check), #422 (retention wording and 10-year plan), #420/#418/#423 (blog, policy and test housekeeping).
- Not exercised before and covered now: freeze obligations (confirmed match to execute, CNMR draft, resolve) and the new `/adverse-media` page.

## Workflow results
Driver: `reports/daily/2026-10-06/mlro_user_drive.py` (`ONLY=mobile|pep|run2|new|freeze|unicode|csrf`; no `ONLY` runs yesterday's full walkthrough). Throwaway local DB over HTTP.

1. **goAML STR (#424).** Fixed. Finalising a draft with no accounts is refused: "Cannot finalize report: the goAML export requires source account number; destination account number. The report is still a draft - edit it, fill these in and finalize again." The draft can be edited and re-saved ("Draft report saved."), and the export then returns 200 XML. The STR builder now pre-fills `TEST-ORG-0001` (the saved reference), `/admin` shows the saved reference, and re-saving the profile with the rendered value keeps it (DB unchanged: `TEST-ORG-0001`).
2. **CSRF (#424).** Fixed. `POST /admin/org-profile` without a token is refused with "Session expired or the form was submitted from a stale page." and nothing is saved. `POST /logout` without a token redirects to `/` and the session stays signed in.
3. **Alert order and PEP wording (#421).** Fixed. A PEP alert now reads "PEP match. This is not a sanctions designation. Apply enhanced due diligence, establish source of wealth and funds, and obtain senior-management approval before establishing or continuing the relationship." Mobile `GET /api/v1/alerts` pages are category-first (sanction at 0.85 on pages 1 and 2, PEP at 1.0 after), 60 unique ids across three pages of 20 with no overlap.
4. **Unicode names (#425).** Fixed. Each of these now screens to 1 match against the seeded entry: Arabic in presentation forms, a zero-width space, a zero-width joiner inside a token, a leading BOM, fullwidth Latin. `mlro-user-evidence/log_unicode.json`.
5. **Freeze obligations (new this run).** Worked, friction G6 to G8. A "Confirmed match" with a narrative creates freeze obligation #1 ("Auto-created from confirmed alert #1"), status Pending Execution. Executing it moves it to "Executed, Pending Report". "File CNMR" creates "CNMR draft #1" and redirects to `/reports/1`. An invalid resolve reason is refused.
6. **/adverse-media (#403).** Worked. Signed in: tabs Open (0), Relevant (0), Not relevant (0), All (0), empty state, with a pointer to Alerts. Anonymous: 303 to `/login`. Not tested with findings, since producing findings needs the GDELT network (see BLOCKED).
7. **Rename and four-eyes.** Unchanged. F1 and F4 reproduce.
8. **Re-screen all customers.** Broken (G9).

## Findings
| ID | Severity | Status | Finding | Evidence |
|---|---|---|---|---|
| F1 | AMBER (high) | CONFIRMED, still open | An MLRO can propose a sanctions dismissal, rename themselves, and confirm their own proposal: "Independent review completed." The trail then shows two different names ("Layla MLRO" proposed, "Someone Else" confirmed) with nothing marking it as one person. Single-operator mode, by contrast, is stamped "No independent review — firm operating in single-operator mode. This gap is recorded deliberately so it is visible at inspection." Severity was RED on 10-04 and 10-05 and is AMBER-high now, per the skeptic's argument that an MLRO can already switch four-eyes off; I kept it high because only the rename path produces a record that claims independence. | `log_run2.json`, `log11.json` |
| F2 | closed | FIXED (#424) | Finalising an STR without accounts. | `log11.json`: "Cannot finalize report…", "Draft report saved.", export 200 |
| F2b | low | CONFIRMED | The "Download goAML XML" link on a draft with an amount but no accounts still returns raw JSON `400 {"detail":"Cannot export goAML filing: source account number is required but missing."}`. | `log11.json`: "export before submit" |
| F3 | closed | FIXED (#424) | Saved reference shown, kept on re-save, used by the builder. | `log_run2.json`: `{'ref': 'TEST-ORG-0001'}` after re-save |
| F4 | AMBER | CONFIRMED, still open | Rename duplicate check is exact-match only: an officer renamed to "LAYLA MLRO" and "layla mlro" while "Layla MLRO" is the MLRO. | `log_new_workflows.json` |
| G1 | closed | FIXED (#421) | PEP alert shown with the sanctions freeze banner. | `log_pep.json` |
| G2 | closed | FIXED (#421) | Mobile page order disagreed with the web queue. | `log_mobile.json` |
| G3 | low | PLAUSIBLE, unchanged | An Iranian PEP at a UAE firm is scored `domestic_pep +30`. | `log_pep.json` |
| G4 | low | CONFIRMED, unchanged | Listed UBO banner "MATCH FOUND - review alerts." has no freeze or tipping-off wording, unlike onboarding. | `log_new_workflows.json` |
| G5 | low | PLAUSIBLE, unchanged | Picked grey-list for an IR customer, panel shows `fatf_blacklist +60`; form choice appears overridden by country. | `log_pep.json` |
| G6 | low | CONFIRMED | Confirming a match shows only "Disposition recorded." The banner does not say that a freeze obligation was created and now needs execution. The MLRO finds it only by opening Freeze Obligations. | `log_freeze.json` |
| G7 | low | CONFIRMED | `POST /freeze-obligations/1/execute` with a blank asset identifier succeeds ("Freeze executed successfully."). A second execute with a real account is then refused ("already executed"), so the asset detail can never be recorded. A browser form marks the identifier `required`, so this takes a crafted request. | `log_freeze.json` |
| G8 | low | CONFIRMED | Freeze timeline wording: "CNMR not yet filed", then "CNMR draft created, not yet filed" after drafting. The five-business-day clock is stated but no due date is shown on the page. | `log_freeze.json` |
| G9 | AMBER (high) | CONFIRMED, new | Every click of "Re-screen all active customers" ends with "Re-screening failed: 'customers'", even with zero customers and with one. The route reads `outcome['customers']`, but `rescreen_all` returns `{"screened", "alerts"}` (`amlkit/api/app.py` ~3712, `amlkit/match/engine.py` ~461), so a KeyError is caught after the re-screen has already run and committed. The EOCN list-change control therefore looks failed on every use. In the same run, 3 new open alerts appeared. | `log_freeze.json`, `log_run2.json`: "KeyError: 'customers'" |
| G10 | AMBER | CONFIRMED | Re-screening raises fresh open alerts for already-dismissed false positives (alerts 1 and 2 dismissed or confirmed; 3 awaiting review) and for the one awaiting independent review, giving 3 new open alerts on 3 customers whose alerts were already decided. | `log_run2.json`: `open/pending before=([], [3]) after=([4, 5, 6], [3])` |
| G11 | low | CONFIRMED, unchanged | An extra middle token clears a listed person: "Ahmed Mohammed Abd Al-Jaleel Al-Hasnawi" returns No match against "Ahmed Abd Al-Jaleel Al-Hasnawi". | `log_unicode.json` |

Carried and not re-tested: F5 (goAML XML shape, PLAUSIBLE off-schema), F6 to F9 from 10-04.

## BLOCKED / not checked
- **BLOCKED:** goAML XSD validation. The FIU schema is not in the repo.
- **BLOCKED:** adverse media findings (needs the GDELT network, so the `/adverse-media` list was only checked empty).
- Not exercised: UAE PASS, KYT rule config, evidence PDF, `/admin/refresh`, mobile create-customer and document upload, the hourly scheduler (#419, needs Cloud Scheduler), retention date wording beyond the close page.
- Production behaviour: not touched, per scope.
- SendMessage to dreamon: not attempted (it has failed on every earlier try with "No agent named 'dreamon' is reachable").

## Files
- `reports/daily/2026-10-06/mlro-user.md` (this report)
- `reports/daily/2026-10-06/mlro_user_drive.py`
- `reports/daily/2026-10-06/mlro-user-evidence/`: `log11.json`, `log_csrf_export.json`, `log_freeze.json`, `log_mobile.json`, `log_new_workflows.json`, `log_pep.json`, `log_run2.json`, `log_unicode.json`, `str_export.xml`
- Branch: `routine/2026-10-06-mlro-user` (cut from master 8750f74). Commit SHA: in the final reply.

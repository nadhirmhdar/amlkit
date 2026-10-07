# MLRO-user daily run — 2026-10-07 (origin/master 0129848)

## Headline: AMBER
The four-eyes self-rename bypass (F1) is fixed on master and holds on the web, mobile and bulk-dismiss paths; the "Re-screen all active customers" button still reports failure on every use (G9), and the newly walked KYT rule page lets an MLRO silence large-cash alerts with no warning.

## Instructions I ran under
- **Standing instructions (Nadhir):** MLRO user in the groAML daily team. Judge the app from outside (HTTP responses, goAML XML, alerts, audit trail). Local seeded instance only: no production (never groaml.grovisor.ae), no `/system/*`, no secrets. Additive-only. Run autonomously, record blocks as BLOCKED, never push to master (a push deploys). Report to dreamon through the branch file and this reply. When delivered, stop: no polling, CI re-checks or self-scheduled reminders.
- **This run:** the scheduled routine "groAML daily: mlro-user" fired at 2026-10-07 01:44 UTC. Scope: master as of today, workflows touched since my last report, plus one workflow not exercised before.
- **Changed because of dreamon:** nothing this run.
- **Persona deviation:** I read the #426 diff (`review.py`, `app.py`, `mobile.py`) to know which paths to probe, and nothing else in source this run. Behaviour findings come from HTTP responses and headless-browser measurements.
- **Assumptions:** the 4-list synthetic seed stands in for production data. FIXED = reproduced on an earlier run and no longer reproduces today.

## Scope
- Previous report: master `8750f74`, report commit `3745b73`. Today's master is `0129848` (`git ls-remote origin refs/heads/master`).
- Merged since: #426 (four-eyes self-confirm anchored to operator id, not name) and #404 (type scale: five text sizes 11/12/13/14/16 and three button heights 32/40/48). Application code otherwise unchanged (`git diff --stat 8750f74 origin/master -- amlkit`: 12 files, review/alert paths plus CSS and templates).
- Not exercised before and covered now: the KYT transaction-monitoring rule page `/admin/rule-config`.

## Workflow results
Driver: `reports/daily/2026-10-07/mlro_user_drive.py` (`ONLY=f1|rules|run2|freeze|new`; no `ONLY` runs the full walkthrough). Throwaway local DB over HTTP; a local uvicorn plus headless Chromium (Playwright) for the visual checks, stopped afterwards.

1. **Four-eyes (#426).** Fixed. After a proposal, self-confirm is refused before and after renaming myself ("independent review requires a different operator than the one who proposed the disposition…"), including after renaming back to the original name. The alert stays `pending_review`. Same result through the mobile API (`400`) and through the bulk-dismiss path. A different operator (an officer renamed to "LAYLA MLRO") can still confirm: "Independent review completed." `mlro-user-evidence/log_f1_recheck.json`.
2. **Regression of yesterday's flows.** The goAML finalise refusal, entity-reference prefill and CSRF fixes still hold (`log11.json`). Freeze obligations and the single-operator trail behave as yesterday (`log_freeze.json`, `log_run2.json`).
3. **Type scale (#404).** Headless Chromium at 390x844 and 1280x800, signed in as the MLRO, 10 pages each (dashboard, alerts, customers, a customer, screen, admin, rule-config, freeze obligations, reports, audit): no horizontal overflow on any page, and no visible text below 11px. `mlro-user-evidence/type_scale_probe.json`. See H7 and the note under findings.
4. **KYT rule configuration (new this run).** The page works, with findings H1 to H6. A threshold change takes effect on the next transaction: with the default 55,000, a 60,000 cash transaction raised `large_cash`; after raising the threshold to 1,000,000 the same transaction raised nothing; after lowering it to 10,000, a 12,000 cash transaction raised `large_cash`. Out-of-range thresholds are refused ("large_cash_threshold must be positive", "…cannot exceed 1,000,000 AED (would disable detection)"). An officer opening the page is redirected to `/admin` with no message. `log_rule_config.json`.

## Findings
| ID | Severity | Status | Finding | Evidence |
|---|---|---|---|---|
| F1 | closed | FIXED (#426) | Self-rename no longer defeats four-eyes. Residual: the check falls back to the name comparison when a proposal pre-dates the operator-id column (stated in the code comment), so a proposal still pending at deploy time keeps the old behaviour; I could not create such a legacy row over HTTP. | `log_f1_recheck.json` (a) to (e) |
| F4 | low | CONFIRMED, still open | Rename duplicate check is exact-match only; an officer renamed to "LAYLA MLRO" shows in the review trail as "LAYLA MLRO" next to the MLRO "Layla MLRO". With F1 fixed the harm is audit readability: two real operators with near-identical names. Re-rated from AMBER. | `log_f1_recheck.json` (c) |
| G9 | AMBER (high) | CONFIRMED, still open | Every click of "Re-screen all active customers" ends with "Re-screening failed: 'customers'" (zero customers and one customer alike; `KeyError: 'customers'` in the server log, from the route reading a key the engine does not return). The re-screen itself has already run and committed. | `log_freeze.json`: "rescreen, org with zero customers", "rescreen, 1 customer" |
| G10 | AMBER | CONFIRMED, still open | Re-screening raises fresh open alerts for customers whose alerts were already decided or are awaiting independent review: before open [], pending [1, 3]; after open [4, 5, 6], pending [1, 3]. | `log_run2.json` |
| H1 | low | CONFIRMED | `/admin/rule-config` is not linked from any page: no template links to it, and `/admin` does not. An MLRO can reach it only by typing the address. | `log_rule_config.json`: "linked from /admin? False"; grep of `amlkit/web/templates` |
| H2 | AMBER | CONFIRMED | The large-cash threshold can be raised to 1,000,000 AED with "Rule configuration updated successfully" and no warning on the page about weakening the detection (a 60,000 cash transaction then raises no rule). Raising is only bounded at 1,000,000. | `log_rule_config.json`: "same 60,000 cash after raising to 1,000,000 ['Transaction recorded. No rules triggered.']" |
| H3 | AMBER (low) | CONFIRMED | The high-risk-countries box accepts anything: "ZZ, not a country" was saved (stored as `['ZZ', 'NOT A COUNTRY']`), and a blank value was accepted, which empties the list, both with the success banner. | `log_rule_config.json` audit rows |
| H4 | low | CONFIRMED | The `settings.kyt_rules_update` audit row records the saved values only; the earlier values are not in the row, so an inspector cannot see what a change replaced. | `log_rule_config.json` "audit row" |
| H5 | low | CONFIRMED | A non-numeric threshold ("abc", only reachable with a crafted request, since the field is a number input) shows a raw Python error banner: "could not convert string to float: 'abc'". | `log_rule_config.json` |
| H6 | low | CONFIRMED | The form shows the threshold as `55000.0`. | `desktop_rule_config.png` |
| H7 | low | CONFIRMED (overlap) / PLAUSIBLE (click blocked) | On the phone home screen (390px, signed in) the round feedback button at the bottom right overlaps the cookie notice's "Got it" button, so the label reads "Got". Hit-testing was inconsistent between probes (the button in one, a page element in another), so I could not establish that taps are intercepted. | `phone390_home_cookie_feedback_fab.png` |
| T1 | low | PLAUSIBLE | #404 states five text sizes and three button heights (32/40/48). Measured: body text is 11/12/13/14/16, with an extra 13.65px on alerts and customer pages and larger heading sizes; button-like elements measure 32/39/40/43/44/56px. My selector counts every `button`, including navigation and the cookie notice, so this may be intended. | `type_scale_probe.json` |

Carried and not re-tested this run: F2b (draft download link returns raw JSON `400` when accounts are missing; seen again in the full run), G3 (`domestic_pep` label), G4 (UBO banner wording; seen again), G5 (tier overridden by country), G6 to G8 (freeze banner and asset wording; G6 and G7 seen again), G11 (extra middle token), F5 to F9 from 10-04.

## BLOCKED / not checked
- **BLOCKED:** goAML XSD validation. The FIU schema is not in the repo.
- **BLOCKED:** adverse media findings (needs the GDELT network).
- Not exercised: UAE PASS, evidence PDF, `/admin/refresh`, mobile create-customer and document upload, compliance calendar and policies upload, the hourly scheduler (#419).
- Legacy-proposal fallback in #426: cannot be created over HTTP, so untested.
- Production behaviour: not touched, per scope. SendMessage to dreamon not attempted (it failed on every earlier try).

## Files
- `reports/daily/2026-10-07/mlro-user.md` (this report)
- `reports/daily/2026-10-07/mlro_user_drive.py`, `reports/daily/2026-10-07/type_scale_probe.py`
- `reports/daily/2026-10-07/mlro-user-evidence/`: `log11.json`, `log_f1_recheck.json`, `log_freeze.json`, `log_new_workflows.json`, `log_rule_config.json`, `log_run2.json`, `type_scale_probe.json`, `desktop_rule_config.png`, `phone390_home_cookie_feedback_fab.png`, `str_export.xml`
- Branch: `routine/2026-10-07-mlro-user` (cut from master 0129848). Commit SHA: in the final reply.

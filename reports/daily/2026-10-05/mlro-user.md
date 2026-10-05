# MLRO-user daily run — 2026-10-05 (origin/master 448a19b)

## Headline: RED
The four-eyes bypass from yesterday (self-rename between proposing and confirming a sanctions dismissal) still reproduces on today's master, and a PEP alert is shown with a "freeze without delay, do not tip off" sanctions banner.

## Instructions I ran under
- **Standing instructions (Nadhir):** MLRO user in the groAML daily team. Judge the app from outside (HTTP responses, goAML XML, alerts, audit trail). Local seeded instance only: no production (never groaml.grovisor.ae), no `/system/*`, no secrets. Additive-only. Run autonomously, record blocks as BLOCKED, never push to master. Report to dreamon through the branch file and the final reply. When delivered, stop: no polling, CI re-checks or self-scheduled reminders.
- **This run:** the scheduled routine "groAML daily: mlro-user" (trig_01GMpFqoriVFYuq7QpUgrKv6) fired at 2026-10-05 01:37 UTC. Its scope: current master, workflows touched since my last report, plus one workflow not exercised last time.
- **Changed because of dreamon:** nothing this run.
- **Persona deviation:** I read the `mobile.py` and `queries.py` diff to learn the paging contract. Behaviour findings come from HTTP responses.
- **Assumptions:** the 4-list synthetic seed stands in for production data. CONFIRMED = reproduced this run; PLAUSIBLE = inferred.

## Scope
- Previous report: master `fc80e9f`, report commit `1bb42ee`. Master is now `448a19ba978ef5c97ee3e955ecad5638c8a94e1e` (`git ls-remote origin refs/heads/master`).
- Commits since: #406 sign-in page redesign, #402 mobile API alert paging and dashboard cap, #401 phone fixes (ownership diagram scroll, cookie notice).
- Not exercised last time and covered now: PEP and high-risk onboarding, UBO add and screen, close and reactivate a relationship.

## Workflow results
Driver: `reports/daily/2026-10-05/mlro_user_drive.py` (`ONLY=mobile|web|new|pep` for the new sections). It drives a throwaway local DB over HTTP; the sign-in page screenshots used a local uvicorn on a throwaway DB, stopped afterwards.

1. **Regression run of yesterday's full walkthrough on 448a19b.** F1, F2 and F3 reproduce unchanged (evidence below). `mlro-user-evidence/log11.json`.
2. **Sign-in page (#406, #401).** Worked. Anonymous `/login` shows no list names. The page text contains no OFAC, UN, EOCN or "sanctions list" strings. `signin-strands.js` is served (200). Headless Chromium at 390x844, 320x568 and 1280x800: the submit button is the element at its own centre point (not covered by the cookie notice) and there is no horizontal overflow. Screenshot: `mlro-user-evidence/login_phone390.png`. I did not judge the strands animation.
3. **Mobile alert paging (#402).** Worked, one ordering problem (G2).
   - Login returns `mfa_required=true`. `GET /api/v1/alerts` while locked returns `403 {"detail":"mfa_required"}`. After `/auth/mfa/verify` it returns 200.
   - 60 open alerts, pages of 20 at offsets 0, 20 and 40: `total=60`, `truncated` true, true, false, and 60 unique ids with no overlap or skip.
   - `limit=0` and `limit=-5` are clamped, `limit=9999` is capped, `offset=-1` is treated as 0, and `limit=abc` returns 422.
   - Mobile dashboard: `alerts_cap=200`, `alerts_truncated=False`, `alert_open_total=60`.
4. **PEP and high-risk onboarding.** Worked, with wording problems (G1, G3, G5). Onboarding a PEP-list name with country IR, grey-list tier and cash-heavy profile gives "Risk rating: high", score 120, EDD required, and the PEP alert opens at 1.000.
5. **UBO add and screen.** Worked. A listed UBO (Viktor Petrovich Sokolov, 60%) raises "MATCH FOUND - review alerts." and an alert. A second owner pushing the total to 105% is refused ("Total UBO ownership would be 105.0% (cannot exceed 100%)"). The risk panel shows `ownership opacity ubo_undisclosed +45` for the 40% undisclosed. Friction G4.
6. **Close and reactivate.** Worked. Close with reason "STR/SAR filed" shows "Relationship closed. Records retained until 2036-10-05."; reactivate gives "Customer reactivated."; an invalid reason gives "A valid exit reason is required".
7. **Rename duplicate check (F4).** Re-tested on this master: the officer can still be renamed to "LAYLA MLRO" and "layla mlro".

## Findings
| ID | Severity | Status | Finding | Evidence |
|---|---|---|---|---|
| F1 | RED | CONFIRMED (still open) | Four-eyes bypass: propose a sanctions dismissal, rename yourself on /admin, confirm your own proposal. | Log lines: "self-confirm own dismissal ... independent review requires a different operator"; then "MLRO renames self mid-review ['Renamed Layla MLRO to Layla Renamed.']"; then "self-confirm AFTER self-rename ['Independent review completed.']". Audit: `alert.confirm ... proposed_by: 'Layla MLRO'` by "Layla Renamed". `log11.json`. |
| F2 | AMBER | CONFIRMED (still open) | A report with no source account is finalised, then export fails with raw JSON `400 {"detail":"Cannot export goAML filing: source account number is required but missing."}` and the report cannot be edited. | `log11.json`: submit, export and re-save steps. |
| F3 | AMBER | CONFIRMED (still open) | STR builder pre-fills the hard-coded `GROVISOR-LIC-2026`; /admin does not show the saved goAML Entity Reference. | `log11.json`: "STR builder prefill ... entity_reference: GROVISOR-LIC-2026". |
| F4 | AMBER | CONFIRMED (still open) | Rename duplicate check is exact-match only. | `log_new_workflows.json`: "F4 rename officer to 'LAYLA MLRO' ['Renamed Omar Officer to LAYLA MLRO.']". |
| G1 | AMBER | CONFIRMED | A PEP alert carries the sanctions banner "SANCTIONS match. Freeze without delay and without prior notice; report to the supervisory authority. Do not tip off." The alert's own category is `pep` and the dataset is "CIA World Leaders". A PEP hit calls for EDD and senior-management approval, not a freeze, so this instruction is wrong and could lead to a wrongful freeze. | `log_pep.json`: "PEP alert row (wording)". |
| G2 | AMBER | CONFIRMED | The mobile queue's page order disagrees with the web queue. Web: category first (sanctions before PEP). Mobile pages are cut by score and only sorted by category within each page. Page 1 (offset 0, 20 rows) is all PEP at 1.0; page 2 starts with sanctions at 0.85 and then continues with PEP at 1.0. The `GET /alerts` docstring promises "highest score first", which the output does not follow either. A phone user paging a long queue sees sanctions alerts after PEP ones. | `log_mobile.json`: "mobile page offset=0 ... cats=['pep'...] scores=[1.0...]", "offset=20 ... cats=['sanction'..'pep']"; web order from `ONLY=web`. |
| G3 | low | PLAUSIBLE | The risk panel labels an Iranian PEP at a UAE firm `domestic_pep +30`. A foreign PEP is normally the higher-risk class; the label may be a mapping of any PEP-list hit. Not verified against the ruleset. | `log_pep.json`: "risk panel ... pep domestic_pep +30". |
| G4 | low | CONFIRMED | The UBO-add banner on a listed owner says only "MATCH FOUND - review alerts." Customer onboarding says "freeze without delay and do not tip off". The two entry points word the same match differently. | `log_new_workflows.json`: "add UBO matching OFAC entry". |
| G5 | low | PLAUSIBLE | I picked grey-list for an IR customer and the risk panel shows `jurisdiction fatf_blacklist +60`. The tier appears derived from the country and overrides the form choice silently; probably correct for Iran, but the form does not say so. | `log_pep.json`: "risk panel". |

Carried from the 2026-10-04 report and not re-tested this run: F5 (goAML XML shape is PLAUSIBLY off-schema), F6 to F9 (near-miss trace, alert noise, structuring inconsistency, wording).

## BLOCKED / not checked
- **BLOCKED:** goAML XSD validation. The FIU schema is not in the repo.
- Not exercised: UAE PASS, adverse media (needs network), freeze obligations, KYT rule config, evidence PDF, `/admin/refresh` and `/admin/rescreen`, mobile create-customer and document upload.
- Mobile queue longer than 200: not built. Paging was tested on 60 alerts; I did not test the 200-row boundary or the web queue past 200.
- Sign-in strands animation and dark/light modes: not judged.
- Production behaviour: not touched, per scope.

## Files
- `reports/daily/2026-10-05/mlro-user.md` (this report)
- `reports/daily/2026-10-05/mlro_user_drive.py`
- `reports/daily/2026-10-05/mlro-user-evidence/`: `log11.json`, `log_mobile.json`, `log_new_workflows.json`, `log_pep.json`, `login_phone390.png`, `str_export.xml`
- Branch: `routine/2026-10-05-mlro-user` (cut from master 448a19b). Commit SHA: in the final reply.

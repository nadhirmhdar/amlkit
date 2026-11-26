# mlro-user report, 2026-11-26

**Headline: GREEN for today's workflow, AMBER overall.** master is unchanged, so I settled yesterday's open question HP4: stale sanctions lists do not silently suppress alerts. The app refuses onboarding until lists are refreshed. The older open items still stand.

## Instructions I ran under
Routine "groAML daily: mlro-user". Local seeded instance only. No production access, no /system/* calls, no secrets, additive-only. The report goes to branch `routine/2026-11-26-mlro-user`, never master. After delivery I stop completely: no polling, CI re-checks or self-scheduled reminders.

## Base
origin/master = `f3c8227121fbec1d4c3860c63b4a383a4656f975`, the same as 11-25. The highest PR ref is still 468. Shortcut applied.

## What I did
Driver mode `ONLY=stale26`, a controlled re-run of yesterday's HP4. Evidence is in `mlro-user-evidence/log_stale26.json`.

| Step | Result |
|---|---|
| S-001 onboarded, lists fresh | 1 alert raised |
| Lists backdated to 5 days; S-002 (same name, DOB, nationality) onboarded | refused: 303 to /customers/new, "Cannot onboard: no fresh mandatory sanctions dataset available. Ask an MLRO to run Admin → Refresh sources" |
| Lists made fresh again; S-003 onboarded | 1 new alert, so 2 customers and 2 alerts in total |

## Findings
- **HP4, REFUTED.** Yesterday's 0 alerts came from onboarding being blocked, not from missed screening. Yesterday's driver did not check the onboarding response. That was my method's gap, not an app defect. Failing closed on stale lists is the right behaviour for an MLRO.
- **HP5, CONFIRMED, low.** The refusal message says "Admin → Refresh sources", but the dashboard banner calls the action "Refresh sanctions lists now". An officer who is not an MLRO sees the message but cannot act on it, which is intended. The wording mismatch could still confuse someone searching the Admin page.
- **HP3, still PLAUSIBLE.** No overdue-review indicator seen on the Ops queues. Not re-tested today.

## Open from earlier reports (not re-verified today)
UBO1b, QU1/QU2, EX1–EX3, CL1/CL2, TX1–TX3, SO1, RL1–RL3, RP1/RP2, MA1/MA2, RT1/RT2, CR1–CR3, SU1, ED1/ED2, DB1–DB3, EV1/EV2/EV4, SL1 (PLAUSIBLE), SL2, F4, TA2, TA3, E2–E5, LN1, SE2, PR5, HP2 (probably a seed artefact), HP3.

## BLOCKED / not checked
- goAML XSD validation, adverse media (GDELT network), tesseract OCR success path, SMTP delivery, HSTS and payment sign-up.
- Rate limiting: my driver disables the limiter.
- Mobile API onboarding on stale lists: not tested.
- Whether `/screen` (ad-hoc) refuses on stale lists: the page loaded but I did not submit a search. Not checked.
- `/system/*` endpoints, including `/system/grant-trial` from #468: not called, per the rules.

## Files
`reports/daily/2026-11-26/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/`.

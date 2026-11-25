# mlro-user report, 2026-11-25

**Headline: AMBER.** master is unchanged since the last report, so I ran one workflow I had not covered (Compliance Health, Ops status and dashboard banners with deliberately stale lists). The stale-list warning is accurate and consistent on all three pages. The earlier open items still stand.

## Instructions I ran under
Routine "groAML daily: mlro-user". Local seeded instance only. No production access, no /system/* calls, no secrets, additive-only. Report goes to branch `routine/2026-11-25-mlro-user`, never master. After delivery I stop completely: no polling, CI re-checks or self-scheduled reminders.

## Base
origin/master = `f3c8227121fbec1d4c3860c63b4a383a4656f975`, the same as 11-24. The highest PR ref is still 468. Shortcut applied: one new workflow, short report.

## What I did (evidence in `mlro-user-evidence/health_*.txt`, `log_health25.json`)
Driver mode `ONLY=health25`: register the org, enrol MFA, add an officer and a second MLRO, then compare the Compliance Health, Ops status and dashboard pages before and after backdating every dataset's `last_refresh` to 2026-11-20.

| Page | Baseline | After aging lists to 5 days |
|---|---|---|
| /admin/compliance | no breach | all 4 mandatory sources flagged BREACH, "121.7h ago" |
| /admin/ops | "All datasets are within their refresh window" | "4 dataset(s) past their refresh window", BREACH rows, age 5.1 days, window 24 h |
| /dashboard | "refreshed within the 24-hour window, oldest under 1 h" | "24-HOUR RULE BREACHED", lists the four sources, cites EOCN, links to the MLRO fix |

## Findings
- **HP1, REFUTED as a defect.** The three pages agree with each other and with the data. The dashboard banner is clear and actionable for an MLRO.
- **HP2, CONFIRMED, low.** Ops status says "No successful load recorded yet" while the same page shows datasets with entities and ages. My seed bypasses the loader, so this is probably a seed artefact. On a real instance the two lines would not contradict each other. Not a defect unless it also appears on a loaded instance.
- **HP3, PLAUSIBLE, low-medium.** I backdated one customer's `next_review` to 2026-01-15 by direct DB update. Neither the Ops queues (open alerts, freeze obligations pending, unfiled CNMR drafts) nor the dashboard text I captured mentions an overdue periodic review. I may have missed a section of the dashboard. If the app has no overdue-review indicator, an MLRO would not see overdue reviews outside the customer list.
- **HP4, NOT DETERMINED.** After aging the lists, onboarding "Ahmed Abd Al-Jaleel Al-Hasnawi" produced 0 alerts (alerts table empty). Earlier runs did produce alerts for this name. I did not run it with fresh lists in the same session, so I cannot say whether stale lists suppress screening or whether my seed differs. It needs a controlled re-run next time.

## Open from earlier reports (unchanged, not re-verified today)
UBO1b, QU1/QU2, EX1-EX3, CL1/CL2, TX1-TX3, SO1, RL1-RL3, RP1/RP2, MA1/MA2, RT1/RT2, CR1-CR3, SU1, ED1/ED2, DB1-DB3, EV1/EV2/EV4, SL1 (PLAUSIBLE), SL2, F4, TA2, TA3, E2-E5, LN1, SE2, PR5.

## BLOCKED / not checked
- goAML XSD validation (no FIU schema), adverse media (GDELT network), tesseract OCR success path, SMTP delivery, HSTS (needs HTTPS behind a proxy), payment sign-up.
- Rate limiting: my driver disables the limiter, so it is untested here.
- Freeze-obligation age on Ops: not exercised. My first attempt failed because no alerts existed (see HP4).
- Replication panel: shows "Replica configured: No" locally, as expected.
- `/system/grant-trial` (added in #468): not called, per the no-/system/* rule.

## Files
`reports/daily/2026-11-25/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/`. Commit SHA: see the final reply and the branch tip.

# mlro-user daily report — 2026-11-16

**Headline: AMBER** — master is unchanged (9219e26); today's walk of relationship closure shows a customer can be closed with an undecided sanctions match or an executed freeze whose CNMR is still unfiled, with no warning.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. No source read today.
- Report to branch `routine/2026-11-16-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master: `git ls-remote origin refs/heads/master` = `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, unchanged since my 2026-11-08 report; highest PR ref still 462. Shortcut applied: one new workflow, short report. Two scheduled prompts arrived together (dated 11-15 and 11-16; the session was idle in between); I treated the 11-16 run as current and wrote one report. Nothing changed in master between the two dates.

## What I did (evidence: `mlro-user-evidence/log_close16.json`; driver `mlro_user_drive.py`, mode `close16`)
1. Onboarded a customer matching the UAE Local Terrorist List (alert left open) and closed the relationship with reason "Customer request": "Relationship closed. Records retained until 2036-11-16." The case file says closed with a 10-year retention date; the sanctions alert stays open in the queue.
2. Onboarded a customer matching the UN list, confirmed the match (a freeze obligation was created), executed the freeze, left the CNMR unfiled, and closed the relationship: accepted with the same banner. The freeze obligation remains in the freeze list.
3. Reactivated that customer with a reason ("Closed by mistake while a freeze is in force."): "Customer reactivated."
4. Exit reasons offered include customer request, risk appetite, STR filed, no CDD, deceased or dissolved, other. Retention is stored as the exit date and reason; the displayed date is exit + 10 years.

## Findings
- **CL1 (medium, CONFIRMED):** A relationship can be closed while a sanctions alert is undecided or while a freeze has been executed but the CNMR not filed. There is no warning and no block. Exiting a customer in that state risks tipping off and leaves the firm without the reporting trail the freeze requires; a reasonable control would require the alert to be dispositioned and the freeze reported or resolved first.
- **CL2 (low, CONFIRMED):** Closing a customer does not touch their open alerts, so closed customers can still have alerts sitting in the open queue.
- **CL3 (low, CONFIRMED):** Closure and reactivation are audited and retention is displayed clearly with the firm-policy explanation; reactivation requires a reason. **REFUTED** as a defect.
- Earlier open items unchanged (no application change since the last report): TX1, TX2, TX3, SO1, RL1, RL2, RL3, RP1, RP2, MA1, MA2, RT1, RT2, CR1, CR2, CR3, UBO1b, SU1, F4, TA2, TA3, high-risk-country field, E2-E5, LN1, SE2, PR5 and the other lows.

## BLOCKED / not checked
- Retention purge behaviour after 10 years (cannot age the data here); retention triggers from report finalisation (#444) not re-walked.
- Rate limiting (my driver disables the limiter), HSTS, payment sign-up, goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-16/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-16-mlro-user`; commit SHA in the final reply.

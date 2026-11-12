# mlro-user daily report — 2026-11-12

**Headline: AMBER** — master is unchanged (9219e26); the web report builder shows the same gap I found on mobile yesterday: a goAML report with an impossible birth date, an unknown country, an invalid IBAN or a malformed email can be finalised and locked.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. No source read today beyond what I had already read.
- Report to branch `routine/2026-11-12-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master: `git ls-remote origin refs/heads/master` = `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, unchanged since my 2026-11-08 report; highest PR ref still 462. Shortcut applied: one workflow, short report. I chose the follow-up I flagged yesterday as not checked.

## What I did (evidence: `mlro-user-evidence/log_webreport12.json`; driver `mlro_user_drive.py`, mode `webrep12`)
Through the web report builder I saved, finalised and exported 13 STR variants, one bad field each, and parsed each exported XML:
1. Accepted at save and at finalise, with well-formed XML exported: a bad reporter email, a birth date in 2999, the birth date "yesterday", a transaction date in 2030, nationality "ZZ", gender "attack helicopter", an invalid IBAN "12345", and an amount of 1e30.
2. Refused at save: a negative amount ("must be zero or a positive number") and a non-numeric amount ("is not a valid number").
3. Refused at finalise: an empty reason for suspicion, and a vertical-tab character in the narrative (the message names the field and says it is often pasted from Word or a PDF). The valid report finalised normally with the banner "Report finalized in groAML. It has not been sent to the UAE FIU; download the goAML XML and file it manually via the goAML portal."

## Findings
- **RP1 (medium, CONFIRMED on web and mobile):** Finalising a goAML report does not validate dates, country codes, gender, IBANs, email addresses or an implausibly large amount. A finalised report cannot be edited, so any such error is locked in before the manual upload to goAML, and the MLRO's only fix is a new report.
- **RP2 (low, CONFIRMED):** Exporting a draft that failed finalisation (empty reason) returns a 400 with a non-XML body.
- The clear, field-naming message for control characters and the "not sent to the FIU" banner on finalise are good practice: **REFUTED** as defects.
- Earlier open items unchanged (no application change since the last report): MA1, MA2, RT1, RT2, CR1, CR2, CR3, UBO1b, SU1, F4, TA2, TA3, high-risk-country field, E2-E5, LN1, SE2, PR5 and the other lows.

## BLOCKED / not checked
- goAML XSD validation (schema is not in the repository), so I cannot say which accepted values the FIU would reject.
- Rate limiting (my driver disables the limiter), HSTS, payment sign-up, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-12/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-12-mlro-user`; commit SHA in the final reply.

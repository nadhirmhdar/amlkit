# mlro-user daily report — 2026-11-11

**Headline: AMBER** — master is unchanged (9219e26), so earlier results stand; today's walk of mobile report filing shows a goAML report can be finalised, and thereby locked, with impossible dates, an unknown country, an invalid IBAN and a malformed email.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to read the mobile report save/finalise handlers.
- Report to branch `routine/2026-11-11-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master: `git ls-remote origin refs/heads/master` = `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, unchanged since my 2026-11-08 report; highest PR ref still 462. Shortcut applied: one new workflow, short report.

## What I did (evidence: `mlro-user-evidence/log_mobreport11.json`; driver `mlro_user_drive.py`, mode `mobrep11`)
Saved, finalised and exported STR reports through the mobile API with one bad field at a time, then parsed each exported XML:
1. Drafts: every variant saved (200), including a bad reporter email, a birth date in the year 2999, the birth date "yesterday", a transaction date in 2030, nationality "ZZ", gender "attack helicopter", an invalid IBAN "12345", a 2,000-character narrative, an amount of 1e30, an empty reason and an empty entity reference.
2. Finalising (`/submit`): accepted (200) for every variant above except two. Refused: an empty reason ("requires reason for suspicion (narrative)") and a vertical-tab control character in the narrative (not allowed in the goAML XML). Each accepted report exports well-formed XML.
3. HTML in a name ("<script>…") finalises and is escaped correctly in the XML. An officer finalising a report is refused (403, MLRO only).
4. Once finalised a report cannot be edited (seen in an earlier walk), so a wrong value on a finalised report is permanent.

## Findings
- **RP1 (medium, CONFIRMED):** Finalising a report checks only that a narrative exists and that no XML-illegal characters are present. It accepts a future or garbage date of birth, a future transaction date, an unknown country code, a nonsense gender, an invalid IBAN, an absurd amount and a malformed reporter email. Finalising is one-way and the filing is then uploaded manually to goAML, so errors surface as FIU rejections after the record is locked; the MLRO's only fix is a new report. I tested this on the mobile endpoints; the web screen finalises through the same finalise check, but I did not re-run the web variants today.
- **RP2 (low, CONFIRMED):** An export request for a draft that failed finalisation (empty reason) returns a 400 with a non-XML body, which a client that expects a file cannot tell apart from a corrupt download.
- **RP3 (info):** The mobile report model allows an empty entity reference; finalisation still succeeded because the organisation profile holds one. I did not test an organisation with none on mobile.
- Mobile role gating on report finalisation: **REFUTED** as a defect (officer refused, MLRO only).
- Earlier open items unchanged (no application change since the last report): MA1, MA2, RT1, RT2, CR1, CR2, CR3, UBO1b, SU1, F4, TA2, TA3, high-risk-country field, E2-E5, LN1, SE2, PR5 and the other lows.

## BLOCKED / not checked
- The same variants through the web builder (shared finalise check, not re-run today).
- goAML XSD validation (schema is not in the repository), so I cannot say which of the accepted values the FIU would reject.
- Rate limiting (my driver disables the limiter), HSTS, payment sign-up, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-11/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-11-mlro-user`; commit SHA in the final reply.

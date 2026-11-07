# mlro-user daily report — 2026-11-07

**Headline: AMBER** — master is unchanged (6560fb0), so earlier results stand; today's new walk shows a customer's identity details cannot be corrected after onboarding and duplicate people are accepted without a warning.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to list the customer routes.
- Report to branch `routine/2026-11-07-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master: `git ls-remote origin refs/heads/master` = `6560fb021f6ea2cadefcd6e60d67ee274d871e73`, unchanged since my 2026-11-05 report; highest PR ref still 459. Shortcut applied: one new workflow, short report.
- Two scheduled prompts arrived together (dated 11-06 and 11-07; the session was idle in between). I treated the 11-07 run as the current one and write one report. Nothing changed in master between the two dates, so the 11-06 run would have found the same.

## What I did (evidence: `mlro-user-evidence/log_correct07.json`; driver `mlro_user_drive.py`, mode `correct07`)
1. Onboarded "Fatma Khan" (a typo for "Fatima Khan"). Searched the case file for any way to correct it: no edit control. The case file offers only adverse media, close, evidence, notes, periodic review, signatures, transactions and UBO. Guessed edit/update URLs return 404 and a PATCH returns 405.
2. Re-onboarding the same person under the same reference: refused ("Reference 'C-001' already exists").
3. Onboarding the same person (same name and date of birth) under new references C-002 and C-003, including a lower-case name: accepted with "Onboarded. Risk rating: low." and no duplicate warning.
4. A reference that differs only by case ("c-001" next to "C-001") is accepted as a separate customer.
5. Closed the typo'd record, then tried to reuse its reference: still refused ("already exists").

## Findings
- **CR1 (medium, CONFIRMED):** There is no way to correct a customer's name, date of birth, nationality or other identity details after onboarding. A typo stays on the file and in every report; the only workaround is a new record under a different reference, and a closed record's reference can never be reused. The name that was screened is the typo'd one, so a wrong spelling can also mean the sanctions screening ran against the wrong name, with no way to fix and re-screen.
- **CR2 (low-medium, CONFIRMED):** The same person (identical name and date of birth) can be onboarded repeatedly with no duplicate warning, so a customer's activity and alerts can be split across records.
- **CR3 (low, CONFIRMED):** Customer references are unique case-sensitively ("c-001" and "C-001" coexist), which invites look-alike references.
- Earlier open items unchanged (no application change since the last report): BD1, BD2, UBO1b, MK1, MK2, F4, TA2, TA3, high-risk-country field, E2-E5, LN1, SE2, PR5 and the other lows.

## BLOCKED / not checked
- The mobile API (only `PATCH /customers/{id}/risk-factors` exists; no identity correction there either, by route list).
- Rate limiting (my driver disables the limiter), HSTS, payment sign-up, goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.
- Full re-run of earlier walks: not needed, no application code changed since the last full run.

## Files and commit
- `reports/daily/2026-11-07/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-07-mlro-user`; commit SHA in the final reply.

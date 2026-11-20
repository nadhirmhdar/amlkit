# mlro-user daily report — 2026-11-20

**Headline: AMBER** — master moved to bfb0253 (two screening commits, #465 and #466); the PEP de-duplication and the day/month-swap fix work, but a month typo in the date of birth still silences an exact name match while a completely different date of birth does not.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to see what #466 changed in the scorer.
- Report to branch `routine/2026-11-20-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master changed: `git ls-remote origin refs/heads/master` = `bfb0253ee88acabb4d8561f6e9cac2021fa3e12d` (previous report: cdf3801). Highest PR ref now 466. Commits: #465 "one hit and one alert per politically exposed person across lists", #466 "a DOB typo or dd/mm swap no longer silences an exact name match". Not the shortcut.

## What I did (evidence: `mlro-user-evidence/log_dob20.json`; driver `mlro_user_drive.py`, mode `dob20`)
1. Onboarded ten customers with the exact name of the listed UAE-list person and different dates of birth, and counted the alerts raised (listed DOB 1975-03-12):
   - 1975-03-12 exact: alert.
   - 1975-12-03 (day and month swapped): alert. (This is the #466 fix.)
   - 1975-03-21 (same month, other day): alert.
   - **1975-08-12 (month typo, same year and day): no alert.**
   - 1957-03-12 (year digits transposed), 1976 and 1974 (year off by one), 1985, 1990 (completely different), and no DOB on file: all alert.
2. PEP de-duplication (#465): I listed the same politically exposed person on a second list (a Wikidata-style list besides the CIA list) and onboarded a matching customer: one alert, not two. The queue row names the first list only and does not say the person is also on the second.
3. Re-ran the earlier country-name check (`ctry19`) on bfb0253: unchanged, all five cases alert.

## Findings
- **DB1 (medium, CONFIRMED):** The scorer's date-of-birth handling is not consistent. A date of birth that differs only in the month (same year and day, a common typing slip) silences an exact name match, while a different year, a different decade or a wholly different date of birth still raises an alert. The #466 rule excuses same-month and swapped day/month, but not a month typo. In practice a typo in the month, on a customer whose name exactly matches a listed terrorist, produces no alert and no trace that a near-match was suppressed.
- **DB2 (low, CONFIRMED):** There is no record that a suppressed near-match occurred; the MLRO cannot see candidates that were scored but fell under the alert threshold.
- **DB3 (info):** PEP de-duplication works (one alert). The alert does not mention the other list that also holds the person, which an MLRO might want in the EDD file.
- Day/month swap now alerting, and one alert per PEP across lists: **REFUTED** as defects (both work).
- Earlier open items unchanged: QU1, QU2, EX1, EX2, EX3, CL1, CL2, TX1, SO1, RL1, RL2, RP1, MA1, RT1, CR1, CR2, UBO1b, F4 and the other lows.

## BLOCKED / not checked
- Behaviour on real list data volumes and real PEP duplicates (seed is small).
- Whether a re-screen after the fix re-opens alerts previously suppressed by a DOB difference: not walked on a populated database.
- Rate limiting (my driver disables the limiter), HSTS, payment sign-up, goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-20/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-20-mlro-user`; commit SHA in the final reply.

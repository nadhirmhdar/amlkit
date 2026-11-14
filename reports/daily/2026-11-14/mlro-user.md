# mlro-user daily report — 2026-11-14

**Headline: AMBER** — master is unchanged (9219e26); today's walk of foreign-currency transactions shows the large-cash rule can be sidestepped by typing a low AED equivalent, because groAML does no currency conversion or plausibility check.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to read the transaction-recording rules for the AED amount.
- Report to branch `routine/2026-11-14-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master: `git ls-remote origin refs/heads/master` = `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, unchanged since my 2026-11-08 report; highest PR ref still 462. Shortcut applied: one new workflow, short report.

## What I did (evidence: `mlro-user-evidence/log_fx14.json`; driver `mlro_user_drive.py`, mode `fx14`)
Recorded cash transactions on one customer with the large-cash threshold at its default of AED 55,000:
1. AED 60,000 cash: "1 rule(s) triggered: large_cash".
2. USD 100,000 cash with the AED equivalent entered honestly (367,250): large_cash triggered.
3. The same USD 100,000 with the AED equivalent entered as 1, and again as 1,000: "No rules triggered." and the transaction is stored with that AED value.
4. USD 100,000 with no AED equivalent: refused ("amount_aed is required when currency is not AED").
5. Currency "XXX" (not a real currency) and lower-case "usd": both accepted.
6. An AED transaction whose AED figure differs from its amount (60,000 vs 10): refused ("for an AED transaction amount_aed must equal amount").
7. The audit trail records each transaction with its AED amount, but nothing about the foreign amount or the rate used.

## Findings
- **TX1 (medium, CONFIRMED):** The AED equivalent of a foreign-currency transaction is typed by the operator and is not checked against any exchange rate or range. A cash transaction of USD 100,000 recorded as AED 1 raises no alert, and structuring, velocity and high-value rules all work on that AED figure. Any operator (or a typing mistake) can therefore keep a large foreign-currency cash deal below the monitoring threshold, and the audit row stores only the AED number.
- **TX2 (low, CONFIRMED):** Currency codes are not validated: "XXX" is accepted as a currency.
- **TX3 (low, PLAUSIBLE):** Lower-case "usd" is accepted; I did not confirm it is normalised to "USD" in reports and exports.
- AED equals-amount check and the requirement for an AED figure on foreign currency: **REFUTED** as defects.
- Earlier open items unchanged (no application change since the last report): SO1, RL1, RL2, RL3, RP1, RP2, MA1, MA2, RT1, RT2, CR1, CR2, CR3, UBO1b, SU1, F4, TA2, TA3, high-risk-country field, E2-E5, LN1, SE2, PR5 and the other lows.

## BLOCKED / not checked
- The same entries through the mobile transaction endpoint (shares the recording function; not re-run today).
- Rate limiting (my driver disables the limiter), HSTS, payment sign-up, goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-14/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-14-mlro-user`; commit SHA in the final reply.

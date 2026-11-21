# mlro-user daily report — 2026-11-21

**Headline: AMBER** — master is unchanged (bfb0253); today's walk of enhanced due diligence shows a high-risk PEP can be onboarded with no source of wealth, source of funds or purpose, and "EDD required" is a label with no approval step behind it.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. No source read today.
- Report to branch `routine/2026-11-21-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master: `git ls-remote origin refs/heads/master` = `bfb0253ee88acabb4d8561f6e9cac2021fa3e12d`, unchanged since my 2026-11-20 report; highest PR ref still 466. Shortcut applied: one new workflow, short report.

## What I did (evidence: `mlro-user-evidence/log_edd21.json`; driver `mlro_user_drive.py`, mode `edd21`)
1. Onboarded a politically exposed Iranian national, real-estate sector, with the source of wealth, source of funds, purpose of relationship and expected activity all left blank. The system accepted it: "Onboarded. Risk rating: high."
2. The risk panel reads "high, score 115, EDD required" with the factors (PEP +30, FATF blacklist jurisdiction +60, real estate +25) and next review one year out (2027-11-16).
3. The case file's actions are adverse media, close, notes, periodic review, signatures, transactions and UBO. There is no EDD checklist and no control to record senior-management approval, source-of-wealth evidence or the date EDD was completed. The words "senior-management approval" appear only in the PEP alert's guidance text.
4. A cash transaction of AED 300,000 from Iran was recorded straight away with no EDD step ("2 rule(s) triggered: large_cash, high_risk_country").

## Findings
- **ED1 (medium, CONFIRMED):** A customer can be onboarded with source of wealth, source of funds, purpose and expected activity empty, even when the risk score is high. These are the core CDD and EDD facts a supervisor asks for first.
- **ED2 (medium, CONFIRMED):** "EDD required" is only a label. Nothing records who approved the relationship at senior-management level, when, or what additional evidence was collected, and nothing prevents business from continuing without it. The MLRO has to track this outside the system (for example in a note).
- **ED3 (low, CONFIRMED):** The review cycle for a high-risk customer is 12 months, shorter than low risk (36 months), so the model does differentiate, but there is no reminder that EDD itself is outstanding, only the periodic review date.
- Risk factors are shown clearly with their points and the ruleset version: **REFUTED** as a defect (a good basis for the file).
- Earlier open items unchanged (no application change since the last report): DB1, DB2, DB3, EX1, EX2, EX3, QU1, QU2, CL1, CL2, TX1, SO1, RL1, RL2, RP1, MA1, RT1, CR1, CR2, UBO1b, F4 and the other lows.

## BLOCKED / not checked
- Whether notes or the signature form are an intended place to record senior-management approval (I did not find any guidance saying so).
- Rate limiting (my driver disables the limiter), HSTS, payment sign-up, goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-21/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-21-mlro-user`; commit SHA in the final reply.

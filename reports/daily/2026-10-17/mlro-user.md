# mlro-user daily report — 2026-10-17

**Headline: AMBER** — master unchanged (0129848), earlier open items stand; the newly walked workflow (periodic review) has no web way to complete a review.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside (HTTP, XML, alerts, four-eyes). LOCAL seeded instance only; no source reading beyond locating routes.
- Report to branch `routine/2026-10-17-mlro-user` (never master) and as final reply. dreamon's messages coordinate scope/format only. No changes from dreamon today.
- Shortcut applied: `git ls-remote origin refs/heads/master` = `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (same as 10-16), highest PR ref still 426, no new commits. One new workflow walked: **periodic customer review**.

## What I did (evidence: `mlro-user-evidence/log_periodic_review.json`, driver `mlro_user_drive.py`, `ONLY=review`)
1. Onboarded R-001 (low, next review 2029-10-01) and R-002 (medium, 2028-10-06). Forced R-001's `next_review` to 2026-01-15 in the local DB to simulate an overdue review.
2. `/customers`: R-001 shows an `overdue` tag. CSV `review_overdue` = True for R-001, False for R-002. Dashboard "Customers due for periodic review" = 1 (of 2 on file). All three agree.
3. Customer case file: only text is "next review 2026-01-15" — no overdue marker. POST actions offered: adverse-media, close, notes, signatures, transactions, ubo. None re-assesses or records a review.
4. `/admin/rescreen` → "Re-screening failed: 'customers'" (G9); next_review stays overdue.
5. Mobile `POST /api/v1/customers/1/risk` → 200, next_review reset to 2029-10-01; overdue tag gone. Audit row is `risk.assess` only.

## Findings
- **PR1 (medium, CONFIRMED)** — No web action to complete a periodic review. The overdue tag is a dead end on the screen: the only thing that clears it is the mobile risk endpoint, which the web UI never calls. An MLRO working on a desktop cannot discharge an overdue review.
- **PR2 (low, CONFIRMED)** — Clearing an overdue review leaves no "reviewed by / outcome / notes" record, only a generic `risk.assess` audit row with the same rating. A regulator asking "who reviewed this customer and when?" gets a recalculated score, not an attestation. Re-assessment also silently moves the date three years out for low risk.
- **PR3 (low, CONFIRMED)** — The case file shows the past due date without any overdue flag, unlike the list.
- Dashboard KPI, list tag and CSV consistency: **REFUTED** as a concern (all agree).
- Still open from earlier: G9 (re-screen KeyError), G10, F4, OP1/OP2, TA1, C1/C3, E1, H2, S1 and the lows listed in earlier reports. Unchanged — master did not move.

## BLOCKED / not checked
- goAML XSD validation (schema not in repo), adverse media (GDELT network), tesseract OCR success path, SMTP delivery.
- Overdue state was simulated by editing the local DB; real clock passage was not tested.

## Files and commit
- `reports/daily/2026-10-17/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-10-17-mlro-user`; commit SHA reported in the final reply below.

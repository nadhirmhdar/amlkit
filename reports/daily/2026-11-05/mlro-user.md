# mlro-user daily report — 2026-11-05

**Headline: AMBER** — master only gained a CI-workflow change (6560fb0), so earlier results stand; today's new walk (bulk-dismiss and reason codes) shows an alert can be dismissed as a false positive using the reason "confirmed_match".

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to locate the bulk-dismiss route.
- Report to branch `routine/2026-11-05-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master: `git ls-remote origin refs/heads/master` = `6560fb021f6ea2cadefcd6e60d67ee274d871e73` (previous report: c5da8aa). The only new commit is #459, a change to a CI workflow file and its test; no application code changed. Highest PR ref 459. Shortcut applied: I did not re-run the full set of earlier walks, only one new workflow.

## What I did (evidence: `mlro-user-evidence/log_bulk05.json`; driver `mlro_user_drive.py`, modes `bulk05` and `single05`)
Seeded three customers with alerts (PEP list, UAE Local Terrorist List, UN list) and exercised `Dismiss all` and single dispositions:
1. Bulk-dismiss of a PEP customer's alert with reason `confirmed_match`: "Dismissed 1 alert(s)." The alert becomes `false_positive` with reason `confirmed_match`, immediately, with no narrative and no second review.
2. Bogus reason code, unknown customer, and another organisation's customer: each dismisses 0 alerts and changes nothing.
3. A customer whose alert is already a confirmed true positive: bulk-dismiss dismisses 0 (the decision is kept).
4. Officer bulk-dismisses a sanctions customer: staged for independent review ("a second operator must confirm"); the same officer confirming their own proposal is refused; the MLRO confirms and it closes. Audit shows `alert.bulk_dismiss`, `alert.propose`, `alert.confirm` with proposer and reviewer.
5. Single-alert path: a PEP alert dispositioned as `false_positive` with reason `confirmed_match` and an empty narrative is accepted ("Disposition recorded."). Reason `other` needs a narrative on the bulk path.

## Findings
- **BD1 (medium, CONFIRMED):** Both the bulk and single dispositions accept a contradictory reason: closing an alert as a false positive with reason code `confirmed_match`. For non-sanctions alerts (PEP) it also needs no narrative and no second review. The record then reads "false positive / confirmed match", which an auditor cannot interpret, and a PEP match can be closed with no stated rationale.
- **BD2 (low, CONFIRMED):** Bulk-dismiss reports "Dismissed 0 alert(s)." as a success banner for an unknown customer, a bogus reason code, or another organisation's customer. The operator cannot tell nothing happened for a reason.
- Four-eyes on bulk dismissal of sanctions alerts, tenant isolation, and protection of confirmed true positives: **REFUTED** as defects.
- Earlier open items unchanged (master has no application change): UBO1b, MK1, MK2, F4, TA2, TA3, high-risk-country field, E2-E5, LN1, SE2, PR5 and the other lows.

## BLOCKED / not checked
- Full re-run of the earlier walks (not needed: no application code changed since the last full run).
- Whether the EU list source check added in #459 passes (CI only; I do not read CI).
- Rate limiting (my driver disables the limiter), HSTS, payment sign-up, goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-05/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-05-mlro-user`; commit SHA in the final reply.

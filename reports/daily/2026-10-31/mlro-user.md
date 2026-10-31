# mlro-user daily report — 2026-10-31

**Headline: AMBER** — master unchanged (401da32); today's freeze-obligation edge walk shows a confirmed sanctions freeze can be closed as "false positive" by one MLRO click with no reason text, authority reference or second approval.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to locate routes and the resolve/file-CNMR handlers.
- Report to branch `routine/2026-10-31-mlro-user` (never master) and as final reply. No dreamon messages today.
- Shortcut applied: `git ls-remote origin refs/heads/master` = `401da3298f97bc94710e4b7171ec43a2ce4162b2` (unchanged since 10-24); highest PR ref still 431.

## What I did (evidence: `mlro-user-evidence/log_freeze_edges.json`; driver `mlro_user_drive.py`, `ONLY=freezeedge`)
Seeded a confirmed UAE Local Terrorist List match (true positive) which creates freeze obligation #1 (CRITICAL), then tried repeat and out-of-order actions:
1. Execute twice: second attempt refused ("already executed at …"). Execute after resolve: refused ("already resolved").
2. File CNMR twice on one obligation: both redirect to the same report (`/reports/1`), no duplicate report created. CNMR before execution or after resolution: "Freeze not ready for CNMR filing".
3. Resolve with an empty or invalid reason: refused, message lists the three valid reasons (authority_clearance, delisted, false_positive).
4. Resolve **before** the freeze was executed with reason `false_positive`, empty authority reference, empty notes: "Obligation resolved successfully." Status becomes Resolved; Execution and Report stay "pending / not yet". `delisted` before execution is refused with a clear message pointing to `false_positive`.
5. Officer (non-MLRO): execute, file CNMR and resolve all refused with a role message. Another organisation's MLRO resolving this obligation: refused ("not found in org 2"), and GET redirects.
6. Audit trail: `freeze.identified`, `freeze.executed`, `freeze.report_drafted`, `freeze.resolved` (with reason and authority_ref) all present, so each step is traceable.

## Findings
- **FZ1 (medium, CONFIRMED):** An alert confirmed as a true sanctions match produces a CRITICAL freeze obligation, but that obligation can be resolved as `false_positive` by a single MLRO with no authority reference and no notes, without executing the freeze or filing a CNMR, and with no second-person approval. The four-eyes rule protects dismissing the *alert*; it does not protect closing the *freeze*. The alert itself still reads true positive, so the two records now contradict each other. An independent reviewer or regulator would see a closed freeze for a confirmed match with only a one-line audit row.
- **FZ2 (low, CONFIRMED):** `authority_ref` and `notes` are optional for every resolution reason, including `authority_clearance` where the authority's reference is the whole point.
- **FZ3 (low, CONFIRMED):** The "not found in org 2" error shown to another tenant discloses their own org id and confirms that the obligation id format is probed per org. Minor.
- Idempotency of execute and CNMR filing, role gates, tenant isolation and audit coverage: **REFUTED** as defects.
- Still open from earlier reports: G9, G10, F4, OP1/OP2, TA1, C1/C3, E1, H2, S1, PR1-PR3, M1, M2, PW1, PW2, SS1, AU1-AU3, PV1, LG1-LG4, SE1-SE2, AX1-AX3, LN1 and the lows. Unchanged; master did not move.

## BLOCKED / not checked
- Whether a second MLRO can be required to approve a freeze resolution (no such control found in the UI).
- Real five-business-day clock for CNMR filing (text appears; no timer or weekend handling to test).
- goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-10-31/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-10-31-mlro-user`; commit SHA in the final reply.

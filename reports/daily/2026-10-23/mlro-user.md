# mlro-user daily report — 2026-10-23

**Headline: AMBER** — master unchanged (0d56f72); earlier open items stand, and the two helper screening endpoints I walked today are unlinked from the UI, report "unconfigured" as an ordinary 200, and leave no audit row.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to locate routes and read the two endpoints' handlers.
- Report to branch `routine/2026-10-23-mlro-user` (never master) and as final reply. No dreamon messages today.
- Shortcut applied: `git ls-remote origin refs/heads/master` = `0d56f72fb85a296c9882903c9552c13a2210a994` (unchanged since 10-22); highest PR ref still 427.

## What I did (evidence: `mlro-user-evidence/log_aux_screens.json`; driver `mlro_user_drive.py`, `ONLY=aux`)
1. Looked for any link to `/customers/{id}/kg-screen` and `/customers/{id}/gdelt-bq` on the customer case file: none.
2. Anonymous: `kg-screen` → 303 `/login`; `gdelt-bq` → 401 JSON. Signed-in MLRO, own customer: both 200 with `{"status":"unconfigured", …empty results…}` (no external services configured in the sandbox).
3. Missing customer id → 404 JSON; another organisation's customer id → 404 JSON (tenant isolation holds).
4. Checked the audit trail after the calls: no audit row for either lookup.

## Findings
- **AX1 (low, CONFIRMED):** `kg-screen` and `gdelt-bq` exist but are not reachable from any screen. An MLRO cannot run them without knowing the URL, so a Compliance Officer would never use or rely on them; either wire them into the case file or remove them.
- **AX2 (low, CONFIRMED):** When the screener is not configured both return HTTP 200 with empty results and `"status":"unconfigured"`. A consumer that ignores the status would read this as "no adverse hits". The same pattern is a risk if it were ever shown in the UI.
- **AX3 (low, PLAUSIBLE):** Neither call writes an audit row, although in a configured deployment the customer's full name would be sent to an external service (knowledge graph / BigQuery). I could not confirm what is sent or whether that disclosure is logged elsewhere, because the sandbox is unconfigured and offline.
- Auth and tenant isolation on both endpoints: **REFUTED** as defects (anonymous refused; cross-org id returns 404).
- Still open from earlier reports: G9, G10, F4, OP1/OP2, TA1, C1/C3, E1, H2, S1, PR1-PR3, M1, M2, PW1, PW2, SS1, AU1-AU3, PV1, LG1-LG4, SE1-SE2 and the lows. Unchanged; master did not move.

## BLOCKED / not checked
- Actual results of knowledge-graph and GDELT BigQuery screening (needs external services/credentials).
- What data leaves the system in a configured deployment.
- goAML XSD validation, adverse media via GDELT, tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-10-23/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-10-23-mlro-user`; commit SHA in the final reply.

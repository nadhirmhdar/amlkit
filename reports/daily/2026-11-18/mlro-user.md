# mlro-user daily report — 2026-11-18

**Headline: AMBER** — master is unchanged (9219e26); today's look at how clearly an alert explains itself found good legal wording and a token-level reason, but no side-by-side of the customer's own date of birth and nationality against the listed person, and some analyst jargon an operator will not read.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. No source read today.
- Report to branch `routine/2026-11-18-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master: `git ls-remote origin refs/heads/master` = `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, unchanged since my 2026-11-08 report; highest PR ref still 462. Shortcut applied: one new workflow, short report.

## What I did (evidence: `mlro-user-evidence/log_reasons18.json`, `alert_queue.txt`, `alert_panel_*.txt`; driver `mlro_user_drive.py`, mode `reasons18`)
Onboarded five customers (an exact UAE-list match, a near-name with a different DOB and nationality, a very common name, an OFAC near-match with the same DOB and nationality, and a PEP) and read what each alert row and detail panel tells the MLRO:
1. Three alerts were raised: UAE Local Terrorist List (score 1.000), OFAC (0.867) and PEP (0.867). The near-name with a different DOB and nationality, and the very common name, raised no alert.
2. Each queue row shows the listed party's date of birth and nationality, its aliases (including the Arabic), a plain-language reason ("Exact canonical match on 3 name token(s) — every token of the query matched a token of the listed name after normalisation") and the legal consequence: for the UAE list "Freeze without delay and without prior notice; report to the supervisory authority. Do not tip off"; for OFAC "apply enhanced due diligence and consider an STR/SAR; no UAE freeze obligation arises".
3. The fuzzy OFAC match explains itself with "recall 1.0 precision 0.667", "Matched tokens: vktr → vktr (1.0) sklv → sklv (1.0)" and "query vktr sklv · listed vktr ptrvš sklv".
4. The decision form offers Not a match / Confirmed match / Escalate with the reason list and a narrative required for a confirmed match or escalation.
5. The detail panel shows only name, dataset, matched name, score, category, status and creation time.

## Findings
- **EX1 (low-medium, CONFIRMED):** Neither the queue row nor the panel shows the customer's own date of birth and nationality next to the listed person's. The operator has to open the customer to compare, which slows decisions and invites mistakes on exactly the facts that clear most false positives. The reason text speaks only about name tokens, even when the DOB and nationality agree exactly (the OFAC case) or differ.
- **EX2 (low, CONFIRMED):** "recall", "precision" and phonetic token keys such as "vktr sklv" are matching-engine terms, not operator language. A compliance officer cannot act on "precision 0.667". A sentence such as "2 of 3 name parts matched" would do.
- **EX3 (low, CONFIRMED):** The detail panel repeats less than the queue row (no reason text, no aliases, no legal consequence), so opening the panel loses information.
- Good practice, **REFUTED** as defects: the legal action text per list (UAE freeze versus other-list EDD), the exact-match explanation, and no alert for mismatched DOB and nationality.
- Earlier open items unchanged (no application change since the last report): QU1, QU2, CL1, CL2, TX1, SO1, RL1, RL2, RP1, MA1, RT1, CR1, CR2 and the other lows listed in earlier reports.

## BLOCKED / not checked
- Whether a score threshold or stricter DOB rule would hide a true match in production data (I used a four-name seed).
- Rate limiting (my driver disables the limiter), HSTS, payment sign-up, goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-18/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*`
- Branch `routine/2026-11-18-mlro-user`; commit SHA in the final reply.

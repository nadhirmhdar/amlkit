# mlro-user daily report — 2026-11-22

> **CORRECTION (added 2026-11-23):** the evidence-PDF overlay described below only appears for an operator who has not yet clicked "I Understand" on the first-use notice. After acknowledging, the PDF is clean. EV1 is therefore low-medium, not high, and the headline should read AMBER, not RED. See `reports/daily/2026-11-23/mlro-user.md`.

**Headline: RED** — master only gained a deploy-setting change (c42c77c), but looking at the evidence PDF as a page rather than as bytes shows a pop-up "Important Notice" box and a grey overlay printed over the customer's reference, name, type and sector on page 1 of every evidence pack.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. No source read today.
- Report to branch `routine/2026-11-22-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master: `git ls-remote origin refs/heads/master` = `c42c77ce59179c86b3ed5107b78e65e227326c0d` (previous report: bfb0253). Highest PR ref now 467. The only new commit is #467 "Deploy with --no-cpu-throttling" (a CI workflow and a CLAUDE.md line, no application code). Shortcut applied: one new workflow, short report.

## What I did (evidence: `mlro-user-evidence/log_arabic22.json`, `evidence_arabic.pdf`, `evidence_english.pdf`, `pg-1.png`, `en-1.png`, `str_arabic.xml`; driver `mlro_user_drive.py`, modes `arabic22`, `pdf22`)
1. Onboarded a customer with an Arabic name, filed an STR with Arabic names and narrative, and followed the name through every output:
   - Case file: Arabic name intact.
   - goAML XML export: well-formed, Arabic preserved. The file starts at `<report>` with no `<?xml ... encoding="UTF-8"?>` declaration.
   - `customers.csv`: Arabic preserved.
   - Evidence PDF: Arabic present in the text layer; fonts embedded (Manrope, DejaVu).
2. Rendered page 1 of the evidence PDF to an image (`pg-1.png` Arabic, `en-1.png` English customer). In both, a white "Important Notice" dialog ("Screening results are decision support, not legal advice. A UAE-qualified adviser should sign off the risk model and reporting workflow before use on real client files.") with an empty input bar sits on top of a grey overlay, covering the Reference, Name, Type and Sector rows. The text layer confirms the collision: the notice text and the customer name interleave ("sign offFatima the riskKhan model").
3. Re-ran the same English-customer PDF on the first master I tested in October (0129848): identical overlay. This is long-standing, not a recent regression; my earlier checks of the PDF looked only at size, the `%PDF` header and the text layer, which is why I did not see it.

## Findings
- **EV1 (high, CONFIRMED):** The evidence PDF, the document an MLRO hands to a regulator or auditor, has a modal pop-up and a grey overlay rendered across page 1. The customer's reference, name, type and sector are covered, and the disclaimer text overprints them in the text layer, so the file is hard to read and hard to extract. It has been like this since at least 0129848.
- **EV2 (low, PLAUSIBLE):** The goAML XML export has no XML declaration. XML without one is valid UTF-8 by default; I cannot tell whether the FIU portal expects the declaration (no schema available here).
- **EV3 (info, CONFIRMED):** Arabic text survives case file, XML, CSV and PDF text layer.
- Earlier open items unchanged (no application change since the last report): ED1, ED2, DB1, DB2, EX1, QU1, CL1, TX1, SO1, RL1, RP1, MA1, RT1, CR1 and the other lows.

## BLOCKED / not checked
- Whether the dialog also appears in the HTML evidence page when viewed in a browser (the PDF is rendered from it; I checked the PDF only).
- Page 2 onwards of the PDF (I rendered page 1).
- goAML XSD validation, rate limiting (my driver disables the limiter), HSTS, payment sign-up, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-22/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*` (JSON, PDFs, PNGs, XML)
- Branch `routine/2026-11-22-mlro-user`; commit SHA in the final reply.

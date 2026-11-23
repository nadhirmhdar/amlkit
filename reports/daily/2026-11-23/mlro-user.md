# mlro-user daily report — 2026-11-23

**Headline: AMBER** — master is unchanged (c42c77c); I am correcting yesterday's RED: the pop-up printed over the evidence PDF only appears for an operator who has not yet clicked "I Understand" on the first-use notice, so it is a real but narrower defect than I reported.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. No source read today.
- Report to branch `routine/2026-11-23-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master: `git ls-remote origin refs/heads/master` = `c42c77ce59179c86b3ed5107b78e65e227326c0d`, unchanged since my 2026-11-22 report; highest PR ref still 467. Shortcut applied: one follow-up workflow, short report.

## Correction to my 2026-11-22 report
Yesterday I reported (EV1, high, headline RED) that every evidence PDF has an "Important Notice" dialog and a grey overlay across page 1. That was wrong in scope. My test operators never acknowledged the first-use notice, and I did not know it existed. Today's checks (below) show the dialog is the first-use disclaimer, which is part of every page until the operator clicks "I Understand". The PDF is a print of that page, so it carries the dialog only for operators who have not acknowledged it. The rest of yesterday's report (Arabic text intact in the case file, XML, CSV and PDF text layer; no XML declaration) stands.

## What I did (evidence: `mlro-user-evidence/log_evpdf23.json`, `log_evpdf23b.json`, `evidence_page.html`, PDFs; driver `mlro_user_drive.py`, modes `evpdf23`, `evpdf23b`)
1. The HTML evidence page for a customer contains `<dialog id="disclaimer-modal" ... open>` titled "Important Notice" with an "I Understand" button that posts to `/acknowledge-disclaimer`.
2. After posting the acknowledgement, the dialog no longer appears on `/`, `/dashboard`, `/customers`, `/alerts`, `/reports` or the evidence page, and the evidence PDF extracts cleanly in order (Reference, Name, "Fatima Khan"); size drops from about 28 KB to 19 KB.
3. A second operator (officer) who has not acknowledged still sees the dialog on `/customers` and gets the overlay in their evidence PDF: the acknowledgement is per operator.
4. The dialog is an open, non-blocking `<dialog>`: an operator can click the evidence-PDF link without dismissing it.

## Findings
- **EV1 (corrected: low-medium, CONFIRMED):** An operator who has not yet acknowledged the first-use notice can download an evidence PDF with the notice and a grey backdrop printed across the customer's reference, name, type and sector. A new officer or MLRO on day one, or any operator whose acknowledgement is lost, would produce an unreadable pack. The PDF should be built without page chrome.
- **EV4 (low, CONFIRMED):** The evidence PDF is created from the signed-in page including interface chrome; the clean version after acknowledging is 19 KB against 28 KB. A print layout that excludes dialogs would remove the dependency.
- **EV2 (low, PLAUSIBLE, from yesterday):** No XML declaration in the goAML export; unchanged.
- Earlier open items unchanged (no application change since the last report): ED1, ED2, DB1, DB2, EX1, QU1, CL1, TX1, SO1, RL1, RP1, MA1, RT1, CR1 and the other lows.

## BLOCKED / not checked
- A visual check of pages 2 and 3 of the PDF after acknowledging (text order checked, images not reviewed).
- goAML XSD validation, rate limiting (my driver disables the limiter), HSTS, payment sign-up, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-23/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*`
- Branch `routine/2026-11-23-mlro-user`; commit SHA in the final reply. I also added a one-line correction notice to the top of the 2026-11-22 report on its own branch.

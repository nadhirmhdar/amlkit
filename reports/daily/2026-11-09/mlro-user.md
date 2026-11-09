# mlro-user daily report — 2026-11-09

**Headline: AMBER** — master is unchanged (9219e26), so earlier results stand; today's new walk of goAML report types shows the tool can only create STR and SAR (plus the freeze report), not the sector reports a real-estate or precious-metals firm must file.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to see which report types the export layer lists.
- Report to branch `routine/2026-11-09-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master: `git ls-remote origin refs/heads/master` = `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, unchanged since my 2026-11-08 report; highest PR ref still 462. Shortcut applied: one new workflow, short report.

## What I did (evidence: `mlro-user-evidence/log_reptypes09.json`; driver `mlro_user_drive.py`, mode `rep09`)
1. Opened the report builder for a real-estate customer with each report type: STR, SAR, CNMR and FFR render a form; DPMSR, REAR, HRCA and HRCT also render a form (it looks the same as the STR form).
2. Saved a DPMSR draft with a complete form (cash gold purchase of AED 75,000): refused with "Report type 'DPMSR' is not supported. Supported types: STR, SAR." Same for REAR.
3. Read the export layer's header: it lists STR, SAR, PNMR, FFR, HRCT, HRCA, DPMSR, REAR and DTR as goAML formats, but the supported set is only STR, SAR and FFR (shown to users as CNMR). The public site and the product pages describe "sector-specific reports for DNFBPs" as a goAML topic.

## Findings
- **RT1 (high for the target market, CONFIRMED):** DPMSR (dealers in precious metals and stones) and REAR (real estate activity) cannot be created in groAML. The product is sold to real-estate brokers and precious-metals dealers, and these are the goAML reports those sectors are expected to file for cash and virtual-asset transactions above the threshold. Such a firm would still need to file them by hand on goAML. The transaction type list does include "Real Estate Buy", which suggests the use case is intended.
- **RT2 (low, CONFIRMED):** The builder page opens for DPMSR, REAR, HRCA and HRCT as if they were supported, and the refusal only appears on save, after the operator has filled in the form. The page should say the type is not available up front.
- **RT3 (info, CONFIRMED):** HRCT/HRCA (high-risk-country reports) and PNMR (partial name match) are likewise listed in the export layer's header but not creatable.
- Earlier open items unchanged (no application change since the last report): CR1, CR2, CR3, UBO1b, SU1, F4, TA2, TA3, high-risk-country field, E2-E5, LN1, SE2, PR5 and the other lows.

## BLOCKED / not checked
- Whether the FIU accepts the sector reports under the codes in the export layer (I cannot validate against the FIU schema; XSD is not available here).
- Rate limiting (my driver disables the limiter), HSTS, payment sign-up, goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-09/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-09-mlro-user`; commit SHA in the final reply.

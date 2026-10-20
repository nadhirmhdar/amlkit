# mlro-user daily report — 2026-10-20

**Headline: AMBER** — master unchanged (0129848) so earlier open items stand; today's audit-trail paging and static-page walk found one server error on a crafted page number and an inaccurate cookie statement on the privacy page.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to locate routes and to check the cookie list.
- Report to branch `routine/2026-10-20-mlro-user` (never master) and as final reply. No dreamon messages today.
- Shortcut applied: `git ls-remote origin refs/heads/master` = `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (unchanged since 10-19); highest PR ref still 426.

## What I did (evidence: `mlro-user-evidence/log_audit_paging.json`; driver `mlro_user_drive.py`, `ONLY=auditpage`)
1. Onboarded 30 customers to push the audit log past one page (98 rows). `/audit` shows 50 per page with a Next/Previous link; page 2 links back to 1; page 3 (empty) links to 2. `/audit/export` returns all rows (99 lines incl. header).
2. Odd page values: `page=0` and `page=-1` return 200 (the latter offers a "previous" link to `page=0`); `page=abc` returns raw 422; `page=99999999999999999999` raises `OverflowError: Python int too large to convert to SQLite INTEGER` (a 500 in production).
3. Access: officer on `/audit` → redirected to `/` with no explanation visible to my driver; `/audit/export` → 403 empty body; anonymous `/audit` → `/login`. `/about` and `/privacy` are public (200 anonymous and signed in).
4. Privacy page says groAML sets "three cookies" (session, csrf, flash). The code also sets `amlkit_trusted_device` (MFA "remember this device", observed in my 10-18 run) and the UAE PASS state cookie.

## Findings
- **AU1 (low, CONFIRMED):** `/audit?page=99999999999999999999` crashes with an unhandled OverflowError (HTTP 500). Needs a logged-in MLRO, so low exposure, but it is an unhandled path in the regulator-facing page.
- **AU2 (low, CONFIRMED):** `/audit?page=abc` returns a raw JSON 422 instead of a friendly page; `page<=0` is accepted (negative pages show a "previous" link to page 0 or less).
- **AU3 (low, CONFIRMED):** An officer hitting `/audit/export` gets a bare 403 with no message, while `/audit` redirects. Inconsistent denial handling.
- **PV1 (low, CONFIRMED):** The privacy page's claim that the "three cookies" listed are all that groAML sets, and that "nothing that happens is left out", is inaccurate: the trusted-device cookie (30 days) and the UAE PASS state cookie are not listed. For a compliance product's data-protection statement this should be fixed.
- Paging order, page links and export completeness: **REFUTED** as defects.
- Still open from earlier reports: G9, G10, F4, OP1/OP2, TA1, C1/C3, E1, H2, S1, PR1-PR3, M1, M2, PW1, PW2, SS1 and the lows. Unchanged; master did not move.

## BLOCKED / not checked
- Whether the audit page redirect shows the officer a "not permitted" banner (driver does not follow the redirect).
- Audit filtering/search (page has none that I found).
- goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-10-20/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-10-20-mlro-user`; commit SHA in the final reply.

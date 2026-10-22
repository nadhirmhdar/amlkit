# mlro-user daily report — 2026-10-22

**Headline: AMBER** — master moved to 0d56f72 (one SEO/head-tags change, #427) and it did not break any MLRO flow I re-ran, but earlier open items stand and signed-in pages carry the customer's name in the page title with no noindex.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to see what #427 changed (diff of app.py, base.html, login.html) and to locate routes.
- Report to branch `routine/2026-10-22-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master is **not** unchanged: `git ls-remote origin refs/heads/master` = `0d56f72fb85a296c9882903c9552c13a2210a994` (previous report: 0129848). One new commit, PR #427 "SEO: fix groAML Ahrefs findings". Highest PR ref now 427. So I focused on what #427 touches (page `<head>` on every page) rather than the shortcut.

## What I did (evidence: `mlro-user-evidence/log_seo_heads.json`; driver `mlro_user_drive.py`, `ONLY=seo`)
1. Read #427's diff: sitemap adds `/apply`; `base.html` now emits a self-referencing canonical, og:url/og:image and twitter tags on every page; `/login` and `/register-organization` are noindex,nofollow; blog `?topic=`/`?q=` views are noindex,follow.
2. Fetched the head of 8 public and 8 signed-in pages. Public pages match the PR text: `/login` and `/register-organization` noindex,nofollow; `/blog?topic=…` and `/blog?q=…` noindex,follow; `/about` has the longer title; sitemap lists `/apply`; `robots.txt` is `Allow: /`.
3. Signed-in pages (`/dashboard`, `/customers`, `/customers/1`, `/audit`, `/reports`, `/account/password`) now carry canonical and og:url set to the **path only** (no customer data, no query string), og:title is the generic "groAML by Grovisor". No robots meta and no X-Robots-Tag on them.
4. Regression: re-ran the `web` and `mobile` driver modes from the previous days on 0d56f72; both completed with exit 0 and no traceback.

## Findings
- **SE1 (low, CONFIRMED):** Signed-in pages have no noindex, and `robots.txt` is `Allow: /` with no Disallow for `/customers`, `/audit`, `/reports`, `/admin`. These pages require login so a crawler normally sees a redirect, but the customer name is in `<title>` (e.g. "Fatima Khan — groAML" on `/customers/1`, from before #427) and #427 now adds canonical/og tags there too. A defence-in-depth `noindex` on authenticated pages would remove the risk if a page were ever served cached or to a link-preview bot.
- **SE2 (low, CONFIRMED):** `/blog?topic=sanctions` canonicalises to itself while `/blog?q=aml` canonicalises to `/blog`. Inconsistent; both are noindex so little impact.
- **SE3 (info, CONFIRMED):** og:image is `grovisor-logo.png` for every page, no per-article image. Not an MLRO concern.
- #427 breaking an MLRO workflow: **REFUTED** (web and mobile modes re-run clean; signed-in pages render, titles intact).
- Still open from earlier reports: G9, G10, F4, OP1/OP2, TA1, C1/C3, E1, H2, S1, PR1-PR3, M1, M2, PW1, PW2, SS1, AU1-AU3, PV1, LG1-LG4 and the lows. Not re-verified today beyond the two driver modes above (#427 touched no business logic).

## BLOCKED / not checked
- Rendered appearance of link previews (no social-card fetcher in the sandbox).
- Search-engine indexing behaviour (cannot reach production, by rule).
- Only `web` and `mobile` modes re-run; other driver modes not re-run on 0d56f72.
- goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-10-22/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-10-22-mlro-user`; commit SHA in the final reply.

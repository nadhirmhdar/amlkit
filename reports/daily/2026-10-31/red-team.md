# Red-team report 2026-10-31 -- origin/master `401da32` (unchanged since 2026-10-24; newest PR #431)

## Headline: GREEN (no new weakness) / earlier findings still open
Master and the PR list are unchanged since my last report; the checks I had listed as not done for the recent SEO and gzip PRs pass, and the one new observation is informational.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged and no PR opened or merged since 2026-10-24, so shortcut applied (one not-checked area, short report). No conflict with my standing instructions. No scheduled run reached me between 2026-10-25 and 2026-10-30, so there are no reports for those days.
- Assumptions: fresh scratch DB; unauthenticated requests; severities are my judgement.

## What I did
Took two items from my last "not checked" list: (1) ran the new blog/SEO/gzip tests plus the security-header tests (`tests/test_blog.py`, `tests/test_security_headers.py`): 47 passed, 0 failed (`evidence/pytest_blog_on_401da32.txt`); (2) checked that gzip-compressed responses still carry the app's security headers (`evidence/gzip_security_headers_on_401da32.txt`).

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| H1 | Info | CONFIRMED | No `Referrer-Policy` or `Permissions-Policy` header is set anywhere in the app (`amlkit/api/app.py` security-header middleware sets CSP, nosniff, frame deny, no-store, and HSTS only when `AMLKIT_BEHIND_PROXY=1`). Same on compressed and uncompressed pages, so it is not caused by #428. Pages with record IDs in the path (`/customers/<id>`) rely on the browser default referrer policy. Suggest `Referrer-Policy: same-origin` (or `strict-origin`) and a restrictive `Permissions-Policy`. |

## Refuted
- Gzip bypassing security headers: CSP, `X-Frame-Options` and `X-Content-Type-Options` are present on gzip'd `/about`, `/blog`, `/sitemap.xml`. HSTS is absent locally only because the proxy flag is unset.
- The test files for PRs #427/#428 pass on the merged head.

## Earlier findings
Unchanged on `401da32`: B1/B2 (scan routes), S3, T1-T3, F6, R1-R3, N3-N6, N8, M2, U1-U3, A1, C1, G1, P1 and the older screening/KYT items. Proposals are in `scripts/proposals/`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails every push with a 402 quota error (last seen 2026-10-24; not re-tested today).
- Excluded by design: `/system/*`, production, real UAE PASS endpoints.
- Not checked: gzip behaviour behind Cloud Run/CDN; scan routes with tesseract installed; the full test suite (only two files run); GCS backend at runtime; live UAE PASS sandbox.

## Files and commit
`reports/daily/2026-10-31/` (this file + two evidence files). Branch `routine/2026-10-31-red-team`. No application code edited, no new probe script, no new proposal.

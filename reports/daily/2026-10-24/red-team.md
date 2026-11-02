# Red-team report 2026-10-24 -- origin/master `401da32` (changed since 2026-10-23: PRs #428-#431 merged)

## Headline: GREEN (for the new changes) / earlier findings still open
The four PRs merged since my last report (selective gzip, public-page link fixes, legal-name change, share image) introduce no new weakness; the gzip middleware is correctly limited to pages that carry no secret.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master changed (`0d56f72` -> `401da32`, PRs #428-#431), so I probed the changed code first. No conflict with my standing instructions.
- Assumptions: fresh scratch DB; unauthenticated requests plus forged cookie headers; severities are my judgement.

## What I did
Read the full diff `0d56f72..401da32` (11 files). The only code with security weight is `amlkit/api/compress.py` (#428), which gzips responses and therefore raises the BREACH question: is a CSRF token or other secret ever compressed next to attacker-influenced text? `repro_redteam/probe_gzip_breach.py` listed which paths are compressed, scanned the bodies for tokens, tried path-confusion to get a private page compressed, and varied the session cookie. Evidence: `reports/daily/2026-10-24/evidence/probe_gzip_breach_on_401da32.txt`.

## Findings
None new.

## Refuted
- BREACH: compressed pages (`/about`, `/blog`, `/blog/<slug>`, `/sitemap.xml`) contain no CSRF token, session value or OAuth state. `/blog?q=` does reflect the query, but with no secret in the same response the side channel has nothing to leak.
- Forms and secrets stay uncompressed: `/login`, `/apply`, `/register-organization` (CSRF field) and `/privacy` are sent without gzip.
- Path confusion: encoded dot segments, trailing slashes, `;` suffixes and `//about` either 404/redirect or return the uncompressed page; none produced a compressed private page.
- Signed-in requests (`amlkit_session=...`, alone or with other cookies) are not compressed. A differently-cased cookie name is compressed, which is harmless because the server does not treat it as a session.
- `Vary: Accept-Encoding` is set on compressed responses, so caches should not mix variants.
- #429-#431 (link and rel changes, legal name, `og-card.png` static image) are template/static changes with no input handling.

## Earlier findings
Unchanged on `401da32` (none of these files were touched): B1/B2 (scan routes), S3, T1-T3, F6, R1-R3, N3-N6, N8, M2, U1-U3, A1, C1, G1, P1 and the older screening/KYT items. Proposals are in `scripts/proposals/`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails every push with a 402 quota error.
- Excluded by design: `/system/*`, production, real UAE PASS endpoints.
- Not checked: gzip behaviour behind Cloud Run's proxy and any CDN (local only); the new `tests/test_blog.py` cases (suite not run); scan routes with tesseract installed; GCS backend at runtime; live UAE PASS sandbox.

## Files and commit
`repro_redteam/probe_gzip_breach.py`, `reports/daily/2026-10-24/` (this file + evidence). Branch `routine/2026-10-24-red-team`. No application code edited, no new proposal.

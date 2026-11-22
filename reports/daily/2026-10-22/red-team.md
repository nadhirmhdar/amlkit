# Red-team report 2026-10-22 -- origin/master `0d56f72` (changed since 2026-10-21: PR #427 merged)

## Headline: GREEN (for the new change) / earlier findings still open
The one commit merged since my last report, PR #427 (SEO metadata), is clean: no markup injection through the new canonical and social-tag URLs. The open findings from earlier days are unchanged.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master changed (`0129848` -> `0d56f72`, PR #427), so I probed the changed code first. No conflict with my standing instructions.
- Assumptions: fresh scratch DB; unauthenticated requests only; severities are my judgement.

## What I did
Read the full diff of `0129848..0d56f72` (9 files: blog SEO fields, `base.html` canonical/og/twitter tags, a `robots` block, `/apply` added to the sitemap, tests). The risk was `base.html` now printing `request.url.path` (percent-decoded by the framework) into `<link rel="canonical">` and `og:url` on every page. `repro_redteam/probe_seo_canonical.py` tried quote, angle-bracket, comment and attribute-breaking paths and a hostile query string, and listed canonical/noindex on public and private pages. Evidence: `reports/daily/2026-10-22/evidence/probe_seo_canonical_on_0d56f72.txt`.

## Findings
None new.

## Refuted
- Path injection into canonical/og:url: every hostile path returns 404 (no template rendered); the real pages only ever print their own fixed path.
- Query-string injection: canonical is `https://groaml.grovisor.ae/about` with no query echoed; `<script>` in the query is not reflected.
- Indexing hygiene: `/login`, `/register-organization`, and filtered/search `/blog` views carry `noindex`; `/dashboard` and `/customers` redirect to login. Public pages (`/about`, `/privacy`, `/apply`, `/blog`) are indexable by design.

## Earlier findings
Unchanged (PR #427 touches none of the code involved): B1/B2 (scan routes), S3, T1-T3, F6, R1-R3, N3-N6, N8, M2, U1-U3, A1, C1, G1, P1 and the older screening/KYT items. Proposals are in `scripts/proposals/`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails every push with a 402 quota error.
- Excluded by design: `/system/*`, production, real UAE PASS endpoints.
- Not checked: authenticated pages' canonical tags (they embed record IDs but need a login), the new `tests/test_blog.py` cases (I did not run the suite), GCS backend at runtime, live UAE PASS sandbox.

## Files and commit
`repro_redteam/probe_seo_canonical.py`, `reports/daily/2026-10-22/` (this file + evidence). Branch `routine/2026-10-22-red-team`. No application code edited, no new proposal.

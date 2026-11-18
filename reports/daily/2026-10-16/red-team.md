# Red-team report 2026-10-16 -- origin/master `0129848` (unchanged since 2026-10-07)

## Headline: AMBER
Master and the PR list are unchanged (newest PR #426), so earlier findings stand; the new area, the in-app `/feedback` widget, renders safely but has no size or rate limit.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged, no PR opened or merged, so shortcut applied (one not-checked area, short report). No conflict with my standing instructions.
- Assumptions: seed DB rebuilt from PR #412's `repro/make_seed.py` (two scratch orgs); severities are my judgement.

## What I did
`repro_redteam/probe_feedback.py`: authenticated `POST /feedback` with an MLRO session: oversize message/page, 300 rapid posts, stored markup rendered in `/admin/feedback` and `/dashboard` (also a markup org name in the page chrome), CSRF and unauthenticated calls. Evidence: `reports/daily/2026-10-16/evidence/probe_feedback_on_0129848.txt`.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| F6 | Low | CONFIRMED | `/feedback` accepts a 900 KB message and a 50 KB `page` value, and 300 posts in 2.9 s all returned 200 (301 rows, plus 300 audit rows). Only the server's own form-size limit stops it (a 5 MB body got 400). Any logged-in operator can bloat the DB, the Litestream replica and the audit trail. Proposal: `scripts/proposals/2026-10-16-new-findings.md`. |

## Refuted / clean
- Stored markup is escaped: `<script>` in the message, `<b>` in `page`, and `<img onerror>` as the org name appear raw in neither `/admin/feedback` nor `/dashboard`.
- Missing CSRF token -> 401; unauthenticated -> 401. Rows are written under the session's `org_id`.

## Earlier findings
Unchanged on `0129848`: R1 (non-Latin org names share one slug), R2 (registration skips password complexity), R3, N3-N6, N8, M2, U1-U3, A1, C1, G1, P1 and the older screening/KYT items.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails every push with a 402 quota error.
- Excluded by design: `/system/*`, production, real UAE PASS endpoints.
- Not checked: GCS backend at runtime, live UAE PASS sandbox, mobile-API rate limits other than registration.

## Files and commit
`repro_redteam/probe_feedback.py`, `reports/daily/2026-10-16/` (this file + evidence), `scripts/proposals/2026-10-16-new-findings.md`. Branch `routine/2026-10-16-red-team`. No application code edited.

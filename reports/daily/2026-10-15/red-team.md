# Red-team report 2026-10-15 -- origin/master `0129848` (unchanged since 2026-10-07)

## Headline: AMBER
Master and the PR list are unchanged (newest PR #426), so earlier findings stand; this run's new area, `/register-organization`, is properly invite-gated and rate limited but has one functional flaw: all non-Latin org names share one slug.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged and no PR opened or merged, so shortcut applied: one not-checked area, short report. Nothing conflicted with my standing instructions.
- Assumptions: scratch DB, throw-away local SMTP sink on 127.0.0.1:2526 (stopped afterwards); invite code set to a test value; severities are my judgement.

## What I did
`repro_redteam/probe_register_org.py` against web `POST /register-organization` and mobile `POST /api/v1/auth/register-organization`: invite gating, password policy, duplicate email/org, slug collisions, CRLF/markup/length, rate limit. Evidence: `reports/daily/2026-10-15/evidence/probe_register_org_on_0129848.txt`; I also read the mail the sink received.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| R1 | Medium (invite-gated) | CONFIRMED | Slug is `[a-z0-9]` only, falling back to `org`. Org names "شركة النور" then "شركة الأمل" (and "!!!", "???") collide on UNIQUE slug; the second is refused with "similar name already exists". Only one Arabic-named firm can ever self-register, in a UAE product. |
| R2 | Low | CONFIRMED | Registration (web and mobile) checks length >= 10 only. `alllowercase12`, `xxxxxxxxxx` create MLRO accounts; complexity is enforced only on reset/change. |
| R3 | Info | CONFIRMED | Blank operator name, 5,000-char and NUL-containing org names accepted. Invite code is whitespace-trimmed (harmless). |

Proposals for R1/R2: `scripts/proposals/2026-10-15-new-findings.md` (HELD).

## Refuted / clean
- Invite gating: wrong, empty, prefix, non-ASCII and unset codes create nothing on web and mobile; no TypeError on non-ASCII (code is `.encode()`d first, unlike N7).
- Duplicate email (case-insensitive) is refused with no orphan org row (0 orgs without an operator).
- CRLF in email rejected; CRLF in name/org stays in the mail body, no `Bcc` header (sink received none).
- 5/min per IP limit holds on both endpoints (6th+ is 429); 1 MB password -> 400.

## Earlier findings
Unchanged on `0129848` (no code changed): N3-N6, N8, M2, U1-U3, A1, C1, G1, P1 and the older screening/KYT items. Proposals in `scripts/proposals/`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails every push with a 402 quota error.
- Excluded by design: `/system/*`, production, real UAE PASS endpoints.
- Not checked: GCS backend at runtime, live UAE PASS sandbox, authenticated `/feedback` limits, HTML rendering of stored org names in admin pages.

## Files and commit
`repro_redteam/probe_register_org.py`, `reports/daily/2026-10-15/` (this file + evidence), `scripts/proposals/2026-10-15-new-findings.md`. Branch `routine/2026-10-15-red-team`. No application code edited.

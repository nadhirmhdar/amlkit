# Red-team report 2026-10-19 -- origin/master `0129848` (unchanged since 2026-10-07)

## Headline: AMBER
Master and the PR list are unchanged (newest PR #426), so earlier findings stand; the new probe of the authenticated screening endpoint found it accepts a 500,000-character name with no rate limit (Low).

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged, no PR opened or merged, so shortcut applied (one not-checked area, short report). No conflict with my standing instructions.
- Assumptions: seed DB rebuilt from PR #412's `repro/make_seed.py` holds only 1 listed entity, so latencies below understate production cost; severities are my judgement.

## What I did
`repro_redteam/probe_screen_cost.py`: authenticated `POST /api/v1/screen` with names of 3 tokens up to a single 500,000-character token, plus a 100-request burst. Evidence: `reports/daily/2026-10-19/evidence/probe_screen_cost_on_0129848.txt`.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| S3 | Low | CONFIRMED (no cap / no limiter); PLAUSIBLE (production latency) | `/screen` accepted a 500,000-character name (0.3 s, 500 KB echoed back) and a 10,000-token name, and 100 back-to-back requests all returned 200 in 1.1 s, leaving 111 `screenings` rows. The full query is stored per screening, so any operator can bloat the DB, the Litestream replica and audit data. Latency was tiny only because the seed list has 1 entity; cost grows with list size and token count, which I could not measure here. |

Proposal: `scripts/proposals/2026-10-19-new-findings.md` (HELD).

## Refuted / clean
- No crash or 500 on any oversized or repetitive name; the endpoint returned well-formed JSON each time.

## Earlier findings
Unchanged on `0129848`: T1-T3 (web and mobile), F6, R1-R3, N3-N6, N8, M2, U1-U3, A1, C1, G1, P1 and the older screening/KYT items.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails every push with a 402 quota error.
- Excluded by design: `/system/*`, production, real UAE PASS endpoints.
- Not checked: screening latency against a full sanctions list, web `/screen` form path, GCS backend at runtime, live UAE PASS sandbox, other authenticated mobile routes' limits (`scan-passport`, CSV exports).

## Files and commit
`repro_redteam/probe_screen_cost.py`, `reports/daily/2026-10-19/` (this file + evidence), `scripts/proposals/2026-10-19-new-findings.md`. Branch `routine/2026-10-19-red-team`. No application code edited.

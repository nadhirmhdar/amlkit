# Red-team report 2026-10-17 -- origin/master `0129848` (unchanged since 2026-10-07)

## Headline: AMBER
Master and the PR list are unchanged (newest PR #426); new area, the unauthenticated mobile token routes, turned up one real flaw: a single setup token can be claimed concurrently to create many MLRO accounts.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged, no PR opened or merged, so shortcut applied (one not-checked area, short report). No conflict with my standing instructions.
- Assumptions: seed DB rebuilt from PR #412's `repro/make_seed.py`; setup tokens inserted directly into the scratch DB (as an admin would issue them); severities are my judgement.

## What I did
`repro_redteam/probe_mobile_unauth.py`: 120 calls each to `/api/v1/auth/verify-email`, `/auth/resend-verification`, `GET /auth/setup`; setup-claim edge cases; 20-thread double-claim of one setup token. Evidence: `reports/daily/2026-10-17/evidence/probe_mobile_unauth_on_0129848.txt`.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| T1 | Medium | CONFIRMED (mobile) / PLAUSIBLE (web) | Mobile `POST /auth/setup` checks the token, inserts the operator, then marks the token used, as separate steps. 20 concurrent claims of one token all returned 200 and created 20 MLRO operators. A leaked or forwarded setup link therefore yields several accounts, not one, and the "one-time" guarantee fails. The web `/setup` (`complete_initial_setup`) has the same check-then-act shape; I did not race it. |
| T2 | Low | CONFIRMED | Mobile `/auth/setup`: an existing operator email returns a bare 500 (token stays unused); `not-an-email` is accepted and creates an MLRO; a weak password (`alllowercase12`) and blank name are accepted. |
| T3 | Low | CONFIRMED | `verify-email`, `resend-verification` and `GET /auth/setup` have no rate limit (120 requests each, no 429). Tokens are high-entropy, so this is defence in depth only. `resend-verification` has a 60 s per-account cooldown and a constant response. |

Proposals: `scripts/proposals/2026-10-17-new-findings.md` (HELD).

## Refuted / clean
- Mobile token routes mint MLRO sessions locked behind MFA (`_login_json` calls `mfa_lock_session`).
- Invalid verify and setup tokens give a generic 400 with no account enumeration.

## Earlier findings
Unchanged on `0129848`: F6, R1-R3, N3-N6, N8, M2, U1-U3, A1, C1, G1, P1 and the older screening/KYT items.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails every push with a 402 quota error.
- Excluded by design: `/system/*`, production, real UAE PASS endpoints.
- Not checked: web `/setup` race (shape only), GCS backend at runtime, live UAE PASS sandbox, rate limits on authenticated mobile routes.

## Files and commit
`repro_redteam/probe_mobile_unauth.py`, `reports/daily/2026-10-17/` (this file + evidence), `scripts/proposals/2026-10-17-new-findings.md`. Branch `routine/2026-10-17-red-team`. No application code edited.

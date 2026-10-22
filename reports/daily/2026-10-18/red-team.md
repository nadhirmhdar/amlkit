# Red-team report 2026-10-18 -- origin/master `0129848` (unchanged since 2026-10-07)

## Headline: AMBER
Master and the PR list are unchanged (newest PR #426); yesterday's setup-token race (T1) is now confirmed on the web path too, so one token can create many MLRO accounts on both surfaces.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged, no PR opened or merged, so shortcut applied (one not-checked area, short report). No conflict with my standing instructions.
- Assumptions: seed DB rebuilt from PR #412's `repro/make_seed.py`; setup tokens inserted directly into the scratch DB; I called `complete_initial_setup` (the function behind `POST /setup`) from 20 threads rather than going through the CSRF form; severities are my judgement.

## What I did
`repro_redteam/probe_web_setup_race.py`: 20-thread double-claim of one setup token, each thread on its own connection; existing-email and malformed-input handling. Evidence: `reports/daily/2026-10-18/evidence/probe_web_setup_race_on_0129848.txt`.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| T1 (web) | Medium | CONFIRMED | All 20 concurrent claims of one setup token succeeded and created 20 MLRO operators. The token is checked, the operator inserted, and `used_at` set as separate statements, so the "one-time" link is not one-time. With 2026-10-17 this now covers web and mobile. |
| T2 (web) | Low | CONFIRMED | A setup claim with an existing operator email raises `IntegrityError`, which `POST /setup` does not catch (it handles only `ValueError`), so the user gets a 500. `not-an-email`, a blank name and `alllowercase12` are all accepted. |

Proposal: `scripts/proposals/2026-10-18-new-findings.md` (HELD).

## Refuted / clean
- Nothing new refuted this run. I did not re-test the CSRF form wrapper; the race is in the function it calls.

## Earlier findings
Unchanged on `0129848`: T1 (mobile), T2 (mobile), T3, F6, R1-R3, N3-N6, N8, M2, U1-U3, A1, C1, G1, P1 and the older screening/KYT items.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails every push with a 402 quota error.
- Excluded by design: `/system/*`, production, real UAE PASS endpoints.
- Not checked: the HTTP form path for the web race (function level only), GCS backend at runtime, live UAE PASS sandbox, rate limits on authenticated mobile routes.

## Files and commit
`repro_redteam/probe_web_setup_race.py`, `reports/daily/2026-10-18/` (this file + evidence), `scripts/proposals/2026-10-18-new-findings.md`. Branch `routine/2026-10-18-red-team`. No application code edited.

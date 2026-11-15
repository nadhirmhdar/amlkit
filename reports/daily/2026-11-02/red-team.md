# Red-team report 2026-11-02 -- origin/master `e8ddf26` (changed since 2026-11-01: 9 PRs merged, #443-#451)

## Headline: AMBER
The new email-link self-unlock (#443) holds up, but the new look-through ownership code (#447) crashes risk reassessment for any legal customer with a very deep ownership chain.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master changed (`11a3527` -> `e8ddf26`, PRs #443-#451), so I probed the changed code first. No conflict with my standing instructions.
- Assumptions: scratch DBs seeded from PR #412's `repro/make_seed.py`; unlock-mail sending replaced in-process by a recorder (nothing sent); the seed customer was switched to `legal` type for the ownership probe (`ownership_state()` returns early for natural persons); I did not run the test suite; severities are my judgement.

## What I did
Read the diff of `11a3527..e8ddf26` (34 app files) and picked the two pieces closest to my areas: #443 self-unlock (it answers my A1 lockout finding) and #447 look-through ownership (my cyclical/deep UBO area). `repro_redteam/probe_self_unlock.py` and `repro_redteam/probe_ubo_depth.py`; evidence in `reports/daily/2026-11-02/evidence/*_on_e8ddf26.txt`. I also read `GET /admin/ops` (#450): MLRO-only, shows shared dataset/replica status plus org-scoped figures.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| U4 | Medium | CONFIRMED | `_identified_ownership` in `amlkit/cases/manager.py` recurses once per chain level. With a legal customer holding a 1,100-level chain (built in under a second through `add_ubo`; no depth or row cap), `ownership_state()` raises RecursionError every time. `reassess_risk`, `reassess_transaction_risk`, `reassess_adverse_media` all fail and mobile `POST /customers/{id}/risk` returns 500; the customer page balloons to 1.9 MB. Depth 900 still works. Any operator who can add owners can break risk handling for that customer (and the same applies to a data-entry mistake). Proposal: `scripts/proposals/2026-11-02-new-findings.md` (HELD). |
| A1 (residual) | Low | CONFIRMED | After #435/#443 the lockout DoS no longer strands the owner: the first lock mails them a single-use unlock link. An attacker can still re-lock the account after each unlock (3 guesses/minute, 8 needed), costing the owner one mail and one click each time. |

## Refuted / clean (self-unlock, #443)
- One mail per lock window: 8 failures -> 1 mail; 5 more failures while locked -> no new mail. Mail only goes to a verified address.
- Redemption: first GET unlocks (303 to /login) and the password then works; reuse, expired, deactivated-operator, empty/garbage/oversized/non-ASCII tokens all give the same generic page (no token probing).
- 20 concurrent redemptions of one token: exactly one 303, the rest generic page or 429.
- Scope: clears only the password lock; an MFA lock set on the same operator stays locked. An org A operator's token does not unlock an org B MLRO.
- Info: redemption is a GET that changes state, so an email link scanner that opens the link will use it up (and unlock the account); harmless but worth knowing.

## Earlier findings still open (unchanged this run)
C1, S1, N8, O1, F2 scoring misses, KYT aggregation gaps (slow structuring, wires, mixed instruments, cross-record splits), D1, H1; see `reports/daily/2026-11-01/red-team.md`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: freeze/alert lifecycle changes (#445), retention date changes (#444), policy-blob and PDF page-size guard (#449), first-run checklist/changelog/palette (#448), Stripe event ordering (#446), UBO diagram rendering at depth, full test suite.

## Files and commit
`repro_redteam/probe_self_unlock.py`, `repro_redteam/probe_ubo_depth.py`, `scripts/proposals/2026-11-02-new-findings.md`, `reports/daily/2026-11-02/` (this file + evidence). Branch `routine/2026-11-02-red-team`. No application code edited.

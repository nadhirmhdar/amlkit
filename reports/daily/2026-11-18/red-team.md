# Red-team report 2026-11-18 -- origin/master `9219e26` (unchanged since 2026-11-08; newest PR #462)

## Headline: GREEN (for this area) / earlier items still open
Master and the PR list did not move; a missing or failing Graphviz is handled gracefully, with one low-severity gap: a hung `dot` process has no timeout.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged and no PR opened or merged since my last report, so shortcut applied (one area, short report). No conflict with my standing instructions.
- Assumptions: two-organisation seed database from PR #412 (`repro/make_seed.py`, not committed); the "hanging" and "failing" `dot` are stub scripts placed first on PATH for the test; severities are my judgement.

## What I did
Closed my "Graphviz behaviour on a machine without `dot`" item. `repro_redteam/probe_no_graphviz.py` loads a customer page and calls the diagram helper four ways: normal, `dot` absent from PATH, `dot` that sleeps 30 seconds, `dot` that prints garbage and exits 1. Evidence: `reports/daily/2026-11-18/evidence/probe_no_graphviz_on_9219e26.txt`.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| GV1 | Low | CONFIRMED | `cases/diagram.py` calls `dot.pipe()` with no timeout. With a `dot` that hangs, the customer page request waited the full 30 seconds (then returned 200); a handful of such requests would hold the same number of worker threads. I could not make the real `dot` hang, even with 200 owners and 10 levels (0.43 s), so this needs a broken installation or a future graph change to matter. |

Proposal: `scripts/proposals/2026-11-18-new-findings.md` (HELD).

## Refuted / clean
- Normal path: customer page 200 in 0.95 s with the diagram present.
- `dot` missing: the helper returns `None` immediately and the customer page returns 200 (0.01 s) without a diagram, with no error page.
- `dot` exits non-zero with garbage output: the page returns 200 immediately.

## Earlier findings still open (unchanged)
N3c, TD1 (direction spelling defeats structuring), TD2, LM1, N3b, SS1b, SS2b, SS3b/SS5, SS4, BL1, BL2, F2b, N8b, K1, K2, I1, H1, D1, A1 residual. See `reports/daily/2026-11-16/red-team.md` and `2026-11-14`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: the diagram in a real browser; the real Checkout round trip; GCS runtime; the live UAE PASS sandbox.

## Files and commit
`repro_redteam/probe_no_graphviz.py`, `scripts/proposals/2026-11-18-new-findings.md`, `reports/daily/2026-11-18/` (this file + evidence). Branch `routine/2026-11-18-red-team`. No application code edited.

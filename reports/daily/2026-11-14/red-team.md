# Red-team report 2026-11-14 -- origin/master `9219e26` (unchanged since 2026-11-08; newest PR #462)

## Headline: AMBER
Master and the PR list did not move; comparing web and mobile write routes for customers showed no validation difference between them, but it exposed that a transaction's direction is never validated, so three AED 54,999 cash deposits raise no structuring alert when the direction is spelt differently each time.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged and no PR opened or merged since my last report, so shortcut applied (one not-checked area, short report). No conflict with my standing instructions.
- Assumptions: two-organisation seed database from PR #412 (`repro/make_seed.py`, not committed); each case runs on a fresh copy; severities are my judgement.

## What I did
Closed my "web/mobile parity for customer-side routes (close, notes, documents, UBO)" item. `repro_redteam/probe_customer_route_parity.py` sends the same 24 hostile inputs (notes, UBO, transactions, relationship close) through the web form and the mobile API and compares whether a row was stored. Evidence: `reports/daily/2026-11-14/evidence/probe_customer_route_parity_on_9219e26.txt`. One result (direction `sideways` stored on both) led to `repro_redteam/probe_txn_direction.py` (evidence `probe_txn_direction_on_9219e26.txt`).

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| TD1 | Medium | CONFIRMED | `direction` is accepted as any string on web and mobile (`sideways`, empty, 500 characters all stored), and the structuring rule groups same-direction transactions by the exact string. Three cash transactions of AED 54,999 raise `structuring` with directions `in`,`in`,`in`; with `in`,`IN`,` in` (or `in`,`in.`,`in2`, or `in`,``,`x`) no rule fires at all. Anyone entering transactions, a data-entry slip or an import script can therefore defeat the AED 55,000 structuring check. |
| TD2 | Low | CONFIRMED | Free-text fields have no size cap or character filter on either surface: a 1 MB case note, a 5,000-character UBO name, and notes containing NUL and a right-to-left override were all stored. |

Proposal: `scripts/proposals/2026-11-14-new-findings.md` (HELD).

## Refuted / clean
- Parity: in all 24 cases the web and mobile outcome is the same (stored vs refused). Both refuse empty notes, UBO stakes of 150% / -5% / a total over 100% / blank name / the customer as its own owner, negative, zero, 1e30, bad-method, bad-currency and garbage-date transactions. (The relationship-close cases were refused on both surfaces because my reason code was not a valid one; I did not re-run with a valid one.)
- The earlier UBO depth/cycle guard still holds on both surfaces.

## Earlier findings still open (unchanged)
LM1 (mobile deactivation of the last MLRO), SS1b, SS2b, SS3b/SS5, SS4, BL1, BL2, N3b, F2b, N8b, K1 (other KYT aggregation gaps), K2, I1, H1, D1, A1 residual. See `reports/daily/2026-11-12/red-team.md` and `2026-11-08`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: a valid relationship-close through both surfaces; document upload parity (the web has no document upload route in the list I compared); whether the same loose-string grouping affects the velocity rule and `method`; the real Checkout round trip; GCS runtime; live UAE PASS sandbox.

## Files and commit
`repro_redteam/probe_customer_route_parity.py`, `repro_redteam/probe_txn_direction.py`, `scripts/proposals/2026-11-14-new-findings.md`, `reports/daily/2026-11-14/` (this file + evidence). Branch `routine/2026-11-14-red-team`. No application code edited.

# Red-team report 2026-11-07 -- origin/master `6560fb0` (unchanged since 2026-11-05; newest PR #459)

## Headline: AMBER (unchanged)
Master and the PR list did not move, so earlier findings stand; the new probe of the Stripe webhook state machine found the payment gate, ordering and replay protection sound, with two low-severity fail-open / robustness issues.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged and no PR opened or merged since my last report, so shortcut applied (one not-checked area, short report). Two scheduled runs reached this session at once (2026-11-06 and 2026-11-07); the container was idle on the 6th, so this single report covers both days and is filed under today's date. No conflict with my standing instructions.
- Assumptions: scratch DB; `STRIPE_SECRET_KEY` and a test webhook secret set to dummy values; events signed locally with that secret (Stripe never contacted); severities are my judgement.

## What I did
`repro_redteam/probe_billing_events.py` drives `POST /billing/webhook` with locally signed events: pending_payment -> trialing on checkout, plan change, out-of-order and superseded-subscription events, an event naming the wrong org, deletion plus the 7-day grace, unknown price/tier, malformed shapes, replay and a 2 MB body. Evidence: `reports/daily/2026-11-07/evidence/probe_billing_events_on_6560fb0.txt`. This closes my earlier "pending_payment -> trial transition" not-checked item.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| BL1 | Low | CONFIRMED | `apply_subscription` takes the plan from `subscription.metadata.tier` when the price is unknown and does not check it against the real plan list. Sending tier `enterprise-free` set the org's plan to that string, and the limits code treats an unknown plan as "retired, do not punish" i.e. unlimited. Only a signed event can do this (so someone who can edit Stripe metadata), but a mis-set value fails open. |
| BL2 | Info | CONFIRMED | A signed event with `items.data` that is not a list of objects raises an exception: the webhook returns 500 and rolls the event back, so Stripe retries it indefinitely. Needs a malformed event from Stripe itself. |

Proposal: `scripts/proposals/2026-11-07-new-findings.md` (HELD).

## Refuted / clean
- Pending org moves to `trialing` only on a signed checkout event that carries a subscription and a known tier.
- Out-of-order protection: an older subscription update is stored but not applied; an update for a superseded subscription cannot overwrite the live one.
- A subscription event for a known customer is attributed to that customer's org even when its metadata names another org; metadata is only used for a customer Stripe has not been seen with (only Stripe can send that).
- Replay returns `duplicate`; a 2 MB body, an unhandled event type, a missing data object and an unknown subscription status are all stored/acked without error; a huge `trial_end` does not crash.
- A subscription deleted more than 7 days ago refuses creation with the read-only message while reads stay open.

## Earlier findings
Unchanged (no code change): SS1 enumeration via open registration, SS2 unpaid org keeps screening/scans, SS3 verification mail to arbitrary addresses, CI1 secret on PR-triggered CI, N3b, F2b, N8b, K1, I1, H1, D1, A1 residual. See `reports/daily/2026-11-05/red-team.md`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: the real Checkout round trip and Portal; annual price display; `scripts/stripe_setup.py` and the go-live runbook; GitHub repository secret scoping; the full test suite.

## Files and commit
`repro_redteam/probe_billing_events.py`, `scripts/proposals/2026-11-07-new-findings.md`, `reports/daily/2026-11-07/` (this file + evidence). Branch `routine/2026-11-07-red-team`. No application code edited.

# Red-team report 2026-11-05 -- origin/master `6560fb0` (changed since 2026-11-04: PR #459, a CI workflow change only)

## Headline: AMBER (unchanged)
Only one commit landed (it passes an EU-feed token to CI steps); I closed two items from my last "not checked" list: the unpaid-org customer/operator gate holds, but the OCR scan routes are still free for unpaid orgs.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master changed (`c5da8aa` -> `6560fb0`, PR #459), so I probed the changed code first (a workflow file, no app code), then one not-checked area. No conflict with my standing instructions.
- Assumptions: scratch DB; `STRIPE_SECRET_KEY` set to a dummy value (Stripe never contacted); a fresh mandatory sanctions dataset row inserted so onboarding reaches the billing check; severities are my judgement.

## What I did
1. Read the #459 diff (`.github/workflows/source-canary.yml`, `tests/test_workflow_env.py`): it sets `AMLKIT_EU_FSF_TOKEN: ${{ secrets.EU_FSF_TOKEN }}` on the "Fetch and parse every source" step and the heartbeat step.
2. `repro_redteam/probe_unpaid_gate.py`: registers an unpaid org (self-serve mode), then tries to create customers, operators and use scans and feedback. Evidence: `reports/daily/2026-11-05/evidence/probe_unpaid_gate_on_6560fb0.txt`.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| CI1 | Low | PLAUSIBLE | The workflow also runs on `pull_request`, and the two steps now receive the EU token and execute code from the PR branch (`python -` block, `scripts/heartbeat.py`). Pull requests from forks do not receive secrets, but a PR from a branch inside the repository does, so anyone with write access (or a compromised automation token) can change those scripts and read the token. The token is for a public sanctions feed, which limits the damage. Worth scoping the secret to `push`/`schedule` runs only. I did not run anything in CI. |
| SS2 (extended) | Low-Medium | CONFIRMED | An unpaid (`pending_payment`) org's MLRO still gets 200 from web and mobile ad-hoc `/screen`, from the passport and trade-licence scan routes (OCR runs), and from `/feedback`. Only creating customers and operators is refused. See `scripts/proposals/2026-11-04-new-findings.md` (SS2). |

## Refuted / clean
- Customer creation while unpaid: mobile `POST /customers` (natural and legal) returns 402 with the payment message; web `POST /customers` redirects with the same error; 0 customers were stored. This closes the earlier "not checked" item.
- Operator creation while unpaid: mobile 402; web redirect with the error; the org still has only its first operator.
- No application code changed since my last report, so every earlier finding is unchanged: SS1, SS3, N3b, F2b, N8b, K1, I1, H1, D1, A1 residual.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: the Checkout success path and the `pending_payment` -> trial transition (needs Stripe events); annual price handling; the Stripe go-live runbook and `scripts/stripe_setup.py`; the repository's secret scoping in GitHub settings (cannot see it); the full test suite.

## Files and commit
`repro_redteam/probe_unpaid_gate.py`, `reports/daily/2026-11-05/` (this file + evidence). Branch `routine/2026-11-05-red-team`. No application code edited, no new proposal file (SS2 extended in place by reference).

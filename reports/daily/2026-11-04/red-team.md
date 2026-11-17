# Red-team report 2026-11-04 -- origin/master `c5da8aa` (changed since 2026-11-03: PRs #457, #458 merged)

## Headline: AMBER
The new self-serve sign-up (active only when Stripe is configured) makes registration open to the internet, and it leaks which email addresses already have an account and leaves unpaid organisations free use of ad-hoc screening.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master changed (`938050f` -> `c5da8aa`, PRs #457 landing/pricing/self-serve sign-up and #458 Stripe go-live wiring), so I probed the changed code first. No conflict with my standing instructions.
- Assumptions: this session started in a fresh container, so I rebuilt the scratch virtualenv and re-fetched my earlier work from `origin/routine/2026-11-03-red-team`; scratch DB; `STRIPE_SECRET_KEY` set to a dummy value to switch self-serve mode on (Stripe never contacted); verification mail captured in-process; severities are my judgement. The invite-gated mode (no Stripe key) is unchanged and was not re-run beyond the gating check.

## What I did
Read the diff `938050f..c5da8aa` (21 app files; the security-relevant part is in `routers/auth.py`, `cases/operators.py`, `billing/limits.py`). `repro_redteam/probe_selfserve_signup.py` registers an org with no invite code, verifies it, and tries what an unpaid (`pending_payment`) MLRO can do. Evidence: `reports/daily/2026-11-04/evidence/probe_selfserve_signup_on_c5da8aa.txt`.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| SS1 | Medium (when Stripe is on) | CONFIRMED | Account enumeration: the open form answers "already exists" for a registered address and success for a new one, so anyone can test whether a person or firm has a groAML account. Before #457 this needed the invite code. |
| SS2 | Low-Medium | CONFIRMED | An unpaid org only loses the ability to create operators (402) and customers. Ad-hoc screening still works on web and mobile: 30 consecutive `/screen` calls were accepted and stored for an org that never paid, so the paid sanctions-screening service is usable for free by anyone who can verify an email. Scan routes (heavy OCR) were not exercised but share the same gap (their only limit is 10/minute per operator). |
| SS3 | Low | CONFIRMED | A verification email goes to any address with an attacker-chosen name in the greeting ("Hi <name>"); the only throttle is 5 registrations/minute per IP (6th-8th got 429; 5 orgs created). There is no per-address cooldown, and I found no cleanup of abandoned unverified sign-ups (PLAUSIBLE: not searched exhaustively). |

Proposal: `scripts/proposals/2026-11-04-new-findings.md` (HELD).

## Refuted / clean
- Gate on creating operators: refused with 402 and a clear message while unpaid (mobile `POST /admin/operators`).
- Without a session or a verified email nothing is reachable; the new landing/pricing/AML-law pages are public by design and read no tenant data (route guards on the rest unchanged).
- Post-verification the user is sent to `/mfa/setup` (MFA enrolment is still forced for the new MLRO).

## Earlier findings
Unchanged (no code touched by #457/#458): N3b Cyrillic homoglyph miss, F2b country-mismatch penalty, N8b legacy proposals, KYT aggregation gaps, I1/H1/D1 info items, A1 residual re-lock. See `reports/daily/2026-11-03/red-team.md`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: customer creation while unpaid (my scratch DB has no fresh sanctions dataset, so onboarding stopped at a 503 before the billing check; the gate sits inside `cases.manager.onboard`); scan routes while unpaid; the Checkout success path and the `pending_payment` -> trial transition (needs Stripe events); annual price handling; the full test suite; the Stripe go-live runbook and deploy wiring in #458.

## Files and commit
`repro_redteam/probe_selfserve_signup.py`, `scripts/proposals/2026-11-04-new-findings.md`, `reports/daily/2026-11-04/` (this file + evidence). Branch `routine/2026-11-04-red-team`. No application code edited.

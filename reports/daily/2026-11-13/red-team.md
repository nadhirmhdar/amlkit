# Red-team report 2026-11-13 -- origin/master `9219e26` (unchanged since 2026-11-08; newest PR #462)

## Headline: AMBER (unchanged)
Master and the PR list did not move; I checked the web-versus-mobile pairing of the remaining admin and four-eyes routes after yesterday's last-MLRO finding and found no second gap, so only LM1 and the earlier low-severity items remain open.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged and no PR opened or merged since my last report, so shortcut applied (one not-checked area, short report). No conflict with my standing instructions.
- Assumptions: two-organisation seed database from PR #412 (`repro/make_seed.py`, not committed); single-operator mode off; severities are my judgement.

## What I did
Closed yesterday's "same web/mobile pairing for role changes, reactivation and password reset" item.
- Code comparison of the web admin routes (`routers/admin.py`) with the mobile ones (`mobile.py`): `POST /admin/operators` (create) and `.../reset-password` have the same checks on both sides (MLRO-only, org-scoped lookup, password and identity validation, plan limit, audit); there is no mobile reactivate, unlock, rename or role-change route, so those exist only on the web where the guards are in place.
- `repro_redteam/probe_four_eyes_parity.py`: the screening-alert four-eyes flow through both the mobile and the web route. Evidence: `reports/daily/2026-11-13/evidence/probe_four_eyes_parity_on_9219e26.txt`.

## Findings
None new.

## Refuted / clean
- Four-eyes on mobile: an officer proposes a dismissal (alert -> `pending_review`); the same officer's confirm is refused with 400 and the alert stays `pending_review`; the MLRO's confirm closes it as `false_positive`; a second confirm is refused ("not awaiting review"); a confirm on an alert nobody proposed is refused.
- Four-eyes on web: same results (same officer refused, MLRO's confirm closes it, a repeat is a no-op).
- Admin create and reset-password are identical on both surfaces apart from the deactivate gap already reported as LM1.

## Earlier findings still open (unchanged)
LM1 (mobile deactivation of the last MLRO, Medium), SS1b, SS2b, SS3b/SS5, SS4, BL1, BL2, N3b, F2b, N8b, K1, K2, I1, H1, D1, A1 residual. See `reports/daily/2026-11-12/red-team.md` and `2026-11-08`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: web/mobile parity for customer-side routes (close, notes, documents, UBO) beyond what the tenant sweep covers; the real Checkout round trip; GCS runtime; the live UAE PASS sandbox.

## Files and commit
`repro_redteam/probe_four_eyes_parity.py`, `reports/daily/2026-11-13/` (this file + evidence). Branch `routine/2026-11-13-red-team`. No application code edited, no new proposal.

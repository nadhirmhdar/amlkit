# Red-team report 2026-11-12 -- origin/master `9219e26` (unchanged since 2026-11-08; newest PR #462)

## Headline: AMBER
Master and the PR list did not move; reviewing the static list of SQL statements that lack an `org_id` turned up one real gap: the mobile API lets the only MLRO be deactivated, which leaves an organisation with nobody able to administer it.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged and no PR opened or merged since my last report, so shortcut applied (one not-checked area, short report). No conflict with my standing instructions.
- Assumptions: the triage tool is PR #412's `repro/sql_scan.py` (fetched into a scratch directory, not committed); two-organisation seed database from the same PR; severities are my judgement.

## What I did
Closed my "static SQL triage list not reviewed line by line" item. `sql_scan.py` lists 35 statements that touch tenant tables without `org_id`. I read the surrounding code of each one that works on rows by id: the others are token/id-bound auth updates, one-time-secret claims (guarded by `used_at IS NULL`) and start-up migrations. Evidence: `evidence/sql_scan_on_9219e26.txt`. The one that looked inconsistent became a probe, `repro_redteam/probe_last_mlro.py` (evidence `evidence/probe_last_mlro_on_9219e26.txt`).

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| LM1 | Medium | CONFIRMED | `POST /api/v1/admin/operators/{id}/deactivate` has no "last active MLRO" check, unlike the web route. As the only MLRO of an organisation I deactivated myself through the mobile API: 200 `{"ok":true}`, active MLROs went from 1 to 0, and the session was revoked. The same request through the web route was refused ("Cannot deactivate the last active MLRO"). With no MLRO nobody can unlock accounts, add operators, change thresholds, confirm dispositions or finalise reports, and the only recovery is out-of-band operator access. It can happen by mistake, by a rogue MLRO, or with a stolen sole-MLRO mobile token. |

Proposal: `scripts/proposals/2026-11-12-new-findings.md` (HELD).

## Refuted / clean
- The other 34 statements are safe: operator deactivation (both routes) and report/UBO row updates are preceded by an org-scoped lookup or act on the row just inserted by the same request; token-bound updates (`unlock`, `setup`, `uaepass_states`, password reset) are single-use claims; the `db.py` entries are migrations; `operators.py:414` (`super_admin` toggle) is the admin-secret path, not tenant-reachable.
- Cross-tenant: the full sweep from 2026-11-11 stands (no leak, no cross-tenant write).

## Earlier findings still open (unchanged)
SS1b, SS2b, SS3b/SS5, SS4, BL1, BL2, N3b, F2b, N8b, K1, K2, I1, H1, D1, A1 residual. See `reports/daily/2026-11-08/red-team.md` and `2026-11-09`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: the same web/mobile pairing for operator role changes, reactivation and password reset (the SQL list does not show them); the real Checkout round trip; GCS runtime; the live UAE PASS sandbox.

## Files and commit
`repro_redteam/probe_last_mlro.py`, `scripts/proposals/2026-11-12-new-findings.md`, `reports/daily/2026-11-12/` (this file + evidence). Branch `routine/2026-11-12-red-team`. No application code edited.

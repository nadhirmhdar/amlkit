# Red-team report 2026-11-11 -- origin/master `9219e26` (unchanged since 2026-11-08; newest PR #462)

## Headline: GREEN
Master and the PR list did not move; I re-ran the full cross-tenant sweep against the current head, which now has about 60 more routes than the last sweep, and found no leak and no cross-tenant write.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged and no PR opened or merged since my last report, so shortcut applied (one area, short report). No conflict with my standing instructions.
- Assumptions: the sweep scripts are PR #412's `repro/` tools (not committed here; fetched from that PR into a scratch directory and deleted afterwards); each request runs on a fresh copy of a two-organisation seed database whose rows carry `ALPHA-` (org A) or `BRAVO-` (org B) markers; severities are my judgement.

## What I did
Tenant isolation is the first of my standing areas and the codebase changed a great deal since the last sweep on 2026-10-04 (router split, billing, self-unlock, identity-reuse alerts, notifications, ops page, freeze lifecycle). Ran, as organisation B's users, against organisation A's data:
- `sweep.py`: 65 path-parameter routes (26 mobile, 39 web; was 62) called with org A's IDs, one fresh database per request, plus a control run with B's own IDs.
- `sweep_lists.py`: 73 parameter-less GET routes as B's MLRO and B's officer with org-A search terms (was 65).
- `check_new_routes.py`: periodic review (web and mobile) and the admin unlock route with org A's IDs.
- `sql_scan.py`: static list of SQL on org-scoped tables with no `org_id` (triage only).
Evidence: `reports/daily/2026-11-11/evidence/{sweep,sweep_lists,check_new_routes,sql_scan}_on_9219e26.txt`.

## Findings
None new.

## Refuted / clean
- `sweep.py`: `HITS: []` -- no response to B contained org-A data and no org-A row changed; the control run with B's own IDs does reach and mutate B's rows (so the requests are well-formed and the test has power).
- `sweep_lists.py`: 0 org-A markers in 73 responses to B's MLRO and 0 to B's officer, while org A's own MLRO sees its markers in 45 of 73 (control).
- `check_new_routes.py`: org A's customer/unlock IDs from org B give 404 or no effect on all three routes; the controls work.
- New code paths covered by the sweep this time and clean: `/unlock/{token}` (POST), notifications read, freeze-obligation resolve/file-FFR, transaction-alert disposition, report submit.

## Earlier findings still open (unchanged)
SS1b sign-up timing gap, SS2b unpaid `/screen`, SS3b/SS5 mail volume and visitor-chosen greeting text, SS4 duplicate org names, BL1, BL2, N3b, F2b, N8b, K1, K2, I1, H1, D1, A1 residual re-lock. See `reports/daily/2026-11-08/red-team.md` and `2026-11-09`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: the static SQL triage list was not re-reviewed line by line (71 lines, compared with the sweep result instead); webhook and billing routes have no tenant session so are outside this sweep; GCS runtime; the live UAE PASS sandbox; the real Checkout round trip.

## Files and commit
`reports/daily/2026-11-11/` (this file + evidence). Branch `routine/2026-11-11-red-team`. No application code edited, no new probe script, no new proposal.

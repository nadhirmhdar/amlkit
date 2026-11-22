# Red-team report 2026-11-17 -- origin/master `9219e26` (unchanged since 2026-11-08; newest PR #462)

## Headline: GREEN (for this area) / earlier items still open
Master and the PR list did not move; the UBO ownership diagram renders a full 200-row customer with hostile owner names in under half a second and produces no script or external link.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged and no PR opened or merged since my last report, so shortcut applied (one area, short report). No conflict with my standing instructions.
- Assumptions: two-organisation seed database from PR #412 (`repro/make_seed.py`, not committed); Graphviz `dot` is installed on this machine; severities are my judgement.

## What I did
Closed my "UBO diagram rendering at depth" item. `repro_redteam/probe_ubo_diagram_load.py` fills one customer to the new structure limits (200 owner rows, a 10-level ownership chain) including 10 owners with hostile names (DOT-injection attempts such as `A" -> "B"; "evil` and `name"];digraph{`, a backslash, `<script>`, a 2,000-character name, a right-to-left override, a newline, a NUL, `{rank=same}`, 300 Arabic letters), then renders `generate_ubo_diagram` and inspects the SVG. Evidence: `reports/daily/2026-11-17/evidence/probe_ubo_diagram_load_on_9219e26.txt`.

## Findings
None new.

## Refuted / clean
- All 10 hostile names were accepted as data and none broke the graph: the render succeeded in 0.43 s (261 KB SVG); five further renders took 0.2 s in total.
- The SVG contains no `<script>`, no `onload`/`onerror` attributes and no external `href`, so a hostile owner name cannot execute script or call out when the diagram is shown inline.
- The 200-row and 10-level limits keep the diagram cost bounded; this resolves the "unbounded UBO diagram" item from 2026-10-04.

## Earlier findings still open (unchanged)
N3c (Urdu heh and other letter variants), TD1 (direction spelling defeats structuring), TD2, LM1, N3b, SS1b, SS2b, SS3b/SS5, SS4, BL1, BL2, F2b, N8b, K1, K2, I1, H1, D1, A1 residual. See `reports/daily/2026-11-16/red-team.md` and `2026-11-14`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: diagram rendering through the web page and the browser (only the generator's output); Graphviz behaviour on a machine without `dot`; the real Checkout round trip; GCS runtime; the live UAE PASS sandbox.

## Files and commit
`repro_redteam/probe_ubo_diagram_load.py`, `reports/daily/2026-11-17/` (this file + evidence). Branch `routine/2026-11-17-red-team`. No application code edited, no new proposal.

# Red-team report 2026-10-20 -- origin/master `0129848` (unchanged since 2026-10-07)

## Headline: AMBER
Master and the PR list are unchanged (newest PR #426); the new probe of the passport-scan upload found that a 164 KB image drives the process to about 4.5 GB of memory, which on a single-instance deploy is a likely service outage.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged, no PR opened or merged, so shortcut applied (one not-checked area, short report). No conflict with my standing instructions.
- Assumptions: seed DB rebuilt from PR #412's `repro/make_seed.py`; MLRO session; memory is the whole test process's peak RSS (`ru_maxrss`, which includes the earlier steps), run in a throw-away process on this machine; production's memory limit is unknown to me, so "outage" is PLAUSIBLE.

## What I did
`repro_redteam/probe_scan_bomb.py`: `POST /api/v1/customers/scan-passport` with blank PNGs of 800x600, 9000x9000, 12000x12000 and 20000x20000 pixels, plus a 60 MB junk file with PNG magic. Evidence: `reports/daily/2026-10-20/evidence/probe_scan_bomb_on_0129848.txt`.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| B1 | Medium | CONFIRMED (resource use); PLAUSIBLE (production OOM) | A 97 KB PNG (9000x9000) raised peak RSS from 211 MB to 1.96 GB and took 27 s; a 164 KB PNG (12000x12000) reached 4.48 GB and took 53 s. Only images above Pillow's hard pixel limit (20000x20000) were refused. The upload is read fully into memory with no size cap (a 60 MB junk file was accepted and processed). Any logged-in operator of any role can send this repeatedly with no rate limit. With one SQLite-backed instance, an OOM kill drops every tenant until restart. |

Proposal: `scripts/proposals/2026-10-20-new-findings.md` (HELD).

## Refuted / clean
- Non-image or oversized-pixel input returns well-formed JSON, not a 500; the MIME magic check works as designed (it is magic-bytes only, so a valid header plus junk passes).

## Earlier findings
Unchanged on `0129848`: S3, T1-T3 (web and mobile), F6, R1-R3, N3-N6, N8, M2, U1-U3, A1, C1, G1, P1 and the older screening/KYT items.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails every push with a 402 quota error.
- Excluded by design: `/system/*`, production, real UAE PASS endpoints.
- Not checked: production memory limit; the web scan routes and Emirates ID route (same code path, not run); PDF inputs; GCS backend at runtime; live UAE PASS sandbox.

## Files and commit
`repro_redteam/probe_scan_bomb.py`, `reports/daily/2026-10-20/` (this file + evidence), `scripts/proposals/2026-10-20-new-findings.md`. Branch `routine/2026-10-20-red-team`. No application code edited.

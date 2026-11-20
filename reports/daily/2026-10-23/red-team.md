# Red-team report 2026-10-23 -- origin/master `0d56f72` (unchanged since 2026-10-22; newest PR #427)

## Headline: AMBER
Master and the PR list are unchanged, so the earlier findings stand; the web trade-licence scan route has the same unchecked-upload behaviour as the passport routes, with a smaller memory cost but the same ~23 s of CPU per request.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged and no PR opened or merged since my last report, so shortcut applied (one not-checked area, short report). No conflict with my standing instructions.
- Assumptions: seed DB rebuilt from PR #412's `repro/make_seed.py`; MLRO session; one case per process; tesseract is not installed here; severities are my judgement.

## What I did
Extended `repro_redteam/probe_scan_variants.py` with two cases and ran them against web `POST /customers/scan-trade-licence`: a 97 KB 9000x9000 PNG and a non-image `MZ...` blob named `l.exe`. Evidence: `reports/daily/2026-10-23/evidence/probe_scan_variants_licence_on_0d56f72.txt`.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| B1 (extended) | Low-Medium | CONFIRMED | The trade-licence route decodes the same 97 KB image in 22.9 s at 430 MB peak (versus 1.6 GB on web passport). Smaller memory amplification, but the same unguarded decode and CPU cost; no size cap or rate limit. |
| B2 (extended) | Low | CONFIRMED | The junk `.exe` upload returns 200: the web trade-licence route also skips the magic-byte check. |

The 2026-10-20/21 proposals already cover both; apply the size/pixel cap and MIME check in the shared extractors in `amlkit/cases/ocr.py` so all four scan routes inherit them.

## Refuted / clean
- No crash or 500 on either input.

## Earlier findings
Unchanged on `0d56f72`: B1/B2 (other scan routes), S3, T1-T3, F6, R1-R3, N3-N6, N8, M2, U1-U3, A1, C1, G1, P1 and the older screening/KYT items.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails every push with a 402 quota error.
- Excluded by design: `/system/*`, production, real UAE PASS endpoints.
- Not checked: scan behaviour with tesseract installed (production), production memory limit, other PDF shapes, canonical tags on authenticated pages, GCS backend at runtime, live UAE PASS sandbox.

## Files and commit
`repro_redteam/probe_scan_variants.py` (two cases added), `reports/daily/2026-10-23/` (this file + evidence). Branch `routine/2026-10-23-red-team`. No application code edited, no new proposal.

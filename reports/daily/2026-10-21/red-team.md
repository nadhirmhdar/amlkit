# Red-team report 2026-10-21 -- origin/master `0129848` (unchanged since 2026-10-07)

## Headline: AMBER
Master and the PR list are unchanged (newest PR #426); my follow-up on yesterday's image-bomb finding (B1) shows it affects the Emirates ID and web scan routes too, and that the web routes skip the file-type check.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged, no PR opened or merged, so shortcut applied (one not-checked area, short report). No conflict with my standing instructions.
- Assumptions: seed DB rebuilt from PR #412's `repro/make_seed.py`; MLRO session; one case per process so RSS is clean; tesseract is not installed on this machine, so some routes failed after decoding rather than returning OCR text; severities are my judgement.

## What I did
`repro_redteam/probe_scan_variants.py`, four cases: mobile Emirates ID with a 9000x9000 PNG; web passport with the same PNG; web passport with a non-image `.exe`-style file; mobile passport with a PDF whose single page is 14400x14400 pt. Evidence: `reports/daily/2026-10-21/evidence/probe_scan_variants_on_0129848.txt`.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| B1 (extended) | Medium | CONFIRMED | The same 97 KB image drives peak memory to 1.2 GB on mobile `scan-emirates-id` (24 s, then a 400 because tesseract is absent) and 1.6 GB on web `scan-passport` (26 s, 200). So the decode path is unguarded on every scan route, not just mobile passport. |
| B2 | Low | CONFIRMED | Web `POST /customers/scan-passport` accepts arbitrary bytes (a `MZ...` blob named `p.exe`, content type `application/octet-stream`) and returns 200; the mobile route rejects such files with the magic-byte check. Inconsistent validation, and it widens what reaches the image/OCR libraries. |

Proposal: `scripts/proposals/2026-10-21-new-findings.md` (HELD).

## Refuted / clean
- PDF input: a PDF with a 14400x14400 pt page returned 200 at 732 MB in 6.7 s, so the PDF rasteriser is not a comparable amplifier here (PLAUSIBLE that other PDF shapes behave worse; not tested).

## Earlier findings
Unchanged on `0129848`: B1, S3, T1-T3 (web and mobile), F6, R1-R3, N3-N6, N8, M2, U1-U3, A1, C1, G1, P1 and the older screening/KYT items.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails every push with a 402 quota error.
- Excluded by design: `/system/*`, production, real UAE PASS endpoints.
- Not checked: web trade-licence scan, other PDF shapes, behaviour with tesseract installed (production), production memory limit, GCS backend at runtime, live UAE PASS sandbox.

## Files and commit
`repro_redteam/probe_scan_variants.py`, `reports/daily/2026-10-21/` (this file + evidence), `scripts/proposals/2026-10-21-new-findings.md`. Branch `routine/2026-10-21-red-team`. No application code edited.

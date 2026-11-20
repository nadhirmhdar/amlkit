# Red-team report, 2026-10-10 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged since my 2026-10-07 report and no PR was opened or merged, so every earlier finding still stands; the one new area I probed (document upload) shows one Medium integrity problem (same-name uploads overwrite earlier evidence) and two Low crashes.

## Instructions I ran under
- Role (Nadhir's standing instructions): "Adversarial Red Team Operator (Agent 4)": probe AMLKit as a malicious actor (Arabic name matching, structuring, tenant isolation, UBO cycles, inputs that cause silent misses or crashes). Terse, evidence-first.
- Powers: read the repo, run code locally, commit and push to a branch. Never master. Local test data only; no production access, no `/system/*` calls, no secrets; additive-only (no application code edited, fixes only as proposals).
- This run: fired by the scheduled routine "groAML daily: red-team". Three daily triggers (2026-10-08, 10-09, 10-10) were queued while the session was idle; because master did not change, one report dated 2026-10-10 covers all three. Shortcut applied: master unchanged and no PR opened or merged since, so I probed one not-checked area (document upload) and kept this short. Nothing in the routine conflicted with my standing instructions.
- Assumptions: probes ran on scratch DBs seeded by PR #412's `repro/make_seed.py`; storage used the local backend (no GCS); severities are my judgement.

## What I did
1. `git ls-remote origin refs/heads/master` -> `0129848` (same as 2026-10-07). Newest PR is #426 (merged 2026-10-06); no PR opened since (GitHub PR list). New remote branches are only other roles' `routine/2026-10-10-*` report branches.
2. Probed file upload handling on `POST /api/v1/customers/{id}/documents` (`probe_upload.py`).
Evidence: `reports/daily/2026-10-10/evidence/probe_upload_on_0129848.txt`.

## Findings (new this run)
| Id | Sev | Status | Summary |
|----|-----|--------|---------|
| U1 | Medium | CONFIRMED | Uploading the same filename twice overwrites the first blob (`{org}/{customer}/{filename}`, `storage.py`). Doc 12's recorded sha256 is `2f618e3d83b2...` but its download returns the second upload's bytes (`...SECOND REPLACEMENT`, sha256 `56725b400814...`; "matches recorded: False"). Both uploads are audited, but the first file's content is gone. |
| U2 | Low | CONFIRMED | Filenames `..` and `.` and a 300-character name return HTTP 500 (`Path(...).name` gives `..`/empty, then the write targets a directory or hits ENAMETOOLONG). |
| U3 | Low | CONFIRMED | Extension is only checked for pdf/png/jpg/jpeg, so PNG- or PDF-magic files named `.html`, `.svg`, `.php`, `x<RLO>gnp.exe` are stored. Downloads are `application/octet-stream` + `attachment` + `nosniff`, which contains it. No size cap: a 40 MB upload was read fully into memory and accepted in 1.0 s. `doc_type` is unvalidated (4 KB and an HTML payload accepted; the web customer page does not display documents, so no raw reflection: `<img onerror` and `<script>alert(2)` were absent). |

## Refuted / clean
- Path traversal: `../../x.png` is stored as `x.png` (basename only). The backslash form `..\..\x.png` is stored literally as a filename on Linux (harmless there).
- Magic bytes are enforced: non-image content named `.png` and an empty file are rejected (400).
- Tenant: org B uploading to org A's customer -> 404 "Customer not found."

## Status of earlier findings
All findings from 2026-10-04 to 2026-10-07 are unchanged on `0129848` (no code change): N3 residual invisible-character screening bypasses, N4 `unscreenable` not enforced downstream, N5 CR/LF customer reference silencing the freeze alert, N6 goAML finalise accepting XML-illegal characters, N8 legacy proposals still rename-bypassable, M2 TOTP replay, plus the older screening/KYT items. Held proposals are in `scripts/proposals/`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails on every push with a 402 quota error (account-level); needs quota restored or the check made non-required.
- Not exercised by design: all `/system/*` endpoints, production.
- Not checked: `Secure` cookie flag (local HTTP), UAE PASS flow (needs network), the GCS storage backend (no credentials), the rate limiter (disabled locally), the full pytest suite.

## Files and commit
Created: `repro_redteam/probe_upload.py`; `reports/daily/2026-10-10/red-team.md` and `evidence/`; `scripts/proposals/2026-10-10-new-findings.md` (HELD). Earlier probes, reports and proposals carried over. No application code edited. Branch `routine/2026-10-10-red-team`; commit SHA in the final reply.

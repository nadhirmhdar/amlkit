# Red-team report, 2026-10-13 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged since 2026-10-07 and no PR was opened or merged, so earlier findings stand; the full test suite is green on it (2170 passed, 0 failed), and the one remaining unchecked area I could read (the GCS storage backend) shows only a defence-in-depth gap.

## Instructions I ran under
- Role (Nadhir's standing instructions): "Adversarial Red Team Operator (Agent 4)": probe AMLKit as a malicious actor (Arabic name matching, structuring, tenant isolation, UBO cycles, inputs that cause silent misses or crashes). Terse, evidence-first.
- Powers: read the repo, run code locally, commit and push to a branch. Never master. Local test data only; no production access, no `/system/*` calls, no secrets; additive-only (no application code edited, fixes only as proposals).
- This run: fired by the scheduled routine "groAML daily: red-team". Shortcut applied: `git ls-remote` shows master `0129848` (same as my reports since 2026-10-07) and no PR beyond #426 exists, so I did one not-checked item (the full pytest suite, which I had listed as not checked every day) plus a read-through of the GCS storage backend, and kept this short. Nothing in the routine conflicted with my standing instructions.
- Assumptions: tests ran in a scratch venv built from `requirements.txt` plus pytest and httpx, on a throw-away worktree of origin/master, with the local test fixtures only. GCS was not exercised (no credentials). Severities are my judgement.

## What I did
1. Ran `python -m pytest tests -q -p no:cacheprovider` on a clean worktree of `0129848`: `2170 passed, 3 skipped, 53 warnings in 1175.19s (0:19:35)`, exit 0, no failures or errors. Evidence: `reports/daily/2026-10-13/evidence/pytest_full_on_0129848.txt`. (PR #426's description reports 2172 passed / 1 skipped on its Windows machine; the 2 skipped-vs-passed difference is environmental, not a failure.)
2. Read `storage.py` (GCS download/delete/upload paths).

## Findings (new this run)
| Id | Sev | Status | Summary |
|----|-----|--------|---------|
| G1 | Info | PLAUSIBLE | `_download_gcs` and `_delete_gcs` take the bucket and object name straight from `stored_path` without pinning them to `GCS_BUCKET` or the expected `documents/`/`policies/` prefix; the local backend likewise reads and unlinks any path in `stored_path`. `stored_path` is only written by the upload functions today, so this is defence in depth (a tampered or restored row would let `purge_expired` or a download touch objects outside the store). Code reading only. Held proposal: `scripts/proposals/2026-10-13-new-findings.md`. |

## Refuted / clean
- The test suite passes in full on current master, including the regression tests for the fixes merged since 2026-10-04 (four-eyes rename, Unicode name normalisation, CSRF on org-profile/logout, goAML finalise, retention).

## Status of earlier findings
Unchanged on `0129848` (no code change): N3 residual invisible-character screening bypasses, N4 `unscreenable` not enforced downstream, N5 CR/LF customer reference silencing the freeze alert, N6 goAML finalise accepting XML-illegal characters, N8 legacy proposals rename-bypassable, M2 TOTP replay, U1-U3 upload findings, A1 account-lockout DoS, C1 UAE PASS verification not bound to the customer, plus the older screening and KYT items. Held proposals are in `scripts/proposals/`. Note: the green suite does not cover these, which is why they persist.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails on every push with a 402 quota error (account-level); needs quota restored or the check made non-required.
- Not exercised by design: all `/system/*` endpoints, production, real UAE PASS endpoints.
- Not checked: the GCS backend at runtime (no credentials), what UAE PASS actually returns in the live sandbox.

## Files and commit
Created: `reports/daily/2026-10-13/red-team.md` and `evidence/pytest_full_on_0129848.txt`; `scripts/proposals/2026-10-13-new-findings.md` (HELD). Earlier probes, reports and proposals carried over. No application code edited. Branch `routine/2026-10-13-red-team`; commit SHA in the final reply.

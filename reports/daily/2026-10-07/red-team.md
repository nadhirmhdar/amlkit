# Red-team report, 2026-10-07 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`)

## Headline: AMBER
The four-eyes rename bypass is fixed for new proposals and the `offset` crash is gone, but screening, KYT and goAML issues from earlier days still reproduce, and two small new ones turned up (legacy proposals still bypassable, TOTP codes replayable). No cross-tenant path.

## Instructions I ran under
- Role (Nadhir's standing instructions): "Adversarial Red Team Operator (Agent 4)": probe AMLKit as a malicious actor (Arabic name matching, structuring, tenant isolation, UBO cycles, inputs that cause silent misses or crashes). Terse, evidence-first.
- Powers: read the repo, run code locally, commit and push to a branch. Never master. Local test data only; no production access, no `/system/*` calls, no secrets; additive-only (no application code edited, fixes only as proposals).
- This run: fired by the scheduled routine "groAML daily: red-team". Scope: code changed since my previous report (master `b7eeb2f`), then one not-checked area (MFA). Nothing in the routine conflicted with my standing instructions.
- Assumptions: probes ran on scratch DBs seeded by PR #412's `repro/make_seed.py`; no network or mail was used this run; severities are my judgement. I did not call any `/system/*` endpoint.

## What I did
1. `git ls-remote` -> master `0129848`; previous report base `b7eeb2f`. Four PRs merged since: #426 (four-eyes check anchored to operator id), #421 (category-first alert queue order, PEP wording), #422 (10-year retention, `screenings.retention_until`, purge guard), #404 (type scale, CSS only).
2. Re-tested the four-eyes fix with a route-created proposal and a legacy proposal (`probe_csrf_session.py`).
3. Load-tested the rewritten `alert_queue` (`probe_alert_queue_scale.py`), probed the new purge logic (`probe_retention_purge.py`), re-ran the mobile paging probe (`probe_mobile_authz.py`).
4. Not-checked area from earlier reports: MFA (TOTP) (`probe_mfa.py`).
5. Re-ran PR #412 `sweep.py` and `sweep_lists.py` plus every earlier probe on `0129848`.
Evidence: `reports/daily/2026-10-07/evidence/*_on_0129848.txt`.

## Findings (new this run)
| Id | Sev | Status | Summary |
|----|-----|--------|---------|
| N8 | Medium | CONFIRMED | #426 compares operator ids only when both the proposal and the confirm call carry one. Proposals created before the deploy have `operator_id = NULL`, so the rename bypass still works for them (`probe_csrf_session` section 1: `BRAVO-officer propose` then `Renamed Officer confirm`, alert ends `false_positive`). Route-created proposals are protected (section 1b: `operator_id` 4 stored, confirm refused, alert stays `pending_review`). A name-join backfill is exact because names are unique per org (proposal in `scripts/proposals/2026-10-07-new-findings.md`). |
| M2 | Low | CONFIRMED | TOTP codes can be replayed: one valid code verified two separate locked sessions (`auth.py` `mfa_verify`, `valid_window=1`, no last-used step; `probe_mfa_on_0129848.txt` section 2). Does not defeat a live phishing relay, but allows reuse of an observed code for ~90 s. |
| I1 | Info | CONFIRMED | `alert_queue` (#421) reads every matching alert per call: 0.66 s per call and 1.3 s per dashboard at 50,000 open alerts (linear; `probe_alert_queue_scale_on_0129848.txt`). Bounded in practice since each alert needs a list hit. |
| I2 | Info | CONFIRMED | MFA lockout is per operator: 5 wrong codes lock the real MLRO for 15 minutes, even for a correct code on a new session (`probe_mfa` section 4). Needs the password. |

## Status of earlier findings on `0129848`
- FIXED: F4 for new proposals (#426); N1 `offset` overflow (`GET /api/v1/alerts?offset=99999999999999999999` now returns 200, `probe_mobile_authz_on_0129848.txt`); F5 and logout CSRF (still clean: `probe_csrf_session` section 2, `probe_logout_goaml`).
- STILL PRESENT, unchanged:
  - N3 invisible-character screening bypasses: VS16, U+034F, control chars, Braille blank, private use still MISS (`probe_unicode_bypass`).
  - N4 `unscreenable` not enforced downstream: onboard succeeds, screening row `hits=0 candidates=0 datasets_used=[]`, `rescreen_all` `screened=1 alerts=0`.
  - N5 CRLF in `customers.reference` accepted (`probe_reference_crlf_web`: stored `'WEB-REF\r\nBcc: x@example.com'`); not re-run end to end this run (needs the local mail sink), `mail.py` unchanged.
  - N6 goAML finalise accepts XML-illegal characters: reports with `\x0b`, `\x00`, U+FFFE, U+D800 reach `status=submitted` and export non-well-formed XML (`probe_goaml_ctrlchars`).
  - F2 extra-token and country/gender-mismatch misses (`probe_e2e2`), F3 `rescreen_all` skipping 24.99%/nominee/director owners (`probe_ubo`), F6-F9 KYT items (`probe_kyt`), stale rule-config cache 200/200 (`probe_cache`), F10 look-alike operator names, F11 weak-password 500 (`probe_csrf_session` section 4).
  - F13/F14 and N7 not re-run (code unchanged).

## Refuted / clean
- Cross-tenant: PR #412 sweeps on `0129848` -> `HITS: []`; lists sweep 66 routes, B->A leaks 0 (control as A: 41 routes carry the marker). The rewritten `alert_queue` keeps `org_id` in its WHERE clause; mobile `total` is tenant-scoped.
- MFA: a locked, enrolled MLRO cannot re-enrol (`GET /mfa/setup` -> 303 `/mfa/verify`, secret unchanged; `POST /mfa/setup` with a bogus code leaves the session locked and the secret unchanged). Backup codes are single-use across sessions. Trusted-device tokens are bound to their operator (not valid for another operator in the org or for org A's MLRO), reject a tampered token, and die on revoke (`probe_mfa` sections 1, 3, 5).
- Retention purge (#422): a closed customer 1 year out is not purged even with a stale `retention_until`; a customer 11 years out is; another org's expired customer and an active customer are untouched (`probe_retention_purge_on_0129848.txt`). Edge only: a closed customer with NULL `exit_date` is purged on `retention_until` alone, but `close_relationship` always sets `exit_date`.
- `/api/v1` auth matrix unchanged: no unauthenticated route, none reachable with an MFA-locked MLRO token, officer refused on the 7 MLRO-only routes (`probe_mobile_authz`).

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails on every push with a 402 quota error (account-level); needs quota restored or the check made non-required.
- Not exercised by design: all `/system/*` endpoints, production.
- Not checked: `Secure` cookie flag (local HTTP), UAE PASS flow (needs network), file-upload content handling, the rate limiter (disabled locally; `/mfa/verify` has a 5/minute per-IP limit I did not test), the full pytest suite.

## Files and commit
Created: `repro_redteam/probe_mfa.py`, `probe_retention_purge.py`, `probe_alert_queue_scale.py`; updated `probe_csrf_session.py` (new section 1b); `reports/daily/2026-10-07/red-team.md` and `evidence/`; `scripts/proposals/2026-10-07-new-findings.md` (HELD). Earlier probes, reports and proposals carried over. No application code edited. Branch `routine/2026-10-07-red-team`; commit SHA in the final reply.

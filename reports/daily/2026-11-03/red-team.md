# Red-team report 2026-11-03 -- origin/master `938050f` (changed since 2026-11-02: 5 PRs merged, #452-#456)

## Headline: GREEN (with low-severity residuals)
The big router refactor (#456) changed no route, rate limit or middleware, and the fixes for my open findings (U4, C1, S1, N8, O1, N3/F2, unlock) all check out; what remains is a Cyrillic homoglyph miss, a legacy-proposal caveat, and the policy-level KYT gaps.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master changed (`e8ddf26` -> `938050f`, PRs #452-#456), so I probed the changed code first. No conflict with my standing instructions.
- Assumptions: scratch DBs seeded from PR #412's `repro/make_seed.py`; unlock-mail sending recorded in-process; local SMTP sink on 127.0.0.1:2526 (stopped afterwards); Stripe/UAE PASS never contacted; the test suite was not run; severities are my judgement.

## What I did
1. **Refactor check (#456, `app.py` 5,046 -> 377 lines).** Dumped every route (method, path, rate limits) and the middleware stack from `e8ddf26` and from `938050f` and diffed them: 199 vs 200 routes, none missing, the only addition is the intended `POST /unlock/{token}`; 0 rate-limit differences (33 vs 34 limited routes, the extra one is the new POST); identical middleware (3 BaseHTTP + SelectiveGZip). Evidence: `evidence/route_diff_e8ddf26_vs_938050f.txt`.
2. **Full probe re-run on `938050f`** (23 probes, `evidence/*_on_938050f.txt`). 12 outputs are line-for-line identical to the 2026-11-01/02 runs after masking timestamps; the rest are the intended behaviour changes below.
3. **Probe maintenance.** `probe_csrf_session.py` enumerated `app.routes` and silently tested 0 routes after the split (new FastAPI wraps included routers); I fixed it to flatten them (`repro_redteam/_routes.py`). It now tests 55 POST and 64 GET routes: no POST changes state without a valid CSRF token. GET routes that change non-session state are the CSV/audit exports (they write audit rows) and `/changelog`. `probe_self_unlock.py` was rewritten for the new two-step unlock.

## Status of my open findings on `938050f`
| Id | Was | Now | Evidence |
|---|---|---|---|
| U4 look-through recursion (RecursionError at ~1,100 levels) | Medium | FIXED: chains refused beyond 10 levels; reassessments work | probe_ubo_depth |
| C1 one UAE PASS identity verifies unrelated customers | Medium | FIXED by flagging: every verification stores match status/detail, a re-used identity raises an `identity_reuse_alerts` row, and neither case back-fills the customer record. It does not block the verification (read in code; the probe still shows both rows recorded) | probe_uaepass, `cases/manager.py` |
| S1 SSO ignores password lock | Low | FIXED: locked officer gets no session via SSO | probe_uaepass |
| O1 look-alike operator names | Low | FIXED: ZWSP, Cyrillic homoglyph copy, case variant, reserved `system`, control characters and over-length names are not stored | probe_rename_authz |
| A1 lockout DoS | Medium | MITIGATED: first lock mails a single-use link; GET only shows a confirm page, POST needs CSRF, token survives scanners; 1 of 20 concurrent redemptions succeeds; expired/deactivated/garbage tokens give one generic page; MFA lock untouched; cross-org token useless; per-IP 10/minute shared bucket. Residual: an attacker can still re-lock after each unlock (1 mail + 1 click each time) | probe_self_unlock |
| N3 invisible/look-alike characters | Medium | NEARLY FIXED: ideographic space, Urdu yeh, Greek homoglyph now HIT | probe_unicode_bypass |
| F2 extra-token query | Medium | FIXED (extra token now scores 0.97 HIT) | probe_unicode_bypass |

## Remaining findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| N3b | Low-Medium | CONFIRMED | A Latin name with one Cyrillic consonant (В for B) still scores 0 / no candidate; only Greek and the other cases were folded. Cyrillic-only names are caught as "unscreenable", but a mixed-script spelling slips through. |
| F2b | Low | CONFIRMED (design) | An exact-name match with a mismatched country still falls under the 0.85 threshold (the -0.20 country penalty). A sanctioned person listed under another country can drop below the alert line. Policy decision, not a bug. |
| N8b | Low | PLAUSIBLE | #453 decides four-eyes by operator id. Proposals created through the routes carry an id and the self-confirm-after-rename bypass is refused (probe 1b). A legacy proposal with NULL `operator_id` is now treated as "proposed by unknown", so its own proposer can confirm it (seen on the seed data). Only matters for rows older than the operator-id column; `scripts/backfill_proposal_operator.py` exists for them. |
| K1 | Policy | CONFIRMED | KYT aggregation gaps unchanged: 54,999 four times at 7-8 day intervals, wires, mixed cash+wire/cheque, and splits across duplicate customer records raise no alert. |
| I1 | Info | CONFIRMED | GET `/changelog` and the CSV/audit export GETs write state (seen-marker, audit rows). No exploit; noted because GET-with-side-effect is prefetch-prone. |
| H1, D1 | Info | CONFIRMED | No `Referrer-Policy` / `Permissions-Policy` (not re-checked live; #442 touched headers, so worth re-running); documents keep a client-chosen display name (downloads are attachment + nosniff). |

## Refuted / clean
- Router split: no route lost or re-protected differently; rate limits and middleware identical.
- Billing (re-run), registration (invite gating, complexity, slug), upload guard, scan routes, setup-token claims, feedback, screening caps, goAML sanity, freeze-alert header safety, MFA replay/backup codes/trusted devices, KYT hardening: all unchanged from the 2026-11-01 results.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: the full test suite on `938050f`; web-side `/unlock` behaviour behind a real proxy/IP header; Referrer-Policy/Permissions-Policy live check; UBO "row cap" and "self-owner/cycle" refusals beyond depth (#455); the freeze/alert lifecycle (#445), retention (#444) and UBO diagram rendering from earlier days; GCS runtime; live UAE PASS sandbox.

## Files and commit
`repro_redteam/dump_routes.py`, `repro_redteam/_routes.py`, updated `probe_csrf_session.py` and `probe_self_unlock.py`, `reports/daily/2026-11-03/` (this file + evidence). Branch `routine/2026-11-03-red-team`. No application code edited; no new proposal (residuals are covered by `scripts/proposals/`).

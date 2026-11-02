# Red-team report 2026-11-01 -- origin/master `11a3527` (changed since 2026-10-31: 11 PRs merged, #432-#442)

## Headline: AMBER (much improved)
Eleven work-package PRs landed; re-running my probes shows most earlier findings are now fixed with no regression, the new Stripe billing code is clean, and a handful of lower-severity items plus the account-lockout DoS (A1) remain open.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master changed (`401da32` -> `11a3527`; PRs #432-#442 incl. #434 billing), so I probed the changed code first, mainly by re-running every earlier probe against the new head and then probing the new billing surface. No conflict with my standing instructions.
- Assumptions: scratch DBs seeded from PR #412's `repro/make_seed.py`; local SMTP sink on 127.0.0.1:2526 (stopped afterwards); Stripe never contacted (checkout/portal creation not exercised); the full test suite was not run; severities are my judgement.

## What I did
Diff read: 117 files (screening, upload guard, auth/lockout, password helper, KYT, goAML, billing, web hygiene). Re-ran 18 probes on `11a3527` (evidence in `reports/daily/2026-11-01/evidence/*_on_11a3527.txt`) and wrote `repro_redteam/probe_billing.py` for PR #434 (Stripe): inert-when-unconfigured, webhook signature edge cases, replay, MLRO-only and CSRF checks.

## Status of earlier findings on `11a3527`
| Id | Was | Now | Evidence |
|---|---|---|---|
| T1 setup token race (web, mobile) | Medium | FIXED: 20 concurrent claims -> 1 operator | probe_web_setup_race, probe_mobile_unauth |
| T2 setup edge cases | Low | FIXED: duplicate email 409, bad email/weak password/blank name 400 | probe_mobile_unauth |
| T3 no limiter on mobile token routes | Low | FIXED: 429 reached | probe_mobile_unauth |
| B1 image-bomb memory | Medium | FIXED: 25 MP cap (413), 10 MB cap; peak RSS 282-597 MB vs 4.5 GB before | probe_scan_bomb |
| B2 no magic-byte check on web scan routes | Low | FIXED: junk -> 415 on web passport and trade-licence | probe_scan_variants |
| S3 `/screen` no cap/limit | Low | FIXED: over-long names -> 400, burst -> 429 | probe_screen_cost |
| F6 `/feedback` no cap/limit | Low | FIXED: 900 KB -> 400, burst -> 429 | probe_feedback |
| N3 invisible-char screening bypasses | Medium | MOSTLY FIXED: VS16, U+034F, controls, U+2800, PUA, Hangul filler now HIT. Still MISS: ideographic space inside a token, Cyrillic/Greek homoglyphs, Urdu yeh-barree | probe_unicode_bypass |
| N4 `unscreenable` not enforced | Medium | FIXED in screen(): `clear=False`, manual-review summary, counted in rescreen_all (no alert row is created; MLRO sees it in the summary/banner) | probe_unicode_bypass |
| N5 CR/LF reference silences freeze alert | Medium | FIXED: CRLF reference still stored, but all 3 alerts sent | probe_freeze_alert_subject |
| N6 goAML XML-illegal chars | Medium | FIXED: finalise refused (stays draft), export well-formed | probe_goaml_ctrlchars |
| N7 `compare_digest` on non-ASCII header | Low | FIXED (`bearer_ok` compares bytes) | code read |
| M2 TOTP replay | Low | FIXED: replay refused | probe_mfa |
| U1 same-name upload overwrite | Medium | FIXED: original evidence preserved, hash matches | probe_upload |
| U2/U3 filename, size, doc_type | Low | FIXED (400/413/415) | probe_upload |
| R1 non-Latin org slug collision | Medium | FIXED | probe_register_org |
| R2 registration skips complexity | Low | FIXED (weak passwords -> 400 on API; web refuses too) | probe_register_org |
| KYT: NaN/inf, `amount_aed` override, 0.0 threshold, stale rule cache, out-of-order entry | various | FIXED | probe_kyt, probe_cache, probe_mobile_threshold |

## Still open on `11a3527`
| Id | Sev | Status | Summary |
|---|---|---|---|
| A1 | Medium | CONFIRMED | Account-lockout DoS: with no credentials, 3 wrong guesses per simulated minute for 3 minutes sets the MLRO's failed count to 8 and the real MLRO's correct password is then refused. #435 added a generic message and an MLRO unlock route (`POST /admin/operators/{id}/unlock`, org-scoped, MLRO-only, CSRF; I read it, did not run it), but a single-MLRO firm has no one to unlock it. |
| C1 | Medium | CONFIRMED (verification not bound) / PLAUSIBLE (#441 adds a mismatch flag I could not see in the probe output) | One UAE PASS identity ("Zed Unrelated") was recorded as verifying two unrelated customers. |
| S1 | Low | CONFIRMED | UAE PASS SSO still issues a session for an operator whose password login is locked (8 failures). May be intended. |
| N8 | Low | CONFIRMED | Legacy proposals without `operator_id` fall back to name comparison; a renamed officer confirmed their own proposal. New proposals are unaffected. |
| F2 | Medium | CONFIRMED | Scoring misses remain: extra-token queries, exact name with country mismatch, Cyrillic/Greek homoglyph spellings. |
| F3/K | Medium | CONFIRMED | KYT gaps remain: 54,999 x4 every 7-8 days, wires x5 same day, cash+wire mixed, cash+cheque, and splits across duplicate customer records raise no alert; a 5-per-24h sliding pattern evades velocity. (Design thresholds; the aggregation rules are a policy decision.) |
| O1 | Low | CONFIRMED | Operator rename accepts look-alikes: a Cyrillic homoglyph copy of an existing name, a trailing zero-width space, and the reserved actor name `system`. |
| D1 | Info | CONFIRMED | Document upload stores a PDF named `evil.html` under that name; downloads are `attachment`, `octet-stream`, `nosniff`, so no exploit. |
| H1 | Info | CONFIRMED | No `Referrer-Policy` / `Permissions-Policy` header (re-checked in the diff: #442 added other headers, not these two; not re-run live). |

## New surface: Stripe billing (#434) -- clean
- Inert (404) on every route while `STRIPE_SECRET_KEY` is unset.
- Webhook: missing/garbled/wrong-secret/stale/future-timestamp/tampered-body/empty-v1/missing-t signatures all 400; valid signature accepted once, replay returns `duplicate`; unset webhook secret -> 503. Verification is HMAC over the raw body, constant-time, 5-minute-style tolerance.
- `/billing*` is MLRO-only and CSRF-checked (anon -> login, officer -> redirect, no-CSRF POSTs refused); checkout/portal URLs must be https `*.stripe.com`.
- Not exercised: the real Stripe API calls, plan-limit enforcement (`billing/limits.py`) under concurrent use, and `handle_event` with real event shapes.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: full test suite on `11a3527`; the new KYT page, deadline API and UBO diagram changes (#441); cross-tenant behaviour of the MLRO unlock route (read only); per-org refresh actor (#441); sanctions scope change (UN/UAE-only freeze, #433); billing plan limits; tesseract-installed scan behaviour; GCS runtime; live UAE PASS sandbox.

## Files and commit
`repro_redteam/probe_billing.py`, `reports/daily/2026-11-01/` (this file + 20 evidence files). Branch `routine/2026-11-01-red-team`. No application code edited, no new proposal (open items are covered by earlier proposals in `scripts/proposals/`).

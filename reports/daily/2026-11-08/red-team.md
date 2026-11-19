# Red-team report 2026-11-08 -- origin/master `9219e26` (changed since 2026-11-07: PRs #460, #461, #462 merged)

## Headline: GREEN (with low-severity residuals)
The launch-blocker PR (#462) fixed my sign-up enumeration, unpaid-scan and CI-secret findings, the new reason-code rule and wider gzip hold up, and what is left is a 64 ms timing difference on the sign-up form plus the same low-severity items as before.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master changed (`6560fb0` -> `9219e26`, PRs #460 SEO round 2, #461 disposition reason codes + 4-hourly refresh, #462 WP-29 launch blockers), so I probed the changed code first. No conflict with my standing instructions.
- Assumptions: scratch DBs; `STRIPE_SECRET_KEY` set to a dummy value for the self-serve probes (Stripe never contacted); mail captured in-process; the test suite was not run; severities are my judgement.

## What I did
Read the diffs of the three PRs (29 files) and re-ran or wrote five probes (evidence in `reports/daily/2026-11-08/evidence/*_on_9219e26.txt`): `probe_selfserve_signup`, `probe_unpaid_gate`, `probe_seo_canonical`, `probe_billing_events` (re-runs); new `probe_enum_timing.py` (sign-up response equality, timing, and gzip/BREACH on the newly compressed `/`, `/aml-law`, `/pricing`, `/privacy`, `/blog`); new `probe_reason_codes.py` (all 40 status x reason combinations through the mobile disposition route).

## Status of my earlier findings
| Id | Was | Now |
|---|---|---|
| SS1 sign-up enumeration | Medium | FIXED in content: an existing address and a new one get the same page (bodies identical after masking the echoed address, same headers), nothing is created for the existing one and its owner gets a notice mail. Residual timing gap below. |
| SS2 unpaid org free scans | Low-Medium | MOSTLY FIXED: passport scan and trade-licence scan now return 402 for an unpaid org on web and mobile. Ad-hoc `/screen` still works (30 calls stored) and `/feedback` still works; I treat that as a product decision. |
| CI1 secret on PR-triggered CI | Low | FIXED: the EU token is empty on `pull_request` runs. |
| BL1, BL2 (webhook plan from metadata, malformed items) | Low / Info | UNCHANGED (not touched). |

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| SS1b | Low | CONFIRMED | Timing oracle on `POST /register-organization`: an existing address returns in about 12 ms (median of 6), a new one in about 76 ms (password hashing and inserts). The page is identical, but a 60 ms gap is measurable over a network. |
| SS3b | Low | CONFIRMED (by code) | The new existing-account notice and the verification mail have no per-address cooldown, so many IPs can flood one inbox (each IP is limited to 5 sign-ups/minute). |
| SS4 | Info | CONFIRMED | Open sign-up now accepts an organisation name identical to an existing firm (that is how the enumeration fix works), so a workspace can be named after a real firm. The name is only visible inside the new tenant today. |
| K2 | Info | CONFIRMED (documented) | Transaction-alert and adverse-media dispositions have no reason codes and no independent review (by design, per the code comments); the new coherence rule covers screening alerts only. |

Proposal: `scripts/proposals/2026-11-08-new-findings.md` (HELD).

## Refuted / clean
- Reason-code coherence (#461): all 40 combinations of disposition and reason code behave exactly as the allowed-table says (including nonsense codes and statuses); no 5xx.
- gzip on more public pages (#460/#462): `/`, `/aml-law`, `/pricing`, `/about`, `/privacy`, `/blog` contain no CSRF token or session value (the `/blog` form is a GET search form), `Vary: Accept-Encoding` is set, `/pricing?x=` does not reflect the query, HEAD works.
- Canonical/og:url (#460): hostile paths still 404; query not echoed; login and registration are `noindex`.
- Stripe webhook state machine re-run: same results as 2026-11-07.

## Earlier findings still open (unchanged)
BL1, BL2, N3b Cyrillic homoglyph miss, F2b country-mismatch penalty, N8b legacy proposals, K1 KYT aggregation gaps, I1/H1/D1, A1 residual re-lock. See `reports/daily/2026-11-03/red-team.md` and `2026-11-07`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: whether 4-hourly sanctions refresh stays inside upstream rate limits and Cloud Scheduler quotas; the static JSON-LD move (#460) beyond the page-level checks above; mail delivery of the existing-account notice (needs SMTP); the real Checkout round trip; the full test suite.

## Files and commit
`repro_redteam/probe_enum_timing.py`, `repro_redteam/probe_reason_codes.py`, `scripts/proposals/2026-11-08-new-findings.md`, `reports/daily/2026-11-08/` (this file + evidence). Branch `routine/2026-11-08-red-team`. No application code edited.

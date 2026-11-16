# Red-team report, 2026-10-12 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged since 2026-10-07 and no PR was opened or merged, so earlier findings stand; the one new area I probed (the UAE PASS flows, with UAE PASS's own endpoints stubbed) has solid state/cookie/tenant binding but lets any UAE PASS identity "verify" any customer.

## Instructions I ran under
- Role (Nadhir's standing instructions): "Adversarial Red Team Operator (Agent 4)": probe AMLKit as a malicious actor (Arabic name matching, structuring, tenant isolation, UBO cycles, inputs that cause silent misses or crashes). Terse, evidence-first.
- Powers: read the repo, run code locally, commit and push to a branch. Never master. Local test data only; no production access, no `/system/*` calls, no secrets; additive-only (no application code edited, fixes only as proposals).
- This run: fired by the scheduled routine "groAML daily: red-team". Shortcut applied: `git ls-remote` shows master `0129848` (same as my reports of 2026-10-07, 10-10 and 10-11) and no PR beyond #426 exists, so I probed one not-checked area and kept this short. Nothing in the routine conflicted with my standing instructions.
- Assumptions: probes ran on scratch DBs seeded by PR #412's `repro/make_seed.py`. UAE PASS's token and userinfo endpoints were stubbed in-process (`uaepass.exchange_code`, `uaepass.fetch_userinfo`) with dummy `UAEPASS_CLIENT_ID/SECRET`, so no request left the machine and the sandbox credentials were not used; everything else (routes, state table, cookies, DB) is real. Severities are my judgement.

## What I did
Ran `probe_uaepass.py` against both flows (operator SSO and customer CDD verification). Evidence: `reports/daily/2026-10-12/evidence/probe_uaepass_on_0129848.txt`.

## Findings (new this run)
| Id | Sev | Status | Summary |
|----|-----|--------|---------|
| C1 | Medium | CONFIRMED | Customer verification is not bound to the customer's recorded identity. One UAE PASS identity (`Zed Unrelated`, IRN, Emirates ID 784199012345678) verified two unrelated customers (names "BRAVO-SECRET Clean Customer" / nationality AE, and "Mohammed Al Testlisted" / LY); both calls succeeded, two `uaepass_verifications` rows were written, and the same Emirates ID with type `emirates_id` was backfilled onto both customers. No name, nationality or ID comparison and no duplicate-identity check (`record_uaepass_verification`, `uaepass_customer_callback`). An insider can attach CDD "verified" evidence to a fictitious or wrong customer with their own account. |
| S1 | Info | CONFIRMED | SSO ignores the password lockout: a linked officer account with `failed_login_count = 8` and `locked_until` set still signed in via UAE PASS (303 `/`). It is a break-glass for the 2026-10-11 account-lockout DoS; a linked MLRO is still sent to `/mfa/setup`, so the MFA lock holds. |
| S2 | Info | PLAUSIBLE | Email-based linking trusts the UAE PASS `email` claim at SOP2 (SOP2 identity with a matching verified operator email was linked on first use; SOP1 was refused). Whether UAE PASS verifies that claim is not established in this repo. |

## Refuted / clean
- State and cookie binding: forged state with no cookie, a victim browser presenting the attacker's callback URL (no state cookie), and a replayed state all fail with a redirect to `/login` and no session cookie.
- State scoping: a customer-verification state used at the operator callback issues no session; a state for customer 4 used on customer 5 records 0 verifications; org A redeeming org B's state on B's customer records 0 verifications; an expired state records 0 verifications.
- Linking policy: a deactivated operator and a SOP1 identity do not get a session; no account is auto-provisioned for an unlinked identity.

## Status of earlier findings
Unchanged on `0129848` (no code change): N3 residual invisible-character screening bypasses, N4 `unscreenable` not enforced downstream, N5 CR/LF customer reference silencing the freeze alert, N6 goAML finalise accepting XML-illegal characters, N8 legacy proposals rename-bypassable, M2 TOTP replay, U1-U3 upload findings, A1 account-lockout DoS, plus the older screening and KYT items. Held proposals are in `scripts/proposals/`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails on every push with a 402 quota error (account-level); needs quota restored or the check made non-required.
- Not exercised by design: all `/system/*` endpoints, production, and real UAE PASS endpoints (stubbed here).
- Not checked: what UAE PASS actually returns in the live sandbox (the userinfo parser is based on a third-party summary), the GCS storage backend (no credentials), the full pytest suite.

## Files and commit
Created: `repro_redteam/probe_uaepass.py`; `reports/daily/2026-10-12/red-team.md` and `evidence/`; `scripts/proposals/2026-10-12-new-findings.md` (HELD). Earlier probes, reports and proposals carried over. No application code edited. Branch `routine/2026-10-12-red-team`; commit SHA in the final reply.

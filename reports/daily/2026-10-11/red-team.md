# Red-team report, 2026-10-11 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged since 2026-10-07 and no PR was opened or merged, so earlier findings stand; the one new area I probed (login rate limits and cookies) held up except for a cheap account-lockout DoS against any known operator email, including the MLRO.

## Instructions I ran under
- Role (Nadhir's standing instructions): "Adversarial Red Team Operator (Agent 4)": probe AMLKit as a malicious actor (Arabic name matching, structuring, tenant isolation, UBO cycles, inputs that cause silent misses or crashes). Terse, evidence-first.
- Powers: read the repo, run code locally, commit and push to a branch. Never master. Local test data only; no production access, no `/system/*` calls, no secrets; additive-only (no application code edited, fixes only as proposals).
- This run: fired by the scheduled routine "groAML daily: red-team". Shortcut applied: `git ls-remote` shows master `0129848` (same as my 2026-10-07 and 2026-10-10 reports) and no PR beyond #426 exists, so I probed one not-checked area (the rate limiter, enabled this time, plus cookie flags) and kept this short. Nothing in the routine conflicted with my standing instructions.
- Assumptions: probes ran on scratch DBs seeded by PR #412's `repro/make_seed.py`. Time was simulated by calling `limiter.reset()` (the limiter allows 3 login attempts per minute per IP+email); lock timestamps are real. Severities are my judgement.

## What I did
Ran `probe_auth_limits.py` with the limiter enabled: IP ceiling with and without proxy trust, X-Forwarded-For spoofing, account lockout, and Set-Cookie flags. Evidence: `reports/daily/2026-10-11/evidence/probe_auth_limits_on_0129848.txt`.

## Findings (new this run)
| Id | Sev | Status | Summary |
|----|-----|--------|---------|
| A1 | Medium | CONFIRMED | Unauthenticated account-lockout DoS. Eight wrong passwords lock an account for 15 minutes (`auth.py` `MAX_FAILED_LOGINS = 8`, `LOCKOUT_MINUTES = 15`) and the limiter allows 3 attempts per minute per IP+email, so after 3 minutes of guesses the MLRO had `failed_login_count = 8`, `locked_until` set, and the correct password was refused (login form re-rendered; control with the same password on a fresh DB redirects 303). It can be repeated every 15 minutes at 3 requests a minute, with no credentials needed beyond a known email. An MLRO who cannot sign in cannot dispose a match or execute a freeze inside the 24-hour window. Held proposal: `scripts/proposals/2026-10-11-new-findings.md`. |
| A2 | Info | CONFIRMED | With `AMLKIT_BEHIND_PROXY=1`, a request that reaches the container without a proxy-appended hop (single spoofed `X-Forwarded-For`) picks its own rate-limit bucket: 14 of 14 login attempts accepted. Cloud Run's front end appends the real client address, so this is only exploitable if another ingress path to the container exists. |

## Refuted / clean
- IP ceiling holds: the 11th login attempt returns 429 with rotating `X-Forwarded-For` values, both with proxy trust off and with `AMLKIT_BEHIND_PROXY=1` and a proxy-appended real client at the right.
- Cookies with `AMLKIT_BEHIND_PROXY=1` (set in the Dockerfile and the deploy command): session cookie `HttpOnly; SameSite=strict; Secure`, CSRF cookie `HttpOnly; SameSite=lax; Secure`.

## Status of earlier findings
Unchanged on `0129848` (no code change): N3 invisible-character screening bypasses, N4 `unscreenable` not enforced downstream, N5 CR/LF customer reference silencing the freeze alert, N6 goAML finalise accepting XML-illegal characters, N8 legacy proposals rename-bypassable, M2 TOTP replay, U1-U3 upload findings, plus the older screening and KYT items. Held proposals are in `scripts/proposals/`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails on every push with a 402 quota error (account-level); needs quota restored or the check made non-required.
- Not exercised by design: all `/system/*` endpoints, production.
- Not checked: UAE PASS flow (needs network), the GCS storage backend (no credentials), `/mfa/verify` and UAE PASS route rate limits (same limiter, not separately exercised), the full pytest suite.

## Files and commit
Created: `repro_redteam/probe_auth_limits.py`; `reports/daily/2026-10-11/red-team.md` and `evidence/`; `scripts/proposals/2026-10-11-new-findings.md` (HELD). Earlier probes, reports and proposals carried over. No application code edited. Branch `routine/2026-10-11-red-team`; commit SHA in the final reply.

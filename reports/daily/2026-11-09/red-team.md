# Red-team report 2026-11-09 -- origin/master `9219e26` (unchanged since 2026-11-08; newest PR #462)

## Headline: AMBER (unchanged)
Master and the PR list did not move; the real-mail test I could not do last time confirms that open sign-up can be used to send groAML-branded email, with text of the sender's choosing, to any address and without a per-address limit.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged and no PR opened or merged since my last report, so shortcut applied (one not-checked area, short report). No conflict with my standing instructions.
- Assumptions: scratch DB; `STRIPE_SECRET_KEY` set to a dummy value to switch on open sign-up (Stripe never contacted); mail delivered to a throw-away local SMTP sink on 127.0.0.1:2526 (nothing leaves the machine), stopped afterwards; severities are my judgement.

## What I did
`repro_redteam/probe_signup_mail_flood.py` with the real SMTP code path (not the earlier in-process capture): one owner registers, then an anonymous visitor submits the sign-up form five times with the owner's address, five times with one fresh address, and with a CR/LF name and a 3,000-character name. I parsed what the sink received. Evidence: `reports/daily/2026-11-09/evidence/probe_signup_mail_flood_on_9219e26.txt`. This closes my "mail delivery of the existing-account notice" not-checked item.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| SS3b | Low | CONFIRMED | No per-address cooldown: submitting the form five times for one address produced one verification mail plus four "Someone tried to register a groAML account with your email" notices (4 notices in 4 attempts). Each IP is held to 5 sign-ups per minute, so a handful of IPs can flood one inbox. |
| SS5 | Low | CONFIRMED | The verification mail greets the address with the visitor's display name verbatim: the sink received "Hi Mallory <b>bold</b> https://evil.test/pay,". The message comes from groAML's own sending address and carries a genuine link, so anyone can use it to deliver text and a URL of their choosing to any mailbox. |

Proposal: addendum in `scripts/proposals/2026-11-08-new-findings.md` (HELD).

## Refuted / clean
- Header injection: a CR/LF display name (`Mallory\r\nBcc: spy@evil.test`) and a 3,000-character name were refused by the form; the sink received no mail for them and no Bcc header anywhere.
- The existing-account notice goes to the owner's address, uses the owner's own stored name (not the visitor's) and contains no link or token; the hostile-name attempts against an existing address produced no notice at all because the name was refused first.
- The owner who already had an account got only their own verification mail, no duplicate.

## Earlier findings still open (unchanged)
SS1b timing gap, SS2b unpaid `/screen`, SS4 duplicate org names, BL1, BL2, N3b, F2b, N8b, K1, K2, I1, H1, D1, A1 residual. See `reports/daily/2026-11-08/red-team.md`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: real-world spam-filter behaviour and sender reputation; the 4-hourly sanctions refresh against upstream limits; the real Checkout round trip; the full test suite.

## Files and commit
`repro_redteam/probe_signup_mail_flood.py`, addendum to `scripts/proposals/2026-11-08-new-findings.md`, `reports/daily/2026-11-09/` (this file + evidence). Branch `routine/2026-11-09-red-team`. No application code edited.

# Red-team report, 2026-10-14 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged since 2026-10-07 and no PR was opened or merged, so the open findings from earlier days stand; the one new area I probed (the public, unauthenticated quotation form `/apply`) held up against header injection, spam and CSRF.

## Instructions I ran under
- Role (Nadhir's standing instructions): "Adversarial Red Team Operator (Agent 4)": probe AMLKit as a malicious actor (Arabic name matching, structuring, tenant isolation, UBO cycles, inputs that cause silent misses or crashes). Terse, evidence-first.
- Powers: read the repo, run code locally, commit and push to a branch. Never master. Local test data only; no production access, no `/system/*` calls, no secrets; additive-only (no application code edited, fixes only as proposals).
- This run: fired by the scheduled routine "groAML daily: red-team". Shortcut applied: `git ls-remote` shows master `0129848` (same as my reports since 2026-10-07) and no PR beyond #426 exists, so I probed one area I had not covered (the public `/apply` form) and kept this short. Nothing in the routine conflicted with my standing instructions.
- Assumptions: probes ran against a scratch DB with a throw-away local SMTP sink on 127.0.0.1:2525 (stopped afterwards, nothing left the machine) and `AMLKIT_QUOTE_TO=sales@example.test`. Severities are my judgement.

## What I did
Ran `probe_apply_public.py`: CR/LF and header-injection attempts in every text field, email-field tricks, markup, oversized input, rate limits, honeypot and CSRF, reading the notice email the sink actually received. Evidence: `reports/daily/2026-10-14/evidence/probe_apply_public_on_0129848.txt`.

## Findings (new this run)
| Id | Sev | Status | Summary |
|----|-----|--------|---------|
| P1 | Info | CONFIRMED | The multi-line `message` field is copied into the notice email body as typed, so a submitter can plant header-looking lines (`Bcc: ...`, `Subject: spoof`) inside the body, and the applicant-chosen display name appears in `Reply-To` (`"<img src=x onerror=alert(1)>" <jane@acme.ae>`). Not a header injection (they sit after the headers), but it lets an outsider shape what the sales mailbox shows; only a social-engineering risk. |

## Refuted / clean
- Header injection: CR/LF plus `Bcc:` in `org_name` and `contact_name` is collapsed to a space (`Subject: groAML quotation request: Acme Bcc: attacker@evil.test` is one subject line, `To:` stayed `sales@example.test`); the sink received no `Bcc` header.
- Email field: CR/LF, a quoted-local-part trick and a comma list are all rejected (form re-rendered, nothing stored).
- Oversized input: a 5,000-character `org_name` and 50,000-character `message` were accepted and truncated by `_one_line`/`[:2000]`.
- Markup in names is stored raw and header-encoded in the email; no `|safe` in the applications templates.
- Abuse controls: 5 valid submissions per hour per IP, the 6th and 7th return 429; a filled honeypot returns the thank-you redirect and stores nothing; a missing CSRF token re-renders the form and stores nothing.

## Status of earlier findings
Unchanged on `0129848` (no code change): N3 residual invisible-character screening bypasses, N4 `unscreenable` not enforced downstream, N5 CR/LF customer reference silencing the freeze alert, N6 goAML finalise accepting XML-illegal characters, N8 legacy proposals rename-bypassable, M2 TOTP replay, U1-U3 upload findings, A1 account-lockout DoS, C1 UAE PASS verification not bound to the customer, G1 storage paths not pinned, plus the older screening and KYT items. Held proposals are in `scripts/proposals/`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails on every push with a 402 quota error (account-level); needs quota restored or the check made non-required.
- Not exercised by design: all `/system/*` endpoints, production, real UAE PASS endpoints.
- Not checked: the GCS backend at runtime (no credentials), what UAE PASS returns in the live sandbox, `/register-organization` and `/feedback-public` abuse limits.

## Files and commit
Created: `repro_redteam/probe_apply_public.py`; `reports/daily/2026-10-14/red-team.md` and `evidence/`. Earlier probes, reports and proposals carried over. No application code edited and no new proposal needed. Branch `routine/2026-10-14-red-team`; commit SHA in the final reply.

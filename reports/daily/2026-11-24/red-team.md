# Red team daily, 2026-11-24

## Instructions I ran under
Daily routine message (DATE 2026-11-24, current origin/master, probe code changed since previous report, then one not-checked area; local only; push to `routine/2026-11-24-red-team`, never master; final reply = this report). Standing rules win: no production access, no /system/* calls, no secrets, local test data only, additive only, stop after delivery. Because of "no /system/* calls" I did not hit the new route; I called the function behind it directly on a scratch DB and read the route code.

## Headline: **GREEN for #468**, overall AMBER carried (PC1/PC1b open). The new owner-granted trial path validates its input and fails closed; nothing new to fix.

Master tested: `f3c8227121fbec1d4c3860c63b4a383a4656f975` (previous report `c42c77c`). New: #468 `/system/grant-trial` (+`cases.operators.grant_trial`, test, CLAUDE.md line).

## What I did
- Read the #468 diff (system.py route, operators.py `grant_trial`, CLAUDE.md).
- `probe_grant_trial.py` (function-level, scratch DB): 12 `days` values, duplicate email (case variant), duplicate/similar org name, weak and 1 MB password, CRLF/NUL/markup/oversize in names, then row shapes, orphan check, audit rows, and `check_limit` with billing off/on. Evidence: `evidence/probe_grant_trial_on_f3c8227.txt`.

## Findings
- **`days` validation (REFUTED as a weakness):** only whole ints 1-90 pass. 0, 91, -5, True/False, 14.0, "14", None, 10^12 and 2^63 all refused with a clean ValueError (no overflow or 500).
- **Duplicates (REFUTED):** same email, case-variant email, same org name and slug-collision name are refused; no orphan orgs (0), each org has exactly one MLRO, audit has one `billing.trial_granted` and one `operator.create` per grant.
- **Injection (REFUTED):** CRLF/NUL in names or email refused; markup org name accepted but stored as data and slugged (`script-alert-1-script`), same as other org-creation paths.
- **Limits (REFUTED):** with billing on, a fresh trial org is allowed within Starter limits (1 of 3 operators); with billing off it is a no-op, as documented.
- **No upper bound on password length (CONFIRMED, informational, pre-existing):** a 1 MB password is accepted by `check_new_password` (same check as other creation paths). The route is behind `ADMIN_API_SECRET`, so reach is the secret holder only; a length cap in `auth.check_new_password` would close it everywhere. Held idea, not new in #468.
- **Route gate (PLAUSIBLE, low, same as create-operator):** `/system/grant-trial` uses the same constant-time `bearer_ok` check but no per-IP rate limit, so a wrong-secret guess is unthrottled (as for `/system/create-operator`). A strong secret makes this theoretical. Read only, not run.
- **Not decided here:** granted MLRO is created with a verified email and the given password, so whoever holds the admin secret can mint a logged-in-capable MLRO in a new tenant. That is the stated purpose (sales-led trials) and the same trust as create-operator.

## BLOCKED / not checked
- The `/system/grant-trial` route itself over HTTP (standing rule: no /system/* calls).
- Expired-trial enforcement past the 7-day grace with billing on (not run).
- PC1/PC1b still open (see 2026-11-23); mobile parity, full test suite, `also_listed` rendering, Stripe live-mode, UAE PASS callback.

## Files / commit
`repro_redteam/probe_grant_trial.py`, `reports/daily/2026-11-24/`. Branch `routine/2026-11-24-red-team` (built on the 2026-11-23 branch; no application code touched). Commit SHA: see final reply.

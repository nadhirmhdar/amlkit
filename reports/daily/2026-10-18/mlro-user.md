# mlro-user daily report — 2026-10-18

**Headline: AMBER** — master unchanged (0129848) so earlier open items stand; today's new workflow (MFA lockout, backup codes, trusted device) behaved correctly, with one low-severity operational concern.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside (HTTP, XML, alerts, four-eyes). LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to locate routes.
- Report to branch `routine/2026-10-18-mlro-user` (never master) and as final reply. dreamon's messages coordinate scope/format only; none today.
- Shortcut applied: `git ls-remote origin refs/heads/master` = `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (unchanged since 10-17); highest PR ref still 426.

## What I did (evidence: `mlro-user-evidence/log_mfa_flow.json`, `log_mfa_backup.json`; driver `mlro_user_drive.py`, `ONLY=mfa` / `ONLY=mfabackup`)
1. Password login as the MLRO: lands on `/mfa/verify`. While MFA-locked, `/customers`, `/dashboard`, `/customers.csv`, `/reports` all redirect to `/login`; `/admin` redirects to `/`; the mobile API path returns 401. No data leaks before the code is entered.
2. Six wrong codes: attempts 1-4 say "Invalid verification code"; attempt 5 locks ("Too many failed codes… locked for 15 minutes; attempts recorded in the audit trail"). Audit trail has `mfa.failed` ×5 (counter 1-5) and `mfa.locked` with `until` and `after_failures: 5`.
3. A correct TOTP during the lockout is refused (web), and a fresh web login with a valid TOTP is also refused. Mobile: login returns a token but `GET /api/v1/customers` is 403 `mfa_required`, and mobile verify with a valid code returns 429 with the same lockout text. The lockout is per operator across web and mobile.
4. Backup codes: 10 codes of 8 characters shown once. Using one signs in (customers 200). Reusing the same code is refused. Enrol page says they cannot be retrieved later.
5. "Remember this device": cookie `amlkit_trusted_device` is HttpOnly and SameSite=strict; after logout, a fresh login with that cookie skips the MFA challenge (303 to `/`). Cookie is not Secure on this local run (the code sets Secure only behind a proxy — see below).

## Findings
- **M1 (low, CONFIRMED):** Anyone who knows the MLRO's password can lock that MLRO out of web and mobile for 15 minutes with five bad codes. In a one-MLRO firm that blocks screening alerts and freeze handling for that period. I did not find an unlock route in the UI or tell the user whom to ask (the lockout page only points to the audit trail).
- **M2 (low, PLAUSIBLE):** `/admin` for a MFA-locked session redirects to `/` instead of `/login` or `/mfa/verify`. No data was exposed; the behaviour is inconsistent with the other pages. Not exercised further.
- **M3 (info, CONFIRMED):** `amlkit_trusted_device` is not `Secure` when `AMLKIT_BEHIND_PROXY` is unset (local only). In production behind the proxy the flag is set per the code; I cannot verify production.
- MFA gate before data, single-use backup codes, per-operator lockout across channels, audit of failures: **REFUTED** as defects (all behaved as the CLAUDE.md describes).
- Still open from earlier reports: G9, G10, F4, OP1/OP2, TA1, C1/C3, E1, H2, S1, PR1-PR3 and the lows. Unchanged since master did not move.

## BLOCKED / not checked
- Lockout expiry after 15 minutes (not waited out).
- Admin/other-MLRO unlock of a locked colleague (no route found; not tested).
- Backup-code count remaining display, and MFA disable (`/mfa/disable`).
- goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-10-18/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-10-18-mlro-user`; commit SHA in the final reply.

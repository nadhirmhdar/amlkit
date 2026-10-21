# mlro-user daily report — 2026-10-21

**Headline: AMBER** — master unchanged (0129848) so earlier open items stand; today's login-hardening walk shows anyone who knows an operator's email can lock that account out (including the MLRO) with no password, and the lock message confirms the account exists.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to locate routes and read the lockout constants.
- Report to branch `routine/2026-10-21-mlro-user` (never master) and as final reply. No dreamon messages today.
- Shortcut applied: `git ls-remote origin refs/heads/master` = `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (unchanged since 10-20); highest PR ref still 426.

## What I did (evidence: `mlro-user-evidence/log_login_hardening.json`, `log_login_lock.json`; driver `mlro_user_drive.py`, `ONLY=loginhard` / `ONLY=loginlock`)
1. Wrong-credential messages: unknown email and known email with a wrong password both say "Incorrect email or password." Email is case/whitespace-insensitive. Empty password gives a raw 422.
2. Fourteen wrong passwords in a row on the officer account: attempts 1–8 say "Incorrect email or password."; from attempt 9 the page says "Account locked after repeated failed attempts. Try again after 01:56 UTC, or ask an admin…". The correct password is then refused (200 login page, no redirect). Lock = 8 failures / 15 minutes (`MAX_FAILED_LOGINS`, `LOCKOUT_MINUTES`).
3. Five wrong passwords then the correct one on the MLRO account: login succeeds and goes to `/mfa/verify` (below the lock threshold).
4. No HTTP 429 appeared across 14+ POSTs in one minute from one client, although the code declares 10/min per IP and 3/min per account.

## Findings
- **LG1 (medium, CONFIRMED):** An unauthenticated person who knows an operator's email address can lock that account for 15 minutes with 8 bad passwords, and repeat when it expires. For the MLRO this blocks screening, alert and freeze handling; the message says to "ask an admin", which in a firm with one MLRO may be the same person. Combined with M1 (MFA lockout) the MLRO has two ways to be locked out.
- **LG2 (low, CONFIRMED):** Account enumeration: unknown emails never show "Account locked", so after 8–9 attempts the message differs between real and unknown addresses. The generic "Incorrect email or password" for first attempts is fine; the lock message undoes it.
- **LG3 (low, CONFIRMED):** Empty password returns a raw JSON 422 rather than the login page error.
- **LG4 (PLAUSIBLE, not verified):** The declared rate limits (10/min IP, 3/min per account) did not return 429 in my run. The test client may be exempt or share a key the limiter ignores; I cannot tell from outside whether it is enforced in production. Recorded as unverified, not as a defect.
- Same-message handling for known vs unknown email on a failed first attempt: **REFUTED** as a defect.
- Still open from earlier reports: G9, G10, F4, OP1/OP2, TA1, C1/C3, E1, H2, S1, PR1-PR3, M1, M2, PW1, PW2, SS1, AU1-AU3, PV1 and the lows. Unchanged; master did not move.

## BLOCKED / not checked
- Rate-limit enforcement (LG4); a real distinct IP cannot be simulated in the test client.
- Lock expiry (15 min not waited out) and the admin unlock route.
- goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-10-21/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-10-21-mlro-user`; commit SHA in the final reply.

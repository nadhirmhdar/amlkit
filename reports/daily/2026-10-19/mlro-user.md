# mlro-user daily report — 2026-10-19

**Headline: AMBER** — master unchanged (0129848) so earlier open items stand; today's new workflows (self-service password change, forget-devices, concurrent-session cap) work and revoke correctly, with two low-severity wording/UX findings.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside (HTTP, XML, alerts, four-eyes). LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to locate routes (and once to explain the session eviction below).
- Report to branch `routine/2026-10-19-mlro-user` (never master) and as final reply. No dreamon messages today.
- Shortcut applied: `git ls-remote origin refs/heads/master` = `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (unchanged since 10-18); highest PR ref still 426.

## What I did (evidence: `mlro-user-evidence/log_pwchange.json`, `log_which_kills.json`; driver `mlro_user_drive.py`, `ONLY=pw` / `ONLY=kills`)
1. `/account/password` validation: wrong current password → "Current password is incorrect."; mismatch → "New passwords do not match."; `abc` → "Password must be at least 10 characters long"; reusing the current password (lower-case, no uppercase) → fails on the uppercase rule. Each message appears on the form.
2. Password change with three live sessions (web 1, web 2 with a remembered device, mobile bearer token): success redirects to `/`. Afterwards web 1, web 2 and the mobile token (401) are all dead, the remembered-device cookie no longer skips MFA (303 to `/mfa/verify`), and the old password is rejected.
3. `/account/forget-devices`: banner "All remembered devices have been forgotten…"; the old trusted cookie then goes to `/mfa/verify`.
4. First attempt at this test showed my first session being logged out when I opened further sessions. Isolated in `ONLY=kills`: a 3rd concurrent web login evicts the oldest session. Cause: `MAX_CONCURRENT_SESSIONS` default 3 (auth.py), oldest revoked silently.

## Findings
- **PW1 (low, CONFIRMED):** After a successful password change the banner says "All other sessions have been signed out." but the current session is also gone (next page request redirects to `/login`). The text is wrong or the behaviour is unintended; the user is surprised either way.
- **PW2 (low, CONFIRMED):** Same-as-current password is rejected only by the generic complexity rule when the old password happens to be non-compliant; I did not confirm a "must differ from current" check with a compliant old password (not tested; PLAUSIBLE that none exists).
- **SS1 (low, CONFIRMED):** The oldest web session is evicted silently when a 3rd concurrent login happens (default cap 3, mobile tokens included in my run). The evicted user lands on `/login` with no "signed out because you signed in elsewhere" message. An MLRO with desktop, laptop and phone loses a working tab mid-case.
- Revocation on password change (other web sessions, mobile token, trusted devices) and the forget-devices flow: **REFUTED** as defects; they work.
- Still open from earlier reports: G9, G10, F4, OP1/OP2, TA1, C1/C3, E1, H2, S1, PR1-PR3, M1, M2 and the lows. Unchanged; master did not move.

## BLOCKED / not checked
- Password-change audit row (my audit query returned the login page; driver bug, no claim made).
- Whether the cap applies to mobile tokens separately (mixed in my run).
- goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery, forgot-password email.

## Files and commit
- `reports/daily/2026-10-19/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-10-19-mlro-user`; commit SHA in the final reply.

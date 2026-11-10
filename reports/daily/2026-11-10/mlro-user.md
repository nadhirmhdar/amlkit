# mlro-user daily report — 2026-11-10

**Headline: AMBER** — master is unchanged (9219e26), so earlier results stand; today's walk of the mobile admin endpoints found that the mobile API can deactivate the only active MLRO, which the web screen refuses.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to list the mobile admin routes and read the deactivate handler.
- Report to branch `routine/2026-11-10-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master: `git ls-remote origin refs/heads/master` = `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, unchanged since my 2026-11-08 report; highest PR ref still 462. Shortcut applied: one new workflow, short report.

## What I did (evidence: `mlro-user-evidence/log_mobadmin10.json`; driver `mlro_user_drive.py`, modes `mobadm10`, `last10`, `lastm10`)
1. As an officer on the mobile API: create operator, reset password, deactivate operator, set threshold and list admin each return 403 "requires the mlro role".
2. As the MLRO on the mobile API: creating an operator with a weak password is refused; a role of `super_admin` is refused; a name with HTML or a newline is refused; a duplicate email (different case) is refused. Role gate, password rule and name rule match the web screen.
3. Web screen, last-MLRO guard: with the second MLRO deactivated, deactivating myself, the only active MLRO, is refused ("Cannot deactivate the last active MLRO. Promote another operator to MLRO first.").
4. Mobile API, same sequence: `POST /api/v1/admin/operators/{id}/deactivate` for the second MLRO returns 200, then for myself returns 200 `{"ok": true}`. The operators table shows no active MLRO left; my session is revoked and my web login is refused. The officer can still sign in.

## Findings
- **MA1 (medium-high, CONFIRMED):** The mobile deactivate endpoint has no "last active MLRO" check (the web screen has one). One mobile call can leave an organisation with no MLRO. With no active MLRO nobody can file or finalise STR/SAR/CNMR, execute or resolve a freeze, confirm alerts, reset passwords, or unlock accounts: the MLRO-only actions the firm is legally required to perform. Recovery would need a Grovisor administrator.
- **MA2 (low, CONFIRMED):** The mobile endpoint also lets an MLRO deactivate their own account in the same call that ends their session, with no confirmation.
- Role gating, password strength, role validation and name hygiene on the mobile admin endpoints: **REFUTED** as defects.
- Earlier open items unchanged (no application change since the last report): RT1, RT2, CR1, CR2, CR3, UBO1b, SU1, F4, TA2, TA3, high-risk-country field, E2-E5, LN1, SE2, PR5 and the other lows.

## BLOCKED / not checked
- Mobile `admin/refresh` and `admin/threshold` success paths (refresh would call external sanctions sources; not run by rule).
- Rate limiting (my driver disables the limiter), HSTS, payment sign-up, goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-10/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-10-mlro-user`; commit SHA in the final reply.

# mlro-user daily report — 2026-11-13

**Headline: AMBER** — master is unchanged (9219e26); today's walk of operator administration shows one MLRO can switch off the second-reviewer requirement for the whole firm in one click, even when the firm has three operators, and there is no way to change an operator's role.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to list the admin routes and read the single-operator handler.
- Report to branch `routine/2026-11-13-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master: `git ls-remote origin refs/heads/master` = `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, unchanged since my 2026-11-08 report; highest PR ref still 462. Shortcut applied: one new workflow, short report.

## What I did (evidence: `mlro-user-evidence/log_roles13.json`; driver `mlro_user_drive.py`, modes `roles13`, `single13`)
1. Admin page: the form actions are create operator, rename, reset password, deactivate, org profile, refresh, re-screen, threshold and single-operator mode. There is no promote, demote or change-role control, and guessed role-change URLs return 404.
2. Deactivate then reactivate an officer: deactivation signs the officer out immediately and blocks login. Reactivating restores access, and the officer signs in with their old password. Reactivating an operator that is already active says "Operator reactivated." again and writes another audit row; an unknown id says "Operator not found."
3. Single-operator mode: with default settings a sanctions dismissal is "Staged for independent review", and the same MLRO confirming their own dismissal is refused. I then pressed "On" on the admin page (the firm has an MLRO, an officer and a second MLRO): "Single-operator mode is now on." A new sanctions dismissal was then recorded immediately with the note "no independent review - firm is in single-operator mode." An officer cannot change the setting (403).

## Findings
- **SO1 (medium, CONFIRMED):** Any one MLRO can turn single-operator mode on for the whole organisation with one click, even when other operators exist, and from then on sanctions and proliferation dismissals apply with no second reviewer. The change is audited (`org.single_operator_set`) and each dismissal is flagged `single_operator`, which is good, but the four-eyes control the product advertises can be removed by the person it is meant to check. The page text says it is for "firms with genuinely one compliance officer", but nothing enforces it.
- **RL1 (low-medium, CONFIRMED):** An operator's role cannot be changed. The error shown when you try to deactivate the last MLRO says "Promote another operator to MLRO first", but no promote control exists; the only route is creating a new MLRO account with a new email.
- **RL2 (low-medium, CONFIRMED):** Reactivating a deactivated operator restores their previous password. An operator removed for cause regains access with the credential they already know unless the MLRO also resets it.
- **RL3 (low, CONFIRMED):** Reactivating an already active operator reports success and adds a duplicate audit row.
- Deactivation revoking sessions and the audited, MLRO-only gate on these actions: **REFUTED** as defects.
- Earlier open items unchanged (no application change since the last report): RP1, RP2, MA1, MA2, RT1, RT2, CR1, CR2, CR3, UBO1b, SU1, F4, TA2, TA3, high-risk-country field, E2-E5, LN1, SE2, PR5 and the other lows.

## BLOCKED / not checked
- Whether the instance-level environment setting for single-operator mode overrides the per-organisation choice in production.
- Rate limiting (my driver disables the limiter), HSTS, payment sign-up, goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-13/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-13-mlro-user`; commit SHA in the final reply.

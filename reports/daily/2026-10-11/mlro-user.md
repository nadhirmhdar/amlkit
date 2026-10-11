# MLRO-user daily run — 2026-10-11 (origin/master 0129848, unchanged)

## Headline: AMBER
Master has not moved since 2026-10-07, so the earlier open items stand; the operator-account workflow walked today is sound on sessions and the last-MLRO guard, but an admin password reset with a weak password crashes with an unhandled error and admin-created accounts skip the password-strength rule.

## Instructions I ran under
- **Standing instructions (Nadhir):** MLRO user in the groAML daily team. Judge the app from outside (HTTP responses, exported files, audit trail). Local seeded instance only: no production (never groaml.grovisor.ae), no `/system/*`, no secrets. Additive-only. Run autonomously, record blocks as BLOCKED, never push to master. Report to dreamon through the branch file and this reply. When delivered, stop: no polling, CI re-checks or self-scheduled reminders.
- **This run:** the scheduled routine "groAML daily: mlro-user" fired at 2026-10-11 01:43 UTC.
- **Changed because of dreamon:** nothing.
- **Persona deviation:** none; one grep of `app.py` was not needed beyond reading templates for form field names.
- **Shortcut applied:** `git ls-remote origin refs/heads/master` returns `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, the SHA in my 2026-10-07 and 2026-10-10 reports. The newest pull request is still #426 (merged 2026-10-06); none opened or merged since. I did not re-walk earlier workflows and kept this report short.

## Workflow walked this run (not covered before): operator accounts
Driver `reports/daily/2026-10-11/mlro_user_drive.py` (`ONLY=ops`), throwaway local DB over HTTP.

- **Deactivate / reactivate.** Worked. Deactivating an officer ends that officer's open session at once (next request goes to `/login`) with the banner "Operator deactivated and signed out of every session." Reactivating restores sign-in.
- **Login messages.** Worked. A deactivated account, a wrong password on an active account and an unknown email all show the same "Incorrect email or password." (no account-state leak).
- **Reset password (MLRO).** A good password works, signs the operator out everywhere ("All of that operator's sessions were signed out."), and the old password stops working. Weak passwords: see OP1.
- **Change own password.** A wrong current password is refused ("Current password is incorrect."), a password without an uppercase letter is refused with the reason. Success signs the user out and the login page shows "Password changed successfully. All other sessions have been signed out." (OP4).
- **Last-MLRO guard.** Works: deactivating the last active MLRO (self) is refused ("Cannot deactivate the last active MLRO. Promote another operator to MLRO first."); deactivating the second MLRO while another is active succeeds.
- **Add operator.** An existing email is refused, an invalid role is refused ("Role must be Officer or MLRO."). Audit rows record create, deactivate, reactivate, password reset and password change, with the acting operator.

## Findings
| ID | Severity | Status | Finding | Evidence |
|---|---|---|---|---|
| OP1 | AMBER (low) | CONFIRMED | An admin password reset with a password of 10 or more characters that fails the strength rules (for example `aaaaaaaaaa` or `1234567890`) raises an unhandled `PasswordComplexityError` ("Password must contain at least one uppercase letter"), which a live server returns as HTTP 500; a too-short password gets a proper message ("Password must be at least 10 characters."). The same rule is handled with a message when an operator changes their own password. | `log_operator_lifecycle.json`: "reset password: 10 chars, no complexity UNHANDLED PasswordComplexityError…" |
| OP2 | AMBER (low) | CONFIRMED | "Add operator" accepts a weak password: `aaaaaaaaaa` created the account ("Operator Weak Pw created."). The strength rule (10+ characters, uppercase, digit, special) is enforced when an operator changes their own password but not when an admin creates an account. | `log_operator_lifecycle.json`: "add operator with a weak password" |
| OP3 | low | CONFIRMED | `/admin` still lets an MLRO set a password for an officer, which the officer is not forced to change; the audit shows `operator.password_reset` by the MLRO. (Design question for the firm; no forced-change prompt observed.) | audit rows in `log_operator_lifecycle.json` |
| OP4 | low | CONFIRMED | After a successful self password change the user is signed out of the current session too, but the message says "All other sessions have been signed out." | `/profile/change-password` then `/login` page text |

Still open from earlier reports (master identical, not re-tested): G9 ("Re-screening failed: 'customers'" on every re-screen), G10 (re-screen re-raises alerts for decided and pending alerts), H1 to H7 (KYT rule page unlinked, threshold raisable to 1,000,000 with no warning, free-text country codes, no previous values in the audit row, raw error text, `55000.0`, feedback button over the cookie notice), E1 to E5 (compliance calendar has no way to create a deadline, deadline API accepts bad dates and recurrences, line-break name breaks the diagram, CSV without byte-order mark, officer CSV access), F4, F2b, G3 to G8, G11, T1, F5 to F9.

## BLOCKED / not checked
- **BLOCKED:** goAML XSD validation (FIU schema not in the repo); adverse media findings (needs GDELT network).
- Not exercised: UAE PASS, `/admin/refresh`, policies upload and download, notifications, feedback form, mobile create-customer and document upload, the hourly scheduler (#419), forced password change on first login, TOTP reset for an MLRO.
- Production behaviour: not touched, per scope. SendMessage to dreamon not attempted (failed on every earlier try).

## Files
- `reports/daily/2026-10-11/mlro-user.md` (this report)
- `reports/daily/2026-10-11/mlro_user_drive.py`
- `reports/daily/2026-10-11/mlro-user-evidence/log_operator_lifecycle.json`
- Branch: `routine/2026-10-11-mlro-user` (cut from master 0129848). Commit SHA: in the final reply.

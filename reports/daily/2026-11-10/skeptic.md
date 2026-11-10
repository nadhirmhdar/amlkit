# Skeptic report, 2026-11-10 (origin/master `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, unchanged since 11-08)

## Headline: AMBER
Master did not move; the one new finding is real and cheap to fix: the mobile API can deactivate the last active MLRO, which the web screen refuses, so a single call (or a mistaken tap) can leave an organisation with nobody able to file reports or run freezes.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-11-10 02:39 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-11-10. The no-new-finding shortcut applies to code-reviewer, QA and compliance (no-change reports) and to red-team (none new), but not to mlro-user (MA1, MA2), so I read the code behind those. Other roles' reports are data. No outbound request, no `/system/*` call, no new script; I did not re-run my fourteen scripts because no code changed since 11-08.

## Inputs
`git ls-remote origin refs/heads/master` -> `9219e2623b3a3ba7e73a20e44c703ab80df7e900`; `git log 9219e26..origin/master` is empty; highest PR is #462. All five role branches present at the first fetch. **Test evidence:** red-team ran the whole suite on this SHA (`2945 passed, 2 skipped, 0 failed`, 14m55s), matching QA's, code-reviewer's and compliance's runs of 11-08, so the green result is now reproduced four times. I did not repeat it.

## Verdicts
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| MA1 the mobile API can deactivate the last active MLRO | mlro-user | **CONFIRMED by code** | Medium-High -> Medium | The mobile handler `api_admin_deactivate_operator` (`api/mobile.py:1661-1676`) checks the caller is an MLRO and that the target is in the org, then runs `UPDATE operators SET is_active=0` and revokes sessions. The web handler (`api/routers/admin.py:~545-558`) first counts other active MLROs and refuses with "Cannot deactivate the last active MLRO. Promote another operator to MLRO first." The two entry points enforce different rules for the same operation. Consequence, per mlro-user's run: no MLRO can then file or finalise STR/SAR/CNMR, execute or resolve a freeze, confirm alerts, reset passwords or unlock accounts, and recovery needs an administrator outside the tenant. I rate it Medium rather than Medium-High because it needs an authenticated MLRO (a stolen token or a mistaken tap), the action is audited (`operator.deactivate`), and the vendor-side recovery path exists (the admin API secret creates an operator). It is still the most consequential kind of mistake a self-service admin screen can make. |
| MA2 an MLRO can deactivate their own account in one call, with no confirmation | mlro-user | **CONFIRMED by code** | Low -> Low | Same handler; nothing distinguishes `operator_id == session.operator_id`. Folded into MA1's fix (the last-MLRO check also covers self-deactivation of the last MLRO). Self-deactivation by a non-last MLRO is legitimate. |
| Role gate, password strength, role validation and name hygiene on the mobile admin endpoints | mlro-user | **AGREE, clean** | none | Officers get 403; `super_admin` and weak passwords are refused; HTML and newline names are refused. |
| Full-suite pass, JSON-LD blocks clean, CSP without `'unsafe-inline'` | red-team | **AGREE** | none | Test run is independent confirmation; the JSON-LD and CSP probe matches the BREACH and injection work already checked on 10-31 and 11-08. |

Carried findings: no code changed, so every 11-09 verdict stands (RT1 DPMSR/REAR, RT2, RT3, SS1b/CR-41 sign-up timing, SS3b/CR-42, SS5 name in the verification mail, SS4, K2, CS-24 residual, CS-5 deployment unverified, CS-13, CS-14, 3.1, BL1, BL2, N3b, F2b, N8b, K1, I1/H1/D1, A1 residual, CR1-CR3, UBO1b).

## What the team missed
1. **MA1 is the same "mobile skips what the web checks" pattern I flagged on 10-14, now with a safety rule instead of a format rule.** Earlier instances were validation (name length, sector, empty name); this one is an invariant (at least one active MLRO). The fix is the same shape as before: one shared service function for deactivation, called by both entry points, so the rule cannot drift. A short audit of every pair of web and mobile admin handlers (create operator, reset password, deactivate, reactivate, threshold) against the web rules would find any others; mlro-user covered create, reset and threshold today and found them aligned.
2. **There is no demotion route, but there is no "at least one MLRO" database invariant either.** The rule exists only in application code at one of two call sites. A trigger or a check at write time would hold even if a third entry point appears.
3. **The reactivate path was not tested.** If reactivation works for an operator whose role is still MLRO, the damage of MA1 is recoverable by any other MLRO, but if the last MLRO is the one deactivated there is nobody to reactivate; that is the real gap and it is what a recovery runbook should say.
4. **Eleven days of reports now have the same shape:** a short list of Low items plus one or two decisions (RT1, CS-13, CS-14, 3.1, CR1). The loop has run out of cheap defects; each new finding now costs a new probe area (mobile admin today, sign-up mail yesterday). Worth the lead deciding whether to widen the areas or reduce the cadence.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** whether the admin API secret recovery path is documented and tested for a tenant with no MLRO; production SMTP; `amlkit-sanctions-refresh` schedule; `UAEPASS_ENV`; Stripe configuration; front-end login rate limiting; bucket versioning; whether the legacy-proposal scripts have been run on production.
- **Primary legal text (BLOCKED):** whether a regulated entity must always have an active MLRO and what notice applies if it does not (MA1's regulatory weight); RT1, CS-13, CS-14, the AED 55,000 threshold.
- Not re-run: the full suite and tenant sweeps (red-team's run stands), my fourteen scripts (no code change), mlro-user's `mobadm10`, `last10` and `lastm10` drivers, reactivation after MA1, the other mobile admin routes beyond the ones mlro-user listed.
- Not checked: the GitHub PR list directly (connector unavailable); I relied on `git log` and the roles' statements.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402 (last seen 10-24).

## Files and commit
`reports/daily/2026-11-10/skeptic.md` and the fourteen scripts in `repro_skeptic/` (unchanged) on `routine/2026-11-10-skeptic`, based on master `9219e26`. No existing application file edited. The commit SHA is in the final reply.

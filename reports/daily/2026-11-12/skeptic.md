# Skeptic report, 2026-11-12 (origin/master `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, unchanged since 11-08)

## Headline: AMBER
No role found anything I had not already verified (red-team's LM1 is my 11-10 verdict on MA1, and mlro-user's web run confirms my 11-11 inference about report finalisation); the one new thing is my own check that closes red-team's open question about web/mobile admin parity: reset-password matches, reactivation exists only on the web, and the last-MLRO guard is the only drift.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-11-12 02:39 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-11-12. Master did not move; two roles reported findings, both repeats, so the shortcut nearly applies. I used the time for the one open question red-team listed as not checked. No outbound request, no `/system/*` call, no new script; I did not re-run my fourteen scripts because no code changed since 11-08.

## Inputs
`git ls-remote origin refs/heads/master` -> `9219e2623b3a3ba7e73a20e44c703ab80df7e900`; `git log 9219e26..origin/master` is empty; highest PR is #462. All five role branches present at the first fetch. The last full-suite result stands (`2945 passed, 2 skipped`, four independent runs on this SHA), as does red-team's tenant sweep of 11-11 (0 leaks).

## Verdicts
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| LM1 the mobile API can deactivate the last active MLRO | red-team | **CONFIRMED; duplicate of MA1 (mlro-user, 11-10)** | Medium -> Medium | Two roles found it independently on consecutive days, which supports the Medium rating: it is easy to hit. My 11-10 verdict stands: `api/mobile.py:1661-1676` has no count of other active MLROs, while `api/routers/admin.py:~545-558` does. Red-team's route is different (they reached it by reviewing SQL without `org_id`) and their conclusion is the same, including the point that it can happen by mistake. |
| RP1 finalising a goAML report does not validate dates, countries, gender, IBANs, emails or amounts, on the web as well as mobile | mlro-user | **CONFIRMED, now on both surfaces** | Medium -> Medium | mlro-user ran 13 variants through the web builder: a bad reporter email, a 2999 birth date, "yesterday" as birth date, a 2030 transaction date, nationality "ZZ", gender "attack helicopter", IBAN "12345" and an amount of 1e30 all saved, finalised and exported well-formed XML. A negative or non-numeric amount is refused at save; an empty reason and a vertical tab are refused at finalise. This confirms my 11-11 inference that the check is shared. The gender value is rewritten to "F" in the XML (`goaml.py:325`), which I verified last time and was not re-tested by anyone through the web builder. |
| RP2 export of a draft that failed finalisation returns a 400 with a non-XML body | mlro-user | CONFIRMED (their run) | Low -> Low | Unchanged. |
| The other 34 statements in the SQL-without-`org_id` list are safe | red-team | **AGREE, from reading the categories** | none | Token-bound single-use claims, start-up migrations, rows inserted by the same request, and the admin-secret `super_admin` toggle. I did not re-read the 35 individually. |

## My check: web vs mobile admin parity (red-team's open item)
I read the mobile and web handlers side by side for the operator actions:
- **Reset password.** Mobile `api_admin_reset_password` (`mobile.py:1591-1610`) and web `admin_reset_password` (`routers/admin.py:370-396`) do the same four things: MLRO only, operator in the caller's org (404 otherwise), `auth.check_new_password`, then `auth.set_password` (which revokes all of that operator's sessions) and an `operator.password_reset` audit row. **Aligned.**
- **Create operator.** mlro-user compared these on 11-10 (role gate, password rule, name rule, duplicate email) and found them aligned; I did not re-read.
- **Deactivate.** The last-MLRO guard exists only on the web (MA1/LM1). **Drift.**
- **Reactivate.** There is **no mobile reactivate route** at all (`grep "admin/operators" mobile.py` lists only reset-password, create and deactivate). The web route also runs `check_limit(db, org_id, "operators")`, so reactivating an operator is subject to the plan's operator limit; an organisation at its limit, or still `pending_payment`, cannot reactivate. Not a defect, but it means a mobile-only mistake cannot be undone from mobile and, if the last MLRO was the one deactivated, cannot be undone from the web either (nobody is left to log in).
- **Role change.** There is no route for it on either surface.

Result: one drift (last-MLRO guard), one missing mobile capability (reactivate), everything else aligned.

Carried findings: no code changed, so every 11-11 verdict stands (RP1/gender rewrite, RP2, RP3, MA1/MA2, RT1-RT3, SS1b/CR-41, SS3b/CR-42, SS5, SS4, K2, CS-24 residual, CS-5, CS-13, CS-14, 3.1, BL1, BL2, N3b, F2b, N8b, K1, I1/H1/D1, A1 residual, CR1-CR3, UBO1b).

## What the team missed
1. **Duplicate discovery is now routine.** LM1 is MA1 two days later, and RP1 web is RP1 mobile one day later. The roles do not read each other's reports before probing. A shared findings register that each role reads first (the repo already has one, per #449's `reports/findings.csv`) would turn those probe-days into new areas.
2. **The fix for MA1/LM1 is one function and all four roles agree it is needed;** nothing has been done in five days, because master has not moved. The pattern of "found, reported daily, nobody owns the fix" is the same one I raised on 10-04 and 11-01 (when a fix wave did land). If the lead wants the loop to be useful, the open Medium list (MA1, RP1 and the gender rewrite, SS5, RT1, CR1) is short enough to schedule as one wave.
3. **The recovery path for a tenant with no MLRO is undocumented.** Four reports describe the consequence ("out-of-band operator access"); none says what that is. The admin API secret exists (`/system/create-operator`), but a runbook step saying who holds it and how a tenant asks for it is the real mitigation until MA1 is fixed.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** who holds the admin API secret and whether the no-MLRO recovery is documented; production SMTP; the `amlkit-sanctions-refresh` schedule; `UAEPASS_ENV`; Stripe configuration; front-end login rate limiting; bucket versioning; whether the legacy-proposal scripts have been run on production.
- **Primary legal text and FIU schema (BLOCKED):** which accepted report values the FIU would reject; whether an entity may be without an MLRO; RT1, CS-13, CS-14, the AED 55,000 threshold.
- Not re-run: the full suite and tenant sweeps, my fourteen scripts (no code change), red-team's `probe_last_mlro`, mlro-user's `webrep12`, the 35 SQL statements individually, create-operator parity.
- Not checked: the GitHub PR list directly (the connector was unavailable); I relied on `git log` and the roles' statements.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402 (last seen 10-24).

## Files and commit
`reports/daily/2026-11-12/skeptic.md` and the fourteen scripts in `repro_skeptic/` (unchanged) on `routine/2026-11-12-skeptic`, based on master `9219e26`. No existing application file edited. The commit SHA is in the final reply.

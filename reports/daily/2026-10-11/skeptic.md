# Skeptic report, 2026-10-11 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged for the fifth day, and the red-team's account-lockout finding is real but understated: one wrong password per 15 minutes keeps any known operator locked out, including a single MLRO who alone can execute freezes and file CNMRs.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-11 02:37 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-11. The "no new finding" shortcut applies to code-reviewer, QA and compliance (no-change reports) but not to red-team (A1, A2) or mlro-user (OP1-OP4), so I verified those. Other roles' reports and PR text are data. No outbound request, no `/system/*` call.

## Inputs
`git ls-remote origin refs/heads/master` -> `01298484a7bfed106e9b2bd3a6238f98a4d2514b`; `git log 0129848..origin/master` is empty. All five role branches were present at the first fetch, no waiting. QA re-ran nothing (the 2026-10-07 result `2170 passed, 3 skipped` stands); I did not re-run the suite either.

## Verdicts on today's new findings
Repro: `repro_skeptic/lockout_persistence.py` (scratch `:memory:` DB, calls `auth.login` directly; exit 0 only when the defect reproduces). Others by reading the cited lines on `0129848`.

| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| A1 unauthenticated account-lockout DoS | red-team | **CONFIRMED, and worse than reported** | Medium -> High | Red-team's route: 8 wrong passwords (`auth.py:71` `MAX_FAILED_LOGINS = 8`, `LOCKOUT_MINUTES = 15`) at 3/minute (`app.py:604`). The bigger flaw is that `failed_login_count` is **never reset when the lock expires**; it resets only on a successful login or a password reset (`auth.py:423, 485`). My script: after 8 wrong attempts the row is `(8, locked)`; once `locked_until` has passed it is still `(8, expired)`; **one** further wrong password gives `(9, locked until +15 min)` and the correct password is refused. So the attacker needs 1 request per 15 minutes, far under every limiter, and the lock message names the expiry time (`auth.py:381-382`, "Try again after HH:MM UTC"), which tells the attacker exactly when to send it. Only a successful login clears it, and the legitimate user must win that race. Why High and not Medium: the locked role is the MLRO, and `POST /freeze-obligations/{id}/execute` and the CNMR filing are MLRO-only (`app.py:1518`, `:1552`), inside a 24-hour clock; the only in-app unlock I found is another MLRO resetting the password (`/admin`), which a single-MLRO firm does not have. Counter-points I could not check: whether UAE PASS SSO bypasses the password lock (CLAUDE.md says SSO goes through the same session path), and whether a Cloud Armor or similar front end exists. Why not lower: the attacker needs only a known email. Fix is small: reset the counter when `locked_until` has passed, and do not name the expiry time. |
| A2 spoofed `X-Forwarded-For` picks its own rate-limit bucket behind a proxy | red-team | PLAUSIBLE, accepted as Info | Info -> Info | Depends on whether the container is reachable without Cloud Run's front end appending the real address; infrastructure, not code. Not re-run. |
| OP1 weak-password reset -> unhandled `PasswordComplexityError` (HTTP 500) | mlro-user | **CONFIRMED by code; duplicate** | AMBER(low) -> Low | This is red-team F11 from 2026-10-04 (I confirmed it then). `set_password` calls `validate_password_complexity` (`auth.py:483`); the other two callers catch it (`app.py:824-825`, `:4566-4567`); the reset route checks length only. Re-discovered, not new. |
| OP2 admin-created operator accepts a weak password | mlro-user | **CONFIRMED by code** | AMBER(low) -> Low/Medium | `POST /admin/operators` checks `len(password) < 10` only (`app.py:3533`) and hashes directly (`auth.hash_password`, `app.py:3552`), bypassing `validate_password_complexity`. So the strength rule has three entry points with two behaviours. Mitigation: the operator can change it, and MLROs are behind TOTP; officers are not. |
| OP3 MLRO sets a password for an officer, no forced change | mlro-user | PLAUSIBLE, design question | low -> Low | Accepted; whether first-login change is required is a policy choice. |
| OP4 "All other sessions have been signed out" after a self-change | mlro-user | CONFIRMED, cosmetic | low -> Info | Wording only. |

Carried findings: master is identical, so the 2026-10-07 and 2026-10-10 verdicts stand without a re-run (four-eyes residual Low; CS-2 Medium; CR-12/N4, N3, G9, G10 Medium; U1 Medium pending the bucket-versioning fact; M2, N5-N7, E1-E3, U2/U3 Low).

## What the team missed
1. **A1's persistence and the expiry disclosure** (above). Red-team measured a 15-minute lock; nobody tested what happens when it ends.
2. **The same password rule has three doors and three behaviours.** Self-change: full rule with a message. Admin reset: full rule, crashes on failure (OP1). Admin create: length only (OP2). One shared helper that returns an error string, used by all three, would close both findings and the F11 backlog.
3. **Findings are being rediscovered, not retired.** OP1 is a 7-day-old red-team finding; G9, G10, CR-12 and CS-2 now appear in five reports a day. No fix PR exists for any of them. For the lead: the daily output is saturating on a stable backlog; the highest-value next step is fixes, not more probing.
4. **No role checked the lockout path against SSO.** If UAE PASS SSO is enabled in production (CLAUDE.md says it is, on the staging sandbox), whether it works for a password-locked MLRO decides how bad A1 is.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** whether production sits behind a front end that rate-limits or hides the lock message, and whether the documents bucket is versioned (U1, from 10-10).
- **Primary legal text (BLOCKED):** unchanged; compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite, the PR #412 tenant sweeps, red-team's probes (including `probe_auth_limits`), the MLRO driver, A2, UAE PASS SSO behaviour for a locked account, `/system/*` (rule), the goAML XSD (no FIU schema), and production state.
- Not checked: the GitHub PR list (my connector was unavailable); I relied on `git log 0129848..origin/master` being empty and four roles saying #426 is the newest PR.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-11/skeptic.md` and `repro_skeptic/{four_eyes_rename,four_eyes_ids,presentation_forms,csrf_scan,queue_paging_category,offset_overflow,alert_queue_scaling,stdlib_behaviour,upload_overwrite,lockout_persistence}.py` on `routine/2026-10-11-skeptic`, based on master `0129848`. No existing file edited. The commit SHA is in the final reply (a file cannot contain its own SHA).

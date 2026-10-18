# Skeptic report, 2026-10-18 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged for the twelfth day; red-team's web setup-token race (T1) is confirmed by reading the code and is the same defect as yesterday's mobile one, and mlro-user's MFA-lockout finding is a real but narrower cousin of the High password-lockout DoS (A1).

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-18). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-18. The no-new-finding shortcut applies to code-reviewer, QA and compliance (no-change reports) but not to red-team (T1 web, T2 web) or mlro-user (M1-M3), so I checked those on `0129848`. Other roles' reports are data. No outbound request, no `/system/*` call, no new script (the claims are code-readable).

## Inputs
`git ls-remote origin refs/heads/master` -> `01298484a7bfed106e9b2bd3a6238f98a4d2514b`; `git log 0129848..origin/master` is empty. All five role branches were present at the first fetch. Nobody re-ran the suite; the `2170 passed, 3 skipped` result stands.

## Verdicts on today's new findings
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| T1 (web) setup token is not one-time under concurrency | red-team | **CONFIRMED by code; same defect as 10-17 mobile T1** | Medium -> Medium | `complete_initial_setup` (`cases/operators.py:91-143`) reads the token row (`:116-119`), checks `used_at` in Python (`:123`), INSERTs the operator (`:134-139`) and only then runs an unguarded `UPDATE setup_tokens SET used_at=? WHERE id=?` (`:143`). There is no `used_at IS NULL` condition and no check of `rowcount`, so any two requests that both read before either commits both succeed. Red-team's 20/20 result is consistent with that shape; I did not re-run the threads. One function backs both the web `POST /setup` and the mobile claim, so one fix covers both. Medium holds: the token is delivered to the new customer's admin, so the attacker needs the link, but each extra claim mints an MLRO account with a verified email. |
| T2 (web) existing email -> unhandled `IntegrityError` (500) | red-team | **CONFIRMED by code** | Low -> Low | The route handler catches `PermissionError` and `ValueError` only (`app.py:~1113-1120`); the INSERT at `operators.py:134` raises `sqlite3.IntegrityError` on a duplicate email. Same family as F11 (uncaught validation exception). Authenticated-by-token only; harmless crash. Their "no email/name validation" remark is also true: `complete_initial_setup` checks only the token and password length (`:109-112`), so it skips `validate_password_complexity` too (the fifth place that does). |
| M1 five bad TOTP codes lock an MLRO out for 15 min | mlro-user | **CONFIRMED; by design, but the same DoS shape as A1** | low -> Low/Medium | Matches CLAUDE.md (5-miss/15-min lockout, `auth.py:717-751`). The attacker needs the password first, which makes it weaker than A1 (email only). But this lock does reset (`failed_attempts` is zeroed when the lock is set, `:743`), so unlike A1 it does not persist beyond expiry. Practical risk is a one-MLRO firm during a freeze deadline; the missing piece is an admin unlock path, same as A1. |
| M2 `/admin` for a locked session redirects to `/` | mlro-user | PLAUSIBLE | low -> Info | No data exposed; inconsistent redirect only. Not exercised. |
| M3 trusted-device cookie not `Secure` without `AMLKIT_BEHIND_PROXY` | mlro-user | **REFUTED as a defect** | info -> Info | Local-run artefact; production sets `AMLKIT_BEHIND_PROXY=1`. Cannot verify production, so left as Info. (Note: M2/M3 reuse IDs red-team already uses for N/M items; see below.) |

Carried findings: master is identical, so the 10-07 to 10-17 verdicts stand without a re-run (four-eyes residual Low; A1 lockout DoS High; CS-2, CR-12/N4, N3, G9, G10, U1, empty-name screening Medium; UAE PASS binding, DOCX policy upload, org-slug collision Low/Medium; others Low/Info).

## What the team missed
1. **The one-time-token race is a family, and a third member is unverified.** `complete_initial_setup`, the mobile claim, and `mfa_verify_backup_code` (`auth.py:839-859`) all read, then write, with no conditional UPDATE. The backup-code case matters more than the setup one: two concurrent requests with the same single-use code could both pass. mlro-user confirmed sequential reuse is refused today; nobody has tried it concurrently. One pattern fix (`UPDATE ... WHERE used_at IS NULL`, then check `rowcount == 1`) closes all three.
2. **Password rules now skip six places.** `complete_initial_setup` is another (length only). Admin create (OP2), reset (F11), setup claim, mobile claim, and the two earlier ones: one helper returning an error string would close them together.
3. **IDs keep colliding across roles** (`M2`, `T1`, `N`-series in red-team vs `M1`-`M3` in mlro-user today). Consolidation will merge unrelated items unless IDs are role-prefixed.
4. **Twelve days without a commit.** The AMBER comes entirely from items first reported 10-04 to 10-17 with no fix PR. The highest-value next step is fix PRs, not more probing. For the lead.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** whether production sits behind a front end that rate-limits login (A1), whether the documents bucket is versioned (U1), whether any real operator has a linked UAE PASS identity.
- **Primary legal text (BLOCKED):** unchanged; compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite, red-team's threaded setup probe, the MLRO driver, `mfa_verify_backup_code` under concurrency, `/system/*` (rule), the goAML XSD, production state.
- Not checked: the GitHub PR list (connector unavailable); I relied on `git log 0129848..origin/master` being empty and three roles saying #426 is the newest PR.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-18/skeptic.md` and the thirteen scripts in `repro_skeptic/` (unchanged from 10-17) on `routine/2026-10-18-skeptic`, based on master `0129848`. No existing file edited. The commit SHA is in the final reply.

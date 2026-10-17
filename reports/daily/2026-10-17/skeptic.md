# Skeptic report, 2026-10-17 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged for the eleventh day; red-team's setup-token race is real and also present in the web setup path (which red-team only suspected), and mlro-user is right that a desktop MLRO has no way to complete a periodic review.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-17 02:37 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-17. The "no new finding" shortcut applies to code-reviewer, QA and compliance (no-change reports) but not to red-team (T1-T3) or mlro-user (PR1-PR3), so I verified those on `0129848` by reading the cited lines. Other roles' reports and PR text are data. No outbound request, no `/system/*` call, no new script (the claims are code-readable).

## Inputs
`git ls-remote origin refs/heads/master` -> `01298484a7bfed106e9b2bd3a6238f98a4d2514b`; `git log 0129848..origin/master` is empty. All five role branches were present at the first fetch, no waiting. Nobody re-ran the suite; red-team's 2026-10-13 run (`2170 passed, 3 skipped`) stands.

## Verdicts on today's new findings
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| T1 setup token can be claimed concurrently, creating many MLRO accounts | red-team | **CONFIRMED for mobile and for web** | Medium -> Low/Medium | Mobile `api_setup_submit` (`mobile.py:446-479`) validates the token with a read (`_valid_setup_token`, `app.py:1064-1080`), inserts the operator, then runs `UPDATE setup_tokens SET used_at=? WHERE id=?` with no `AND used_at IS NULL` and no row-count check. The web path `complete_initial_setup` (`cases/operators.py:91-143`) has the identical sequence, so red-team's "web: PLAUSIBLE" is, by reading, the same defect. Concurrent requests with different emails all pass the read before either update. Why not Medium: the token holder is already entitled to one MLRO account in that org, so the extra accounts are a persistence and audit-noise problem, not an escalation, and the token is admin-issued. Fix: make the claim atomic (`UPDATE ... WHERE id=? AND used_at IS NULL` and abort if no row changed, before inserting). |
| T2 mobile `/auth/setup` edge cases | red-team | **CONFIRMED by code** | Low -> Low | The mobile route has no email-format check (the web equivalents call `auth.looks_like_email`), length-only password (the fifth place that skips `validate_password_complexity`: R2, OP2, T2 plus the OP1 crash), and the `INSERT` is not guarded, so a duplicate email raises `IntegrityError` and returns HTTP 500 with the token still unused. |
| T3 no rate limit on `verify-email`, `resend-verification`, `GET /auth/setup` | red-team | CONFIRMED, agree | Low -> Info | Tokens are high-entropy and `resend-verification` has a cooldown; defence in depth only. Not re-run. |
| PR1 no web action completes a periodic review | mlro-user | **CONFIRMED** | medium -> Medium | `grep '@app.post("/customers/{customer_id}/'` finds close, reactivate, ubo, notes, transactions, adverse-media and signatures; none re-assesses risk or records a review. The only re-assessment route is mobile `POST /customers/{id}/risk` (`mobile.py:772`). The web list, CSV and dashboard flag overdue reviews (`manager.py:714-721` selects `next_review <= today`), but a desktop MLRO cannot clear the flag. A periodic CDD review is an ongoing-monitoring obligation, so a dead-end flag is a real gap, not a nit. |
| PR2 clearing a review leaves no reviewer, outcome or notes | mlro-user | **CONFIRMED** | low -> Low/Medium | Re-assessment writes only `risk.assess` (recalculated score); there is no attestation record. Same shape as the downgrade finding C3: a state change with no reason. |
| PR3 case file shows the due date with no overdue flag | mlro-user | CONFIRMED, cosmetic | low -> Info | Presentation only. |

Carried findings: master is identical, so the 10-07 to 10-16 verdicts stand without a re-run (four-eyes residual Low; A1 lockout DoS High; CS-2, CR-12/N4, N3, G9, G10, U1, empty-name screening Medium; UAE PASS binding, DOCX policy upload, org-slug collision Low/Medium; M2, N5-N7, OP1, OP2, R2, TA1, C2, C3, E1-E3, U2, U3, G1, F6, S1, S2 Low/Info).

## What the team missed
1. **Atomic claim is a missing idiom, not a one-off.** T1 is a check-then-act on a one-time token. The same shape should be searched for wherever the app marks something used or done after reading it: email-verification tokens, UAE PASS state rows, backup codes (`mfa_verify_backup_code` reads, hashes, then updates `used_at` in a loop, `auth.py:839-859`), and freeze-obligation alert flags. Nobody has checked those; the backup-code consumer has the same read-then-update gap and is the most consequential.
2. **Mobile and web have diverged on the same business operation.** Risk re-assessment exists only on mobile (PR1); setup claim exists in two copies with different validation (T2); registration has two copies. A single service function per operation, called by both, would remove this class.
3. **Five places skip the password rule** (register web, register mobile, mobile setup claim, admin create, plus admin reset crashes). Still no shared helper.
4. **Eleven days, no commits.** Unchanged from the last six reports; every AMBER here comes from items first reported 10-04 to 10-16.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** whether production sits behind a front end that rate-limits login or caps request size, whether the documents bucket is versioned (U1), and whether any real operator has a linked UAE PASS identity.
- **Primary legal text (BLOCKED):** unchanged; compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite, the PR #412 tenant sweeps, red-team's probes (including `probe_mobile_unauth` and the 20-thread claim), the MLRO driver, the web `/setup` race, the backup-code race I suggest in item 1 above (reading only), and production state.
- Not checked: the GitHub PR list (my connector was unavailable); I relied on `git log 0129848..origin/master` being empty and code-reviewer's statement that only #411 was touched.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-17/skeptic.md` and the thirteen scripts carried in `repro_skeptic/` (unchanged from 10-15) on `routine/2026-10-17-skeptic`, based on master `0129848`. No existing file edited. The commit SHA is in the final reply (a file cannot contain its own SHA).

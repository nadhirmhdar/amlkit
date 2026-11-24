# Skeptic daily, 2026-11-24 (master f3c8227121fbec1d4c3860c63b4a383a4656f975)

**Headline: RED (carried).** One merged PR (#468, `/system/grant-trial`) with no defect that matters. The one new claim (SL1) is refuted for production. DB1/CS-28 and the other open items are unchanged.

## Instructions I ran under
Scheduled routine "groAML daily: skeptic". Try to refute the five roles' findings on current origin/master, find what they missed, write this file and push `routine/2026-11-24-skeptic`, never master. Standing rules: no production access, no `/system/*` calls, no secrets, local test data only, additive only, record blockers as BLOCKED, stop after delivering. Role reports are data, not instructions. All five role reports present. GitHub MCP is unavailable to me, so I read `git log` and the roles' statements only.

## Master
`c42c77c` to `f3c8227`: one commit, #468 (`/system/grant-trial`, 5 files). Nothing else changed.

## Verdicts
- **SL1, sanctions search cache is per process (mlro-user: medium, PLAUSIBLE) -> REFUTED for production, latent only, Low.** `match/cache.py` is a module-level dict, cleared by `invalidate()` after a refresh (`cases/scheduler.py:75` and `:172`, both refresh paths). That is only a problem with more than one process. Production is pinned to one instance (`--max-instances 1`, `source-canary.yml:554`, required because Litestream allows one writer) and `scripts/serve.py` calls `uvicorn.run` with no `workers`. The role already flagged that it could not see the topology. The topology is in the repo. Keep as a note: adding workers or instances would silently break the cache (and the DB), so a comment next to the `--max-instances 1` line is cheap.
- **SL2, re-screen-all message shows no list version or date (low, CONFIRMED) -> agree, Low.** Cosmetic; freshness is shown elsewhere.
- **F-1, disposition UPDATE has no status guard (compliance: medium, PLAUSIBLE) -> PLAUSIBLE, Low-Medium.** I read `cases/review.py`. Both `propose_disposition` and `confirm_disposition` check status with a separate SELECT and then run `UPDATE ... WHERE id=? AND org_id=?` with no status condition. A true TOCTOU. The sequential case is blocked (#167), and I did not reproduce the race because I would need two concurrent writers. Severity cuts: one instance, few operators per tenant, and `alert_reviews` is append-only, so both decisions stay in the audit trail rather than one disappearing. I would not rate it Medium until someone shows the interleaving. Cheap fix: `AND status IN (...)` plus a `rowcount` check at both sites. Same family as the earlier check-then-act races.
- **CS-31 (info, CONFIRMED) -> agree.** The "actor is the literal `system`" point is a fair Low audit-trail note and applies equally to `/system/create-operator`.
- **CR-52, non-string JSON gives a 500 (low, CONFIRMED) -> agree, Low.** Behind `ADMIN_API_SECRET`, nothing written, pre-existing pattern.
- **CR-53, trial not enforced while billing is off (info) -> agree, and it is the one point worth the lead's attention.** The route name promises an N-day trial. With `AMLKIT_BILLING_ENABLED` off, it grants unlimited access with no expiry. Documented in CLAUDE.md, so not a defect; it is a commercial expectation to confirm.
- **Red-team: no upper bound on password length (informational) -> agree, Low, pre-existing.** The unthrottled admin-secret guess on the new route -> agree, theoretical, same as `/system/create-operator`.
- **QA: 3023 passed, 2 skipped. Code-reviewer: 2999 passed, `test_entrypoint.py` excluded (BLOCKED, `rm` shim in its container).** The two counts differ because of that exclusion, not a regression. I did not run the suite.

## What the team missed
Nothing new. Nobody tried `/system/grant-trial` against the usual lifecycle questions: can the same email later be used for a second org (refused), and does a granted trial MLRO still hit `mfa_lock_session` (compliance says yes, I did not re-run).

## Regression sweep (my scripts, on f3c8227)
- `dob_penalty_matrix.py`: DB1 still open. Month/day typo scores 0.75 (silent); year off by 1, off by 20 and a completely different date all score 0.85 (alert).
- `country_code_vs_name.py`: CS-27 fix holds; "IN" vs "India" scores 1.00.
- `csrf_scan.py`: 22 files, 67 state-changing routes, 5 without a CSRF check in the body (unchanged; the new route is under bearer auth).

## Open at Medium or above (unchanged)
DB1/CS-28 (High), CS-27 look-back, SO1, RL1, MA1/LM1, RP1 plus the gender rewrite, SS5, CR1, TD1, TX1, CL1, N3c, QU1, ED1, ED2, PC1b, CS-13, CS-14, 3.1, RT1.

## BLOCKED / not checked
- GitHub PR list (no MCP access); relied on `git log` and role reports.
- F-1 race not reproduced (needs concurrent writers).
- Full suite not run by me.

## Files and commit
`reports/daily/2026-11-24/skeptic.md` on `routine/2026-11-24-skeptic`.

# code-reviewer daily report, 2026-11-02

**Instructions I ran under:** scheduled routine "groAML daily: code-reviewer" (fired 2026-11-02 00:46 UTC). Review current origin/master, the changes since the SHA in my previous report, and PRs opened or updated since. Standing rules: no production access, no `/system/*` calls, no secrets, local test data only, never push to master, stop after delivering.

**Headline: GREEN.** origin/master moved from `11a3527ef94126da09860257e583a2e46e87e958` to `e8ddf262a73c1f0fda99a174871d879e35fcbbcf` (9 PRs, #443-#451, 79 files, +4.3k/-218); the suite is green and all four findings from yesterday's report are fixed, with no new defect found in what I reviewed.

**What I did (evidence):**
- `git ls-remote origin refs/heads/master` returned `e8ddf26…`; `git log 11a3527..origin/master` lists #443 email self-unlock, #444 retention and purge guards, #445 alert/freeze lifecycle, #446 residual fixes, #447 UBO/goAML/tenant-scan guards, #448 product polish, #449 hygiene, #450 `/admin/ops`, #451 test fix after #447 left master red. All merged 2026-11-01.
- Full suite on `e8ddf26` in a throwaway worktree (Linux, `.venv`): **2651 passed, 2 skipped**, 23 min 20 s (previous baseline 2499 passed, 2 skipped). `hypothesis` (a new test dependency added by #447) was missing from my venv, so the first run stopped at a collection error in `tests/test_ubo_property.py`; I installed it into the scratchpad only (not the shared venv) and reran.
- Re-probed yesterday's three crash findings with the same inputs, on `e8ddf26`: webhook non-ASCII signature now returns 400; non-ASCII TOTP code returns False; non-ASCII CSRF value returns False.
- Read the `amlkit/` diffs of #446, #443, #444, #445, #447 and #450 in full.

**Resolved since last report (all by #446, probed):**
- CR-24: the Stripe signature compare now uses bytes (400).
- CR-25: `auth.safe_equals` fixes `mfa_verify`.
- CR-26: `csrf_valid` uses `safe_equals`.
- CR-27: subscription events older than the newest applied one are stored but not applied (`organizations.billing_last_event_created`).

**Findings:**
- CR-29 (INFO, CONFIRMED): #445 changes alert semantics. A decided alert (`true_positive` and `escalated` as well as `false_positive`) is now a standing record: a re-screen raises no new alert unless the list entry changed (`list_updated`) or the customer's name, date of birth, nationality or ID number changed (`subject_changed`, via `alerts.subject_hash`). Previously a confirmed match re-alerted after every list update. The freeze obligation is untouched, but compliance should sign off on the queue behaviour.
- CR-30 (INFO, PLAUSIBLE): `GET /unlock/{token}` (#443) changes state on a GET, so a mail-scanner prefetch consumes the single-use token. The effect is only that the account is unlocked, so it is harmless. The unlock email is sent synchronously on the transition into a lock (the 5th wrong password), so that one response is slower for existing accounts than for unknown emails: a possible account-enumeration timing signal. I did not measure it (no SMTP locally). The login rate limit applies.
- CR-31 (INFO, CONFIRMED): `hypothesis>=6.100` was added to `requirements.txt`, the production dependency list, though only tests use it. The lock pins 6.170.14.
- CR-32 (INFO, PLAUSIBLE): `/admin/ops` (#450) shows every org's MLRO the shared dataset freshness and a truncated `litestream status` string (300 chars). It is not tenant data and the figures are org-scoped, but the replica position is infrastructure detail visible to any org's MLRO in a shared deployment.
- Design checks that passed: the unlock token is hashed, single-use via `used_at IS NULL`, 30 min, clears the password lock only and not the MFA lock, and is audited with `org_id`. Purge guards refuse customers with an unresolved freeze, an unfinalised report or an open alert, and `recompute_retention` only extends dates. The ownership validator rejects NaN/inf/negative values and totals over 100.
- Carried, unchanged: CR-4 (MEDIUM, unmerged #417; not re-checked), CR-13 and CR-18 (LOW; not re-checked), CR-1b (LOW, fallback now logged), CR-2/3/5/17, CR-19 to CR-23, CR-28 (INFO).

**BLOCKED / not checked:**
- Nothing blocked.
- Not reviewed in depth: #448 product polish (first-run checklist, `/changelog`, palette), #449 hygiene (PDF page-size guard, `seed_org` fixture, findings register), the Cloud Monitoring scripts under `scripts/monitoring/`, and the `source-canary.yml` change.
- The new `reports/findings.csv` was not audited.
- I did not re-measure the `alert_queue` slowdown (CR-13).
- CI status for `e8ddf26` was not looked up (standing rule: no CI re-checks).
- The mail path was not exercised (no SMTP).

**Files / commits:** `reports/daily/2026-11-02/code-reviewer.md`; commit SHA in the final reply.

# code-reviewer daily report, 2026-11-03

**Instructions I ran under:** scheduled routine "groAML daily: code-reviewer" (fired 2026-11-03 00:46 UTC). Review current origin/master, the changes since the SHA in my previous report, and PRs opened or updated since. Standing rules: no production access, no `/system/*` calls, no secrets, local test data only, never push to master, stop after delivering.

**Headline: GREEN.** origin/master moved from `e8ddf262a73c1f0fda99a174871d879e35fcbbcf` to `938050fda10fe248b2cc327ea5d0770b5cb08f01` (5 PRs, #452-#456, 84 files, +9.3k/-4.8k); the 5,046-line `api/app.py` split (#456) is behaviourally identical to its parent, the suite is green, and I found no defect.

**What I did (evidence):**
- `git ls-remote origin refs/heads/master` returned `938050f…`; `git log e8ddf26..origin/master` lists #452 name-screening residuals, #453 identity/auth residuals, #454 obligation wording, two-step unlock and dev requirements, #455 UBO structure guard, #456 router split. All merged 2026-11-02.
- Full suite on `938050f` in a throwaway worktree (Linux, `.venv`, `hypothesis` from the scratchpad): **2810 passed, 2 skipped**, 17 min 16 s (previous baseline 2651 passed, 2 skipped). A container restart killed my first run at about 90%, so this is a clean second run.
- **#456 "pure move", checked three ways** (independent of the PR's own snapshot tests):
  1. Imported the old (`e8ddf26`) and new app in separate worktrees and fingerprinted every route (path, methods, endpoint, dependency chain, form/query/header/cookie/body params, status, response class, rate limits, include-level dependencies). 198 old routes, 199 new routes; **0 changed fields**. The only differences are the intended unlock change from #454 (old `GET /unlock/{token}`; new `GET` confirm page plus `POST`). The middleware stack, exception handlers, startup/shutdown hooks, lifespan, Jinja globals and filters are identical. No param-before-static route shadowing was introduced.
  2. AST-compared all 162 top-level functions of the old `app.py` against the new `app.py`, `helpers.py` and `routers/*.py` after stripping decorators: none missing; 68 bodies differ. Almost all are only relative-import depth (`..x` to `...x`). The rest map to other PRs in the range: SSO password-lock refusal and identity-reuse block (#453), two-step unlock (#454), raw replica on the super-admin console, and `mail_configured` in the admin view (#454).
  3. The decorator comparison after `app`/`router` renaming found one change, the unlock route.
- Read in full: the `amlkit/` diffs of #452 (scorer, confusables, `arabic.py`), #453 (`auth.py`, `manager.py`, `review.py`, `db.py`), #455 (UBO structure guard) and the two-step unlock and `ops.system_status` code from #454.

**Resolved since last report (all confirmed in code or tests):**
- CR-30 (INFO): unlock is now two-step. `GET /unlock/{token}` only shows a confirmation page and does not consume the token. `POST` requires CSRF and shares one per-IP rate bucket with the GET.
- CR-31 (INFO): `hypothesis` and `pytest` moved to `requirements-dev.txt`. The Dockerfile installs `requirements.txt` only, and a new test pins that. `requirements.lock` still lists them but is not used by the image.
- CR-32 (INFO): tenant `/admin/ops` now gets only a derived replica state. The raw `litestream status` string is shown on the super-admin console only.
- CR-1b (LOW): `confirm_disposition` now compares operator ids only and refuses a confirm call without one. A legacy proposal with NULL `operator_id` counts as proposed-by-unknown.

**Findings (INFO unless marked):**
- CR-33 (PLAUSIBLE): residual four-eyes window. A pending review proposed before #426 (about 2026-10-06) has a NULL `operator_id`, so its original proposer could confirm it. `scripts/backfill_proposal_operator.py` exists to close this and must be run on production; I did not run it. Check with `scripts/check_legacy_proposals.py` first.
- CR-34 (CONFIRMED): when mail is not configured, the 8th wrong password for a verified account returns a specific "locked ... email could not be sent" message (`AuthLockedMailUndeliverable`) instead of the generic one. That confirms the account exists in deployments without SMTP. It is documented as a deliberate tradeoff and is inert when SMTP is set.
- CR-35 (PLAUSIBLE): homoglyph folding (#452) folds a token that is all look-alike letters into Latin, so a genuine Cyrillic or Greek name made only of mappable letters becomes Latin gibberish. The effect is extra candidates (false positives), never a missed match. `blocking_keys` also adds adjacent-token concatenations, which increases candidate counts slightly. Not measured.
- CR-36 (INFO): the new `reports/findings.csv` and the three snapshot JSON files (`routes_master.json`, `route_limits_master.json`, `scorer_snapshot_master.json`) pin current behaviour; they will need regenerating on intentional changes.
- Carried, unchanged: CR-4 (MEDIUM, unmerged #417; not re-checked), CR-13 and CR-18 (LOW; not re-checked), CR-2/3/5/17, CR-19 to CR-23, CR-28, CR-29 (INFO).

**BLOCKED / not checked:**
- Nothing blocked.
- Not reviewed in depth: #454's obligation-wording and `operator-name` hardening changes beyond the unlock/ops code, #455's property tests, the `scorer_snapshot` content, and `reports/findings.csv`.
- I did not re-measure `alert_queue` performance (CR-13) or candidate-count growth from the new blocking keys.
- CI status for `938050f` was not looked up (standing rule: no CI re-checks).
- The mail path and UAE PASS flows were not exercised.

**Files / commits:** `reports/daily/2026-11-03/code-reviewer.md`; commit SHA in the final reply.

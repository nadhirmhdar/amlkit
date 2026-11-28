# code-reviewer daily report, 2026-11-08

**Instructions I ran under:** scheduled routine "groAML daily: code-reviewer" (fired 2026-11-08 00:45 UTC). Review current origin/master, the changes since the SHA in my previous report, and PRs opened or updated since. Standing rules: no production access, no `/system/*` calls, no secrets, local test data only, never push to master, stop after delivering.

**Headline: AMBER.** origin/master moved from `6560fb021f6ea2cadefcd6e60d67ee274d871e73` to `9219e2623b3a3ba7e73a20e44c703ab80df7e900` (3 PRs, #460-#462); the suite is green and four of my open findings are fixed, but the new open sign-up still lets a caller tell registered emails from new ones by response time.

**What I did (evidence):**
- `git ls-remote origin refs/heads/master` returned `9219e26…`; `git log 6560fb0..origin/master` lists #460 SEO round 2 (HEAD on public pages, static JSON-LD, gzip), #461 WP-30 (reason codes must fit the disposition; sanctions refresh every 4 hours), #462 WP-29 launch blockers (sign-up enumeration, honest email-failure page, accurate public claims, unpaid-org scans, PR secret gating). All merged 2026-11-07. 29 files, +788/-83.
- Full suite on `9219e26` in a throwaway worktree (Linux, scratchpad venv, Python 3.13): **2945 passed, 2 skipped**, 16 min 3 s (previous baseline 2860 passed, 2 skipped).
- Read the full `amlkit/` diff and the workflow diff.
- Probed with a dummy `STRIPE_SECRET_KEY`, throwaway DB, no network:
  - Open sign-up with a new email, an existing email plus existing firm name, and a second new email: all return HTTP 200 and the bodies are identical once the address is normalised. The existing-email request creates no organisation or operator (2 orgs, 2 operators afterwards).
  - Latency over 12 pairs: median **113.9 ms for a new email vs 10.0 ms for an existing one**.
  - The six public pages now added to the compressible list (`/`, `/aml-law`, `/pricing`, `/privacy`, `/about`, `/blog`) contain no `csrf_token` field and not the value of the `amlkit_csrf` cookie, so compressing them is still safe.
  - `HEAD` on `/verify-email`, `/unlock/x` and `/setup` returns 405, so the HEAD allow-list does not trigger token-consuming GET handlers.

**Resolved since last report:**
- CR-40 (LOW): `EU_FSF_TOKEN` is no longer passed on `pull_request` runs (`github.event_name != 'pull_request' && secrets.EU_FSF_TOKEN || ''`); the new test pins it.
- CR-38 (PLAUSIBLE, partly): sign-up no longer reveals whether an email or a firm name is already in use (same page; duplicate names get a random slug suffix); the verification link is never shown on screen in open mode. See CR-41 for what remains.
- CR-37 (INFO, partly): the OCR scan routes (web and mobile) now return 402 for an unpaid `pending_payment` org via `check_scan_allowed`. Ad-hoc `/screen` stays open by design.
- Reason codes now have to fit the disposition (`ALLOWED_REASON_CODES`; `insufficient_data` can never close an alert), and `status` is validated against the same four dispositions first, so there is no KeyError path.

**Findings:**
- CR-41 (LOW, CONFIRMED, measured): open sign-up is still an account-enumeration oracle by timing. The existing-email path returns before the password is hashed, about 10 ms against about 114 ms for a new sign-up. In production both paths send mail synchronously, which adds noise, but the roughly 100 ms gap can still be averaged out at the 5/min per-IP limit. Fix: always run the password hash (or a dummy hash) before branching, or send the mail in a background task so neither path waits on SMTP.
- CR-42 (PLAUSIBLE, residual of CR-38): both sign-up paths still send a mail to whatever address was typed (a verification link, or a "someone tried to register" notice), so email-bombing a third party remains possible at 5/min per IP. The mobile `POST /api/v1/auth/register-organization` is still invite-gated.
- CR-43 (INFO): refresh cadence is now every 4 hours in the Cloud Scheduler job, so `rescreen_all` runs six times a day instead of 24 h / 20 h; I did not measure the extra load on the single SQLite writer.
- Carried, unchanged: CR-4 (MEDIUM, unmerged #417; not re-checked), CR-13 and CR-18 (LOW; not re-checked), CR-2/3/5/17, CR-19 to CR-23, CR-28, CR-29, CR-33 to CR-37, CR-39 (INFO).

**BLOCKED / not checked:**
- Nothing blocked.
- Not reviewed in depth: the template and copy changes (`landing`, `aml_law`, `register_organization`, the "accurate public claims" wording), the static JSON-LD move (`jsonld.js` deleted), and `tests/test_wp29_launch_blockers.py` beyond a skim.
- I did not run the scheduler change (it is a workflow edit) or measure the effect of the 4-hourly refresh.
- I did not re-measure `alert_queue` performance (CR-13).
- CI status for `9219e26` was not looked up (standing rule: no CI re-checks).
- The mail path was not exercised against SMTP; the timing result is the no-mail case.

**Files / commits:** `reports/daily/2026-11-08/code-reviewer.md`; commit SHA in the final reply.

# code-reviewer — daily run 2026-10-07

## Instructions I ran under

Standing role (Nadhir, unchanged): Senior Software Architect & Code Auditor (Agent 3) for `nadhirmhdar/amlkit`. Audit the Python implementation, database integrity, migrations, concurrency and tenant isolation; separate real defects from harmless comments. Powers: read the checkout, run tests locally, push only to my designated branch and to `routine/<DATE>-code-reviewer`, never master (a push to master deploys to production). Rules that win over everything else: no production access, no `/system/*` calls, no secrets, local test data only, additive-only (no edits to routes, schema, queries or business logic; fixes go in as proposed diffs marked HELD), run autonomously, record anything blocked as BLOCKED, push the report and stop. Today's trigger ("groAML daily: code-reviewer") set scope and format. Nothing changed because of dreamon today.

Disclosure on `/system/*`: I called no `/system/*` route. The repo's own tests exercise those routes in-process through FastAPI's `TestClient` with dummy secrets and no network; I ran that suite locally, as on earlier days.

## Headline

**AMBER.** The four-eyes bypass (CR-1) is fixed on every live path in master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`; what stays open is that a name nobody could screen (Cyrillic, CJK) is still stored as a clean screening on onboarding, UBO add and rescreen (CR-12).

## What I did, with evidence

- `git ls-remote origin refs/heads/master` → `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (previous report: `b7eeb2f32c6f3eae4f29420477189aaf11ea1d02`). Four merges since: #422 `c7d0f42`, #421 `8750f74`, #404 `1d1ef39`, #426 `0129848`. 26 files, +1028/−155.
- Read the code diff of #426 (the four-eyes fix) in full, the conflict resolution of #422 and #421 as merged, and the #404 test change; compared the final heads of #422 (`a1ffa67`) and #404 (`4c97902`) with what I reviewed before.
- Full suite on master `0129848` in a throwaway worktree with the repo venv: `2170 passed, 3 skipped, 53 warnings in 830.63s`. Master CI for the same SHA (GitHub Actions push runs): Tests, CodeQL Advanced and Source canary all `success`.
- PRs opened or updated since the last report: #426 (new, merged), #422 (updated head, merged), #404 (updated head, merged), #421 (merged). The only reviewable open PRs are #417 (unchanged, head `83a4567`) and #411 (mine); #410 and #412–#415 are drafts unchanged since 2026-10-04 and were not re-reviewed.
- Probes on master `0129848` (script in the scratchpad, run against throwaway SQLite files):

```
A. live path: both sides carry operator_id=1, renamed          -> refused
B. both ids, a different operator (id 2) confirms              -> ACCEPTED (false_positive)
C. proposal staged BEFORE migration (id NULL), renamed         -> ACCEPTED (false_positive)
D. proposal has id, confirm call omits id, renamed             -> ACCEPTED (false_positive)
alert_reviews rows (action, operator, operator_id): [('propose', 'Alice', 1), ('confirm', 'Bob', None)]
```

- #417 merged into a throwaway copy of current master (merges cleanly): `tests/test_a11y_review.py`, `test_loading_glass.py`, `test_p84_mobile_accessibility.py`, `test_login_page.py`, `test_csp_no_inline_scripts.py` → `42 passed`.
- Secrets/production scan over every added line of `b7eeb2f..0129848`: 0 matches.

## Findings

| ID | Sev | Status | Where | Finding |
|---|---|---|---|---|
| CR-1 | HIGH → closed | CONFIRMED fixed (live paths) | `amlkit/cases/review.py:394-398` (fix), call sites `amlkit/api/app.py:2606,2660,2683`, `amlkit/api/mobile.py:1302,1327`, `review.py:517` | #426 anchors "different operator" on `alert_reviews.operator_id` (new column, `db.py` `_MIGRATIONS`). Probe A is refused and probe B is accepted. Every non-test caller of `propose_disposition`, `confirm_disposition` and `bulk_dismiss_alerts` now passes `operator_id=session.operator_id` (found with `git grep`). |
| CR-1b | LOW | CONFIRMED | `review.py:394-397` | The fix fails open when either side has no id: it falls back to comparing names. Probe C: a proposal staged before the migration (no id) is still bypassable by rename and confirm. Probe D: a confirm call that omits the id is accepted after a rename. No live caller omits the id, so D is a future-caller hazard; C is a one-off window for proposals already pending at deploy. Also the `confirm` row is stored without an id (`review.py:422` insert unchanged: `('confirm', 'Bob', None)`), so who confirmed rests on a name. Proposed fix (HELD): at migration, backfill `operator_id` on `pending_review` proposals by `(org_id, operator)` where the name is unique; make `confirm_disposition` refuse when the proposal has an id and the caller gave none; store the confirmer's id. |
| CR-12 | MEDIUM | CONFIRMED, open | `amlkit/match/engine.py:292` (flag set), consumers still only `amlkit/api/mobile.py:538` and `amlkit/web/templates/screen.html:76` | Unchanged since 2026-10-06: `git grep unscreenable` shows no new consumer. Onboarding, UBO add and `rescreen_all` still store a name with letters but no blocking keys as a screening with 0 candidates, 0 hits, no marker, risk `low`. Fix proposal unchanged (HELD): persist the flag, notify at onboarding/UBO add, count unscreenables in `rescreen_all`. |
| CR-4 | MEDIUM | CONFIRMED, open (PR #417, not on master) | PR #417 `screen.html:40`, `bg-submit.js` `verdictFor` | Head still `83a4567`. On a merge into current master, `李小龍` gives `data-verdict: ('clear', '0')` while the page shows "Not screened", so the glass would say "No match." Merge is clean and 42 tests pass, so nothing blocks the merge except this. Fix HELD, in #417. |
| CR-13 | LOW | CONFIRMED benchmark, now on master | `amlkit/queries.py:537-547` (`alert_queue`, merged #421) | The category-first rewrite ranks every matching alert in Python before paging. Numbers from my 2026-10-06 benchmark on the PR tree apply unchanged: 2,000 alerts 6.8 → 22.8 ms; 20,000 alerts 9.9 → 246.0 ms (`open`, limit 200), `dashboard()` 156.6 → 392.9 ms. Fine at DNFBP scale today. |
| CR-14 | LOW | CONFIRMED behaviour, PLAUSIBLE reachability, unchanged | `amlkit/api/app.py:3935,3999,4038,4085` | The four `/system/*` bearer checks still call `secrets.compare_digest` on `str`; a non-ASCII header raises `TypeError` (500 instead of 401). The invite-code check at `app.py:1169` already does it correctly with `.encode()`. Fix HELD: encode both sides. |
| CR-18 | LOW | CONFIRMED | `tests/test_a11y_review.py` `test_type_scale_is_five_steps_and_buttons_have_three_sizes` (from #404) | The new test calls `read_text()` with no encoding on the CSS and every template. With a non-UTF-8 default encoding it fails: `PYTHONCOERCECLOCALE=0 PYTHONUTF8=0 LC_ALL=C` → `UnicodeDecodeError: 'ascii' codec can't decode byte 0xe2 in position 1104`; in the normal environment it passes. That is the failure class #423 fixed for the Windows dev machine and `.claude/skills/run-amlkit-tests/SKILL.md` lists, so it will reappear there. Fix HELD: pass `encoding="utf-8"`. |
| CR-17 | INFO | CONFIRMED | `CLEANUP_POLICY.md` line 154 | The policy still says 46 of 72 `_MIGRATIONS` entries add columns missing from `SCHEMA`; master now measures 49 of 75 (`:memory:` load of `db.SCHEMA` against `_MIGRATIONS`). |
| CR-15 | INFO | resolved | #422 as merged (`amlkit/cases/manager.py:608,618`) | The conflict with #423 was resolved correctly: `purge_expired` uses `utc_today()` and `_inside_policy_window`, and the statutory constant is gone. One local-date use remains in `manager.py:2162` (`today = date.today()`, document expiry), outside the retention logic. |
| CR-2 | LOW | PLAUSIBLE, carried | `amlkit/api/app.py:3963` | `sync_replica(timeout=30)` still sits in `system_refresh`'s `finally`. |
| CR-3 | LOW | PLAUSIBLE, carried | `repro/make_seed.py:76` on #412 head `15d40a1` (unchanged) | Seed passes `direction="in"`. |
| CR-5 | LOW | PLAUSIBLE, carried | PR #417 `bg-submit.js:40,204` | No `inert` or focus trap behind the glass; JS unchanged. |

Reviewed, no defect found: #422 retention logic (migration plus `_inside_policy_window` as merged; the 71 own tests I ran on 2026-10-06 are part of today's suite), #421 category and PEP/other obligation wording logic (wording is flagged in the PR for adviser sign-off), #404's CSS and template changes, #426's route changes and migration.

## BLOCKED / not checked

- BLOCKED: SendMessage to dreamon is not possible from this cloud session; the branch file and this reply are the channel.
- Not checked: production environment values; #404's visual result in a browser; legal accuracy of the PEP/other obligation wording (#421) and the retention copy (#422); whether proposals already pending in production at deploy time have ids (that is probe C's window); #410–#415 (unchanged drafts).

## Files created

- `reports/daily/2026-10-07/code-reviewer.md` on `routine/2026-10-07-code-reviewer` (report-only commit on master `0129848`) and on `claude/tender-ritchie-mq2xh4`; commit SHAs in the final reply.
- No application code, tests or schema changed. Scratch probes and throwaway worktrees lived in the session scratchpad and are removed.

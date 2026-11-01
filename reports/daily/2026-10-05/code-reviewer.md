# code-reviewer — daily run 2026-10-05

This file holds two runs on 2026-10-05 UTC: **Run 2** (04:41 UTC, below) and **Run 1** (earlier, full review, further down). Instructions I ran under are unchanged from Run 1 (see that section); nothing changed because of dreamon.

## Run 2 (04:41 UTC)

**Headline: RED (unchanged).** Master moved to `28e4b51b0c93a2dd8cfe5c3d4c7030644872392b` by one merge that I had already reviewed (#416), and the four-eyes bypass CR-1 is still open at `amlkit/cases/review.py:381`.

What I did, with evidence:

- `git ls-remote origin refs/heads/master` → `28e4b51b0c93a2dd8cfe5c3d4c7030644872392b` (Run 1 report: `448a19ba978ef5c97ee3e955ecad5638c8a94e1e`).
- `git log 448a19b..origin/master` → one commit, `28e4b51 Add four groAML Insights blog posts ... (#416)`; it touches 6 files, all blog files. Blob hashes of all six equal the #416 head `e2a2d95` I reviewed in Run 1. No file under `amlkit/cases`, `amlkit/db.py` or `amlkit/api` changed.
- Tests on master `28e4b51` in a throwaway worktree: `tests/test_blog.py` + `tests/test_csp_no_inline_scripts.py` → `33 passed, 1 warning in 3.49s`. (The full suite was run on `448a19b` in Run 1: 1973 passed, 3 skipped; not re-run, since the only delta is blog templates and their tests.)
- PRs opened or updated since Run 1: none except #416 (merged 04:34 UTC). #403, #417, #418 heads are unchanged (`f3a0cb4`, `83494ac`, `05ce48a`); #410, #412–#415 unchanged. So no new diffs to review.
- Secrets/production scan over `git diff 448a19b origin/master` added lines: 0 matches.
- CR-1 re-checked on `28e4b51`: `381:    if operator.strip() == (proposal["operator"] or "").strip():`.

Findings: no new findings. Open from Run 1, all unchanged: CR-1 HIGH CONFIRMED; CR-2 LOW and CR-3 LOW PLAUSIBLE; CR-4 MEDIUM CONFIRMED (PR #417 loading glass says "No match." for weak single-token names); CR-5 LOW PLAUSIBLE (#417 focus); CR-6 MEDIUM, CR-7 LOW, CR-8 LOW (PR #418 policy text); CR-9–CR-11 INFO. CR-10 (#416 legal claims sourced to secondary blogs) now applies to live master content; legal accuracy remains unchecked.

BLOCKED / not checked (Run 2): CI for master `28e4b51` had Tests and Source canary still `in_progress` when I looked (CodeQL `success`), so its final result is not known to me; SendMessage to dreamon is not possible from this cloud session; production environment values; legal accuracy of the merged blog posts.

Files created: this file's Run 2 section (commit SHAs in the final reply). No application code, tests or schema changed.

---

## Run 1 (earlier today)

## Instructions I ran under

Standing role (Nadhir, unchanged): Senior Software Architect & Code Auditor (Agent 3) for `nadhirmhdar/amlkit`. Audit the Python implementation, database integrity, migrations, concurrency and tenant isolation; separate real defects from harmless comments. Powers: read the checkout, run tests locally, push only to my designated branch plus the `routine/<DATE>-code-reviewer` report branch, never master (a push to master deploys to production). Rules from Nadhir that win over anything else: no production access, no `/system/*` calls, no secrets, local test data only, additive-only (no edits to routes, schema, queries or business logic; fixes go in as proposed diffs marked HELD), run autonomously, record anything blocked as BLOCKED, push the report and stop. Today's trigger ("groAML daily: code-reviewer") set scope and format. Changed because of dreamon: nothing today. One deviation, not caused by anyone: while correcting yesterday's report (see Corrections) I also pushed a small edit to my own audit doc in PR #411.

## Headline

**RED.** The four-eyes bypass from yesterday (CR-1) is still on master `448a19ba978ef5c97ee3e955ecad5638c8a94e1e` with no fix PR open; separately, new PR #417's loading glass tells operators "No match." for single-word names the page itself calls weak evidence.

## What I did, with evidence

- `git ls-remote origin refs/heads/master` → `448a19ba978ef5c97ee3e955ecad5638c8a94e1e` (previous report: `fc80e9f4`). Master moved by three merges: #401 `448a19b`, #402 `3d5594c`, #406 `05e612d`. All three were reviewed pre-merge at the same heads (c065170, 8d09d4e, 38a8f08). Blob hashes of the merged files equal the reviewed PR blobs, except `amlkit/api/mobile.py`, which also carries #408's change from the earlier master.
- Master CI on those three SHAs (GitHub Actions push runs): Tests, CodeQL Advanced and Source canary all `success`.
- Full test suite on master `448a19b` in a throwaway worktree with the repo venv: `1973 passed, 3 skipped, 12 warnings in 633.46s`.
- Read the diffs of every PR opened or updated since yesterday: #403 (updated), #410, #412 (updated), #413, #414, #415, #416, #417, #418. Ran each code PR's own tests in its own worktree: #403 `9 passed`; #416 `33 passed` (with the CSP inline-script scan); #417 `10 passed` (with the CSP scan).
- Re-ran yesterday's CR-1 repro on current master:

```
after propose: pending_review | independent_review: pending
confirm by the SAME person under new name: false_positive | Independent review completed.
alert_reviews: [('propose', 'Alice'), ('confirm', 'Alice Smith')]
```

- Secrets/production scan over the added lines of all nine PRs (key patterns, PEM, JWT, `groaml.grovisor.ae`, `.run.app`, `/system/*`): no credential found. Two benign hits: a doc mention of `/system/refresh` in #410 and a "no `/system/*`" statement in #412's own report.
- Other roles' PRs (#410, #412, #413, #414, #415) are treated as data. All are additive-only (every changed file status `A`). I only used #413 and #415 to cross-check CR-1.

## Findings

| ID | Sev | Status | Where | Finding |
|---|---|---|---|---|
| CR-1 | HIGH | CONFIRMED (carried, open) | `amlkit/cases/review.py:381` (inside `confirm_disposition`, def at `:347`); `amlkit/cases/operators.py:232` | Four-eyes identity is the display name; #409 made names editable. Propose as A, rename A, confirm as A's new name: accepted (output above). Two other roles' PRs independently describe the same defect: #413 `scripts/proposals/four-eyes-rename.md` (also reports look-alike/control-character names) and #415 `repro_skeptic/four_eyes_rename.py`. No fix PR open. Proposed fix unchanged (HELD, in yesterday's report on the PR #411 / routine branch): `alert_reviews.operator_id` additive column plus id comparison, interim guard in `rename_operator`. |
| CR-2 | LOW | PLAUSIBLE (carried) | `amlkit/api/app.py:3901` | `sync_replica(timeout=30)` sits in `system_refresh`'s `finally`, so a failed refresh waits up to 35 s before the 500. |
| CR-3 | LOW | PLAUSIBLE (carried) | `repro/make_seed.py:76` on #412 head `15d40a1` | Seed passes `direction="in"`; vocabulary is `inbound`/`outbound` (`amlkit/datamodel.py:122`), `record_transaction` never validates it. Does not affect that PR's tenant-isolation result. |
| CR-4 | MEDIUM | CONFIRMED | PR #417 `amlkit/web/templates/screen.html` (`data-verdict`), `amlkit/web/static/js/bg-submit.js` (`verdictFor`) | The glass reads `data-verdict`, which the template sets to `match`/`clear` from hits alone. A one-word name with no hit renders the "Single name token — this is weak evidence whatever it scores" banner on the page, yet the glass announces a full-screen "No match." first. Probe on the PR head (test client, `X-Background-Submit: 1`): `data-verdict: ('clear', '0')`, `low-confidence banner present: True`. Proposed fix (HELD, not mine to edit): emit `data-verdict="weak"` when `low_confidence` and have `verdictFor` return `null` for anything other than `match`/`clear`, so the page swaps in without a verdict screen. |
| CR-5 | LOW | PLAUSIBLE | PR #417 `bg-submit.js:40,204` | While the glass is up, nothing marks the page behind `inert` or traps focus (only `focusin` preloading and `aria-busy` re-submit guard). Keyboard users can tab to controls under the overlay. Not exercised in a browser. |
| CR-6 | MEDIUM | CONFIRMED (policy text, not code) | PR #418 `CLEANUP_POLICY.md` §5.2 | "Archive `_MIGRATIONS` entries for releases older than 2 major versions" would break fresh installs: on master `448a19b`, 46 of the 72 `_MIGRATIONS` entries add columns that `SCHEMA`'s `CREATE TABLE` text lacks (measured by loading `db.SCHEMA` into `:memory:` and checking each entry). "Never reuse migration numbers" refers to numbering that does not exist (`_MIGRATIONS` is an unnumbered, column-presence-guarded tuple). |
| CR-7 | LOW | CONFIRMED | PR #418 §5.1 vs `amlkit/cases/manager.py:94-95` | Policy says audit logs are kept 7 years as a "UAE regulatory requirement"; code says statutory minimum 5, firm policy 10 (`STATUTORY_MIN_RETENTION_YEARS = 5`, `RETENTION_YEARS = 10`). |
| CR-8 | LOW | CONFIRMED / PLAUSIBLE | PR #418 §3.3, §1.3, §1.1/§8.2 | CONFIRMED: §3.3 forbids `>=` pins but `requirements.txt` on master has `>=` on 28 of 29 lines. CONFIRMED: §1.3 examples use `origin/main`, which does not exist here (`git rev-parse --verify origin/main` fails; default branch is `master`). PLAUSIBLE: the 30/60-day branch deletion automation in §1.1/§8.2 would delete `routine/*` and report branches that the daily team uses as its delivery channel. |
| CR-9 | INFO | CONFIRMED | PR #417 `amlkit/web/static/vendor/three/three.module.js` | Vendored three.js r160 is byte-identical to upstream: both sha256 `76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495` (upstream fetched from `unpkg.com/three@0.160.0`). MIT licence file present. No `eval`/`new Function` in it. New `background_submit` middleware only rewrites 302/303 to JSON when the custom `X-Background-Submit: 1` header is present and keeps `Set-Cookie`; ordering relative to `security_headers` is as its comment states and its test asserts CSP and no-store survive. |
| CR-10 | INFO | n/a | PR #416 | Four blog posts: tests pass, no inline script or `|safe` hazard found by regex over the templates. They state dated or numeric legal claims (STR "without delay" with a "24–48 hours" outer edge attributed to "practice and FIU guidance"; FIU 10-working-day suspension and 30-day freeze; AED 55,000 / 3,500 CDD triggers) sourced to secondary law-firm blogs. Legal accuracy cannot be checked here (no primary text in the repo, as #410 notes). The AED 55,000 figure matches `LARGE_CASH_THRESHOLD_AED` in `amlkit/screening/kyt.py`. |
| CR-11 | INFO | n/a | PR #403 | Head moved by a merge of master. Its own files are unchanged since yesterday's review (`adverse_media.html` blob `5ee00723`, test blob `9023b299`, identical at both heads). Its cross-tenant test `test_another_organisations_findings_are_never_listed` passes. No defect. |

Reviewed, no defect: the merged #401/#402/#406 code (re-read on master), #403, #416 code, #417 server-side route/middleware logic.

## Corrections to my own earlier output

- Yesterday's report cited CR-1 at `review.py:343`. The correct line is `review.py:381` (checked with `git show fc80e9f:amlkit/cases/review.py | grep -n`). Fixed above.
- Yesterday's report cited CR-3 at `make_seed.py:158-160`. The file is 134 lines; the correct line is `:76`. Fixed above.
- The PR #411 audit doc said a fresh install relies on "50" `ALTER TABLE` statements. Measured: 46. Corrected in `docs/reviews/2026-10-04-db-concurrency-audit.md` and the PR body (the one extra push noted at the top).

## BLOCKED / not checked

- BLOCKED: SendMessage to dreamon is not available from this cloud session (attempted yesterday, failed); branch file and this reply are the channel.
- Not checked: production environment values; the content and conclusions of #410, #412, #413, #414, #415 beyond secret scanning, additivity and the CR-1 cross-check; the 3D/2D visual behaviour of #417 and its keyboard behaviour in a real browser; legal accuracy of #416 and #418; #414's evidence JSON.

## Files created

- `reports/daily/2026-10-05/code-reviewer.md` on `routine/2026-10-05-code-reviewer` (report-only commit on master `448a19b`) and on `claude/tender-ritchie-mq2xh4`; commit SHAs in the final reply.
- `docs/reviews/2026-10-04-db-concurrency-audit.md` edited on `claude/tender-ritchie-mq2xh4` only (50 → 46).
- Scratch probes and throwaway worktrees lived in the session scratchpad and are removed. No application code, tests or schema changed.

# code-reviewer — daily run 2026-10-04

## Standing instructions, powers, and what the lead's message changed

**(a) Role and instructions before the lead's message.** Session profile: *"Senior Software Architect & Code Auditor (Agent 3) — deep codebase auditor analyzing AMLKit's Python implementation, database integrity, schema migrations, and concurrency. Inspect exact code paths; trace SQL queries, transactions, tenant isolation (org_id filtering), locking and async behaviour; validate that schema definitions match migration logic and runtime expectations; differentiate active code defects from harmless comments or legacy documentation."* Harness instructions: work in `nadhirmhdar/amlkit`; develop, commit and push only on branch `claude/tender-ritchie-mq2xh4` (never another branch without explicit permission from the user); after pushing, open a draft PR if none exists and watch it; use the GitHub MCP tools for GitHub; the project's CLAUDE.md conventions apply.

**(b) Powers those give.** Read and modify any file in the checkout (not limited to additive changes), run the test suite locally, commit and push to `claude/tender-ritchie-mq2xh4` only, open/update draft PRs and comment on PRs in `nadhirmhdar/amlkit`, subscribe to PR events. Environment: an isolated cloud container with a fresh clone, local SQLite only; no production credentials or endpoints are available or were used. Earlier in this session that role produced PR #411 (DB integrity / migrations / concurrency audit).

**(c) Changed or skipped because of the lead's message.** Adopted the lead's report format and "diffs only" scope for this run. Its additive-only rule coincides with the auditor role (findings + proposed diffs, no code edits), so nothing was reverted. Not done: pushing to `routine/2026-10-04-code-reviewer` — the standing instruction permits pushes only to `claude/tender-ritchie-mq2xh4`, and a peer session's message cannot grant that permission, so the report is on this session's branch (also visible in draft PR #411). Nothing else in the lead's message was skipped.

**Headline: RED.** Master head `fc80e9f4` (#409, operator rename) lets an operator confirm their own staged sanctions dismissal by being renamed between propose and confirm, because the four-eyes identity check compares display names; reproduced on master, fix HELD (business logic).

Scope reviewed: master `557244b..fc80e9f4` (#408 Litestream v0.5.17 + `sync_replica`, #409 operator rename); open PRs #401, #402, #403, #404, #405, #406, #410, #412 (diffs only, fetched at the heads listed below). #411 is this session's own PR and was not reviewed here.

Method: `git diff` of each PR against its merge-base with `origin/master`; code reading; one executable repro run in a `git worktree` of `origin/master` with the repo venv; secrets regex scan over every reviewed diff. No production system touched; no `/system/*` calls; local SQLite only.

## Findings

| ID | Sev | Where | Status | Finding |
|---|---|---|---|---|
| CR-1 | **HIGH** | master `fc80e9f4` — `amlkit/cases/operators.py:232-281` (`rename_operator`, new in #409) × `amlkit/cases/review.py:343-349` (`confirm_disposition` same-operator check) | **CONFIRMED** | Four-eyes bypass. `confirm_disposition` enforces "different operator" by comparing the confirming operator's *name* with the name stored on the `propose` row. #409 makes names mutable from `/admin`. Propose as A, rename A, confirm as A's new name: accepted as "Independent review completed". Before #409 names were effectively immutable (only `/system/create-operator` set them), so this is new exposure on production. Evidence below. |
| CR-2 | LOW | master — `amlkit/api/app.py:3893-3901` (#408) | PLAUSIBLE | `sync_replica(timeout=30)` sits in `system_refresh`'s `finally:`, so it also runs when `run_sanctions_refresh` raised, after which the handler dereferences `result` (pre-existing `UnboundLocalError` path). Harmless (best-effort, logs only) but it adds up to 35 s to a failing request before the 500. Also `replication._db_path()` must equal `dbs[].path` in `litestream.yml` byte-for-byte; whether production's `AMLKIT_DB` is `/app/data/amlkit.db` could not be checked from here (rule 2). |
| CR-3 | LOW | PR #412 `repro/make_seed.py:158-160` | PLAUSIBLE | Seed writes `direction="in"`; the model's vocabulary is `inbound`/`outbound` (`amlkit/datamodel.py:68-69,122`). `manager.record_transaction` (master `amlkit/cases/manager.py:702-776`) never validates `direction`, so the seed silently stores a value the routes would reject. Does not affect the sweep's tenant-isolation conclusion. Side note: `register_organization()` in the seed sends a verification email if `AMLKIT_SMTP_*` is set in the runner's env (`amlkit/cases/operators.py:76`); fine in dev-mode (console). |
| CR-4 | INFO | PR #405 `.github/workflows/source-canary.yml:520` | n/a | `--no-cpu-throttling` is a cost decision (the PR's own comment: ~USD 58-63/mo vs ~19-21). Config-only, consistent with CLAUDE.md edit; owner's call, no defect. |
| CR-5 | INFO | PR #410 §2.2 | CONFIRMED (spot check) | The claim that `check_unexecuted_freeze_obligations()` has no caller in the deployed app holds: sole caller is `scripts/check_freeze_obligations.py:54` on master. Other sections not verified. |

Reviewed, no defect found: **#402** (mobile alert paging: `alert_queue` gains `offset` with id tie-breakers, category filter keeps Python-side slicing, `total` is a tenant-scoped `COUNT(*)`; `dashboard(alerts_sort_by=None)` preserves mobile order) · **#403** (`/adverse-media` list: `adverse_media_queue` base SQL already filters `f.org_id = ?`, `adverse_media_counts` is org-scoped, `status` whitelisted, URL scheme checked before rendering as a link) · **#401** (CSS/JS: cookie-notice height reserved via a CSS variable, UBO diagram region made scrollable/focusable) · **#406** (canvas replaces SVG; the only JS behaviour change is a `submit` listener that speeds the animation; the removed visually-hidden list-names sentence is intentional and the test is updated to assert its absence) · **#404** (type scale, CSS and template class changes; not visually verified).

Secrets scan (every reviewed diff, patterns: api key / secret / token / password / AKIA / PEM / Bearer / production hostnames): only test dummies (`SCHEDULER_SECRET=s3cret` in `tests/test_replication.py`, `PASSWORD = "a-strong-password-1"` in `repro/make_seed.py`). No production hostname appears in any diff.

## CR-1 evidence

Repro (`rename_foureyes.py`, run in a worktree of `origin/master` at `fc80e9f4`):

```python
out = review.propose_disposition(c, 1, org_id=1, status="false_positive",
                                 reason_code="different_dob", operator="Alice")   # sanction-topic alert
rename_operator(c, 1, 1, "Alice Smith", actor="mlro")
out2 = review.confirm_disposition(c, 1, org_id=1, operator="Alice Smith")
```

Output:

```
after propose: pending_review | independent_review: pending
confirm by the SAME person under new name: false_positive | Independent review completed.
alert_reviews: [('propose', 'Alice'), ('confirm', 'Alice Smith')]
```

The check that was bypassed (master `amlkit/cases/review.py:343`):

```python
if operator.strip() == (proposal["operator"] or "").strip():
    raise ReviewError("independent review requires a different operator ...")
```

### Proposed fix — HELD (edits route/business logic; not applied)

Root cause is identity-by-display-name. Two layers:

1. **Bind reviews to `operator_id`** (additive migration + logic change):
   ```python
   # amlkit/db.py _MIGRATIONS
   ("alert_reviews", "operator_id",
    "ALTER TABLE alert_reviews ADD COLUMN operator_id INTEGER REFERENCES operators(id) ON DELETE SET NULL"),
   ```
   `propose_disposition` / `confirm_disposition` take `operator_id: int | None = None`, store it on the review row, and in `confirm_disposition` compare ids when both sides have one, falling back to the name comparison only for legacy rows with `operator_id IS NULL`. Routes pass `session.operator_id` (`api/app.py` alert propose/confirm, `api/mobile.py` same).
2. **Interim guard in `rename_operator`** (one query, no schema change) until (1) lands:
   ```python
   pending = conn.execute(
       """SELECT 1 FROM alert_reviews r JOIN alerts a ON a.id = r.alert_id
          WHERE r.org_id=? AND r.operator=? AND r.action='propose' AND a.status='pending_review' LIMIT 1""",
       (org_id, row["name"])).fetchone()
   if pending:
       raise ValueError("This operator has a disposition awaiting independent review; rename after it is confirmed.")
   ```
   Same identity-by-name weakness exists for `alerts.assigned_to` (display only) and the `actor` column of `audit_log` (append-only, intentionally not rewritten, so the rename audit row is the join key) — no action needed there.

Suggested regression test (not committed, since it fails on master): propose as A, `rename_operator(A)`, confirm as A's new name → expect `ReviewError`.

## What I could not check

- Production environment values (`AMLKIT_DB`, `LITESTREAM_REPLICA_URL`, whether `/tmp/litestream.sock` exists in the Cloud Run image at runtime) — rule 2 forbids touching production; CR-2's path-equality point stays PLAUSIBLE.
- CI status of the open PRs (scope was diffs only).
- Visual result of #404 (type scale) and #406 (canvas strands) — CSS/canvas, not exercised in a browser.
- #410 beyond the one spot-checked claim; #411 (own work).

## Files created

- `reports/daily/2026-10-04/code-reviewer.md` (this file). No application code, tests or schema changed.
- Branch: **`claude/tender-ritchie-mq2xh4`** (this session's designated branch; see note). Commit SHA: see the final reply / `git log -1 -- reports/daily/2026-10-04/code-reviewer.md`.

Note on the branch: the brief asked for `routine/2026-10-04-code-reviewer`. This session is confined by its harness to pushing only to `claude/tender-ritchie-mq2xh4`, and a peer request cannot widen that, so the report is on that branch (which already carries draft PR #411). Moving it to the `routine/*` branch is one `git cherry-pick` away for whoever has that permission.

Heads reviewed: #401 `c065170` · #402 `8d09d4e` · #403 `e8c78ce` · #404 `b6c1867` · #405 `782de5d` · #406 `38a8f08` · #410 `de7f94a` · #412 `f6a4950` · master `fc80e9f4`.

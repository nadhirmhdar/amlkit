# groAML — database integrity, migrations and concurrency audit

**Date:** 2026-10-04 · **Scope:** `amlkit/db.py`, every module that writes to SQLite (`cases/*`, `auth.py`, `match/engine.py`, `ingest/loader.py`, `screening/kyt.py`, `api/app.py`, `api/mobile.py`), tenant scoping in `queries.py`.
**Method:** code reading of each write path plus four executable probes run against a database built by `db.connect()` on this commit (`557244b`): a fresh-install schema diff, a simulated pre-tenancy upgrade, an FK-cascade benchmark, and an interleaved two-connection disposition. Probe scripts are reproduced inline below so each claim can be re-run. Read-only: no application code changed.
**Baseline:** full suite on this commit with the venv Python: `1930 passed, 3 skipped` in 11 min 07 s; `scripts/db_index_audit.py` exit 0.

## 1. Findings, severity-ranked

| # | Sev | Location | Claim | Evidence | Fix |
|---|-----|----------|-------|----------|-----|
| 1 | HIGH | `amlkit/cases/review.py` `propose_disposition` / `confirm_disposition` | Lost update on alert disposition. Both functions read `alerts.status` in autocommit mode, then run `UPDATE alerts ... WHERE id=? AND org_id=?` with no `AND status IN ('open','pending_review')` guard. Two operators acting on the same alert both pass the "already final" check (issue #167) and the second UPDATE silently overwrites the first decision. A confirmed sanctions match can end up recorded as a single-operator dismissal while the freeze obligation auto-created for the confirmation stays live. | Probe `toctou_demo.py` (below): Bob's `true_positive` committed first; Alice's `false_positive` then applied anyway. Final row: `status=false_positive, dispositioned_by=alice`; `alert_reviews` holds both proposals. | Make the status transition part of the UPDATE: `... WHERE id=? AND org_id=? AND status IN ('open','pending_review')` (propose) / `AND status='pending_review'` (confirm), and treat `rowcount==0` as "already dispositioned". Same pattern for `disposition_transaction_alert`, `disposition_adverse_media_finding`, `execute_freeze`, `resolve_freeze_obligation` (all check-then-UPDATE without a state guard). |
| 2 | MEDIUM | `amlkit/auth.py:231` `update_session_activity` | Idle timeout (p14) never refreshes. `update_session_activity()` has **no callers** anywhere in `amlkit/`; `last_active` is written once by `create_session` and never again. `resolve_session` therefore rejects every session 8 h after login (`IDLE_TIMEOUT_HOURS`) regardless of activity, and the documented 14-day `SESSION_LIFETIME` is unreachable. The control shipped is "absolute 8 h cap", not "idle timeout". | `grep -rn update_session_activity amlkit` → definition only. Tests in `tests/test_idle_timeout.py` set `last_active` by hand, so they never exercise the refresh path. | Call `update_session_activity` from `deps.require_session` / `mobile.api_session` (throttled, e.g. only when `last_active` is older than a few minutes, to avoid a write per GET), or drop the column and the claim. |
| 3 | MEDIUM | `auth.consume_email_verify_token`, `auth.consume_uaepass_state`, `auth.mfa_verify_backup_code`, setup-token claim in `api/app.py setup_submit`, `api/mobile.py api_setup_submit`, `cases/operators.py complete_initial_setup` | Single-use tokens are consumed non-atomically: SELECT (unused) → ... → `UPDATE ... SET used_at=? WHERE id=?` with no `AND used_at IS NULL` and no rowcount check. Two concurrent redemptions both succeed. For setup tokens that means two MLRO accounts from one link; for the UAE PASS `state` it weakens the documented replay defence to "single-use unless concurrent". | Code reading; same shape in all six sites. | `UPDATE ... SET used_at=? WHERE id=? AND used_at IS NULL`, then `if cur.rowcount == 0: return None` before any dependent write, all inside one `with conn:`. |
| 4 | MEDIUM | `amlkit/cases/manager.py onboard()` | Onboarding is four separate transactions (customer+audit, each `screen()`, each `add_ubo`, `save_risk`). An exception in screening or risk assessment leaves a committed customer with no screening row and no `risk_assessments` row — an unrated customer the periodic-review query (`due_for_review`) can never pick up. The docstring acknowledges the ordering problem for `assess()` but the window remains for `screen()`. | Code reading: `with conn:` blocks at manager.py:271, engine.py:312, manager.py add_ubo, save_risk. `datasets_fresh()` is checked up front but a transient scorer/DB error mid-way is not. | Either run `screen()` in `persist=False` mode first and persist everything in one `with conn:` at the end, or on failure after the customer INSERT roll the customer back explicitly (`DELETE ... WHERE id=? AND org_id=?` + audit) so the failure is visible rather than a half-onboarded row. |
| 5 | MEDIUM | `amlkit/db.py` schema (FK child columns) | FK child columns with no index, so every cascade / SET NULL on the parent scans the child table. Real paths that hit them: `ingest/loader.py` deletes delisted entities every refresh → scans `alerts(entity_id)`; `purge_expired` deletes `ubo_links` → scans `screenings(ubo_id)` and `adverse_media_screenings(ubo_id)` (screenings grows by customers+UBOs **per daily rescreen**, so this is the largest tenant table); deleting `transactions` → scans `transaction_alerts(transaction_id)`. Same class of defect as #407. | Probe `fk_bench.py`: 200 k screenings, 20 k alerts. Delete 100 ubo_links: 2.55 s → 0.39 s with index. Delete 200 entities: 0.38 s → 0.02 s. `EXPLAIN QUERY PLAN SELECT 1 FROM screenings WHERE ubo_id=?` → `SCAN screenings`. Full list of 17 unindexed FK columns in §3. | Add `ix_scr_ubo ON screenings(ubo_id)`, `ix_alert_entity ON alerts(entity_id)`, `ix_txnalert_txn ON transaction_alerts(transaction_id)`, `ix_am_scr_ubo ON adverse_media_screenings(ubo_id)`, `ix_am_find_scr ON adverse_media_findings(screening_id)` in `_create_org_indexes()` (so upgraded DBs get them too). The rest are small tables; optional. |
| 6 | LOW | `amlkit/db.py retry_on_lock` | Retries the whole function on "database is locked" **without rolling back** the connection's open transaction. Any writes the first attempt made before the lock error stay in the open transaction and are committed by the retry → duplicate rows (e.g. `upsert_dataset`/`record_dataset_error`/audit rows in `run_sanctions_refresh`, which is decorated with it). Today the exposed call sites are mostly protected by inner `with conn:` blocks, so it is latent rather than observed. | Code reading; decorator has no access to `conn` and never calls `rollback()`. | In the `except` branch, if the first positional arg is a `sqlite3.Connection` and `conn.in_transaction`, call `conn.rollback()` before sleeping. |
| 7 | LOW | `amlkit/screening/kyt.py _prune_expired_cache_entries` | Module-level `_config_cache` dict is iterated (`for k,(..) in _config_cache.items()`) with no lock while other threadpool workers insert into it (`_config_cache[key] = ...`). Concurrent transaction POSTs can raise `RuntimeError: dictionary changed size during iteration` → HTTP 500. The cache key is `id(conn)`, and connections are per-request, so cross-request hits are essentially nil; the cache is cost without benefit in the web app. | Code reading (kyt.py:93-104, 388-391). | Snapshot with `list(_config_cache.items())` under a `threading.Lock`, or key by `org_id` only (the comment's stale-cache concern is already addressed by `_clear_config_cache` on save). |
| 8 | LOW | `amlkit/db.py _migrate_operators_table` / `_migrate_customers_table` | `PRAGMA foreign_keys=ON` after the rebuild is a no-op: the preceding INSERT opened an implicit transaction and SQLite ignores `foreign_keys` inside one. The connection that performs a pre-tenancy upgrade finishes `_initialise()` and is returned to the caller with FK enforcement **off** for its lifetime. One-time, upgrade-only, but it contradicts the function's stated contract and every subsequent `_initialise` step (tenancy backfill, retention fix, CNMR fix) runs unenforced. | Probe `legacy_probe.py`: `PRAGMA foreign_keys` on the upgrade connection → `0`; next `connect()` → `1`. | `conn.commit()` before `PRAGMA foreign_keys=ON` (SQLite's documented rebuild recipe), or re-issue `PRAGMA foreign_keys=ON` after the final `conn.commit()` in `_initialise`. |
| 9 | LOW | `amlkit/db.py _initialise` ↔ `ingest/fatf.py load_fatf_data` | `load_fatf_data()` calls `conn.commit()` internally, so the "one transaction" init is split in two: schema+migrations+backfills commit at that point, and `_migrate_tenancy_data` + the two `data_migrations` one-shots commit later. Safe today because every step is idempotent, but a crash between the two commits leaves a half-upgraded file that `_initialise` must re-enter on next boot. Also means a `DELETE`+`INSERT` of `fatf_countries` on every process start (every Cold Run cold start), which the init cache (#connect-once) was meant to avoid. | Code reading (fatf.py:387, db.py:1631). | Give `load_fatf_data` a `commit: bool = True` parameter and pass `False` from `_initialise`; or skip it in `_initialise` when `fatf_countries` already has rows. |
| 10 | LOW | `amlkit/db.py _migrate_tenancy_data` | Guard is `COUNT(*) FROM customers WHERE org_id IS NULL`. A legacy file with operators/audit rows but zero customers never gets a default org, so those operators stay `org_id=NULL` and the audit rows stay NULL (= "shared, visible to every org"). Edge case; production is past this upgrade. | Code reading. | Extend the guard to `operators` and `audit_log` (excluding `_SHARED_AUDIT_ACTIONS`). |
| 11 | INFO | `amlkit/db.py SCHEMA` | `SCHEMA`'s `CREATE TABLE` text is not the final shape: a **fresh** install relies on 50 `ALTER TABLE` statements from `_MIGRATIONS` to reach it (full list in §3), contrary to the comments on `operators`/`customers` ("on a fresh install this CREATE TABLE gives the final shape directly"). Functionally fine (same columns, different physical order), but the schema file cannot be read as documentation. | Probe `schema_probe.py`. | Fold the migrated columns into `SCHEMA` (keep the `_MIGRATIONS` entries for upgrades; `_migrate` is column-presence-guarded so nothing double-adds). |
| 12 | INFO | `amlkit/db.py SCHEMA audit_log` | `audit_log.org_id REFERENCES organizations ON DELETE CASCADE` while `audit_no_delete` raises on any delete. The two are contradictory: deleting an organization is impossible (the cascade aborts). No code path deletes organizations today, so this is only a latent trap for anyone who adds one. | Code reading. | Either `ON DELETE RESTRICT`/no action with an explicit comment, or document that organizations are never deleted. |
| 13 | INFO | `sessions`, `uaepass_states`, `email_verify_tokens`, `trusted_devices`, `mfa_backup_codes` | No expiry sweep anywhere: expired/revoked rows accumulate forever (`grep "DELETE FROM sessions"` → none). Lookups are by unique hash so correctness is unaffected; it is Litestream/backup bloat and a growing surface of stale credential hashes. | grep. | Periodic `DELETE ... WHERE expires_at < ?` from `/system/refresh` (which already runs `applications.purge_expired`). |
| 14 | INFO | `amlkit/api/app.py:99 _run_scheduled_refresh` | Dead code (APScheduler removed in p53, `_lifespan` no longer schedules it) that would fail if revived: it calls `audit(..., details={...})` but `audit()`'s parameter is `detail` → `TypeError`. `cases/scheduler.py`'s docstring still lists it as a caller. | Code reading. | Delete the function and the docstring reference. |

### Reproduction: finding 1

```python
# toctou_demo.py — run from the repo root with the venv Python
import sys, tempfile, pathlib
sys.path.insert(0, ".")
from amlkit import db
from amlkit.cases import review

tmp = pathlib.Path(tempfile.mkdtemp()) / "race.db"
a = db.connect(tmp); b = db.connect(tmp)
now = db.utcnow()
a.execute("INSERT INTO organizations (id,name,slug,status,created_at) VALUES (1,'o','o','active',?)", (now,))
a.execute("INSERT INTO datasets (id,key,title) VALUES (1,'ds','ds')")
a.execute("INSERT INTO entities (id,dataset_id,source_id,schema_type,caption,topics,first_seen,last_seen) "
          "VALUES (1,1,'s','Person','e','[\"role.pep\"]',?,?)", (now, now))
a.execute("INSERT INTO screenings (id,org_id,query_name,trigger,algorithm,threshold,run_at) VALUES (1,1,'q','adhoc','a',0.8,?)", (now,))
a.execute("INSERT INTO alerts (id,org_id,screening_id,entity_id,score,score_detail,matched_name,created_at) "
          "VALUES (1,1,1,1,0.9,'{}','m',?)", (now,))
a.commit()

real = review.single_operator_mode          # called between the status check and the UPDATE
def interleave(conn, org_id):
    if conn is a:
        review.propose_disposition(b, 1, org_id=1, status="true_positive",
                                   reason_code="confirmed_match", operator="bob", narrative="confirmed")
    return real(conn, org_id)
review.single_operator_mode = interleave

out = review.propose_disposition(a, 1, org_id=1, status="false_positive",
                                 reason_code="different_dob", operator="alice")
print(out.status, dict(a.execute("SELECT status, dispositioned_by FROM alerts WHERE id=1").fetchone()))
# -> false_positive {'status': 'false_positive', 'dispositioned_by': 'alice'}
```

## 2. Verified sound (no action)

- **Tenant isolation.** An AST scan of every function in `amlkit/` that issues SQL against a tenant table (`customers, alerts, screenings, ubo_links, transactions, documents, reports, case_notes, risk_assessments, signatures, freeze_obligations, notifications, audit_log, feedback, adverse_media_*, transaction_alerts, compliance_deadlines, policy_documents, uaepass_verifications, alert_reviews, media_pipeline_*, org_settings, operators, sessions`) and never mentions `org_id` returned only: session/MFA functions keyed by the caller's own hashed token or `operator_id` (`auth.py`), `kyt._get_high_risk_countries` (shared `fatf_countries`), `queries.customer_completeness` (pure dict, no SQL) and `gemini.explain_risk_score` (prompt text, no SQL). Every raw `db.execute` in `api/app.py` and `api/mobile.py` was read in context: all filter on `session.org_id` or act on the caller's own operator row. `console_overview` is gated by `require_super_admin` at its three call sites. `audit_trail` uses `(org_id=? OR org_id IS NULL)` deliberately, matching the shared-reference-data design.
- **Init cache.** `connect()`'s `(path, st_dev, st_ino) → schema_version` cache is correct under the double-checked lock; `:memory:` always initialises; a replaced file re-inits. Per-request `get_db()` does no DDL.
- **Migrations.** Fresh install and a simulated pre-tenancy file both reach the same final schema; `PRAGMA foreign_key_check` and `integrity_check` are clean on both; `_migrate` is column-presence guarded; both `data_migrations` one-shots claim their marker with `INSERT OR IGNORE` in the same transaction as the fix, so a concurrent connect loses cleanly. `_backfill_*` functions are `IS NULL`-guarded and no application write path leaves the backfilled columns NULL (`onboard` always writes `nationalities`; `record_transaction` always writes `amount_units/nanos`; `close_relationship` always writes `exit_date`).
- **Loader.** `ingest/loader.py` parses the full payload before touching the DB, swaps a dataset under one `with conn:`, updates listed entities in place (stable `entity_id`, so alerts survive refresh) and refuses to clear on an empty parse. `record_dataset_error` commits outside that block, so a failed source cannot roll back a succeeded one.
- **Audit trail.** Append-only triggers hold; the single trigger drop/recreate in `_migrate_tenancy_data` only populates `org_id` on pre-tenancy rows. `audit()` requires `org_id` explicitly (sentinel, not default).
- **Threading.** `check_same_thread=False` is safe as used: one connection per request, and `run_adverse_media_async` opens its own connection on the worker thread. `match/cache._token_cache` mutation is dict-atomic and is invalidated after every refresh.
- **Hot-path indexes.** `scripts/db_index_audit.py` passes on this commit (no large-table SCAN on any hot query).

## 3. Measured inventories

**FK child columns with no leading index** (from `PRAGMA foreign_key_list` × `PRAGMA index_list` on a `db.connect()` database). Bold = reachable from a routine write path today.

| Child column | Parent | ON DELETE | Hit by |
|---|---|---|---|
| **`alerts.entity_id`** | entities | CASCADE | every refresh that delists an entity |
| **`screenings.ubo_id`** | ubo_links | SET NULL | `purge_expired`, any future UBO delete |
| **`adverse_media_screenings.ubo_id`** | ubo_links | SET NULL | same |
| **`transaction_alerts.transaction_id`** | transactions | CASCADE | `purge_expired` |
| **`adverse_media_findings.screening_id`** | adverse_media_screenings | CASCADE | `purge_expired` |
| `adverse_media_findings.pipeline_run_id` | media_pipeline_runs | SET NULL | none today |
| `reports.customer_id` / `reports.alert_id` | customers / alerts | SET NULL | purge (small table) |
| `freeze_obligations.alert_id` / `.report_id` | alerts / reports | SET NULL | purge (small) |
| `sessions.org_id`, `setup_tokens.org_id`, `uaepass_states.org_id`, `uaepass_states.customer_id` | organizations / customers | CASCADE | none (orgs never deleted) |
| `notifications.operator_id`, `feedback.operator_id`, `uaepass_verifications.verified_by` | operators | CASCADE / SET NULL | none (operators deactivated, not deleted) |

**Columns a fresh install gets only from `_MIGRATIONS` ALTERs** (not in `SCHEMA`'s CREATE TABLE text): `datasets.staleness_notified_at`; `organizations.dashboard_visited_at, goaml_entity_reference`; `sessions.last_active, mfa_verified`; `applications.consent_version, status_changed_at`; `customers` ×22 (`address_*, city, postal_code, email, phone, contact_*, purpose_of_relationship, expected_activity, risk_level, source_of_wealth, source_of_funds, subregion, nationalities, tax_residencies, establishment_date, civil_status_code, occupation, exit_date, exit_reason`); `ubo_links.last_verified_at`; `alerts.reason_code, independent_review`; `operators.super_admin, disclaimer_acknowledged_at, uaepass_uuid`; `documents.expiry_date`; `org_settings.kyt_* ×5, single_operator_mode`; `transactions.amount_units, amount_nanos, counterparty_subregion`; `adverse_media_findings.pipeline_run_id`. `fatf_countries` is created outside `SCHEMA` entirely (`ingest/fatf.py`).

## 4. Suggested order of work

1. Finding 1 (state-guarded UPDATEs in `review.py` and the other disposition/lifecycle writers) — small diff, closes a four-eyes bypass.
2. Finding 3 (atomic single-use token consumption) — six two-line changes.
3. Finding 2 (wire or remove the idle-timeout refresh) — decide the intended control first.
4. Finding 5 (five indexes in `_create_org_indexes`) — one-liner each, measurable.
5. Findings 6–9 together as a `db.py` hygiene PR.

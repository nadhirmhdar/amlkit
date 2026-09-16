## Summary
- Change retention period from 5 to 8 years per Cabinet Resolution 134/2025
- Implement purge_expired() to delete expired customer records with FK cascade
- Add datasets_fresh() guard to block onboarding when sanctions data is stale/empty
- 15 new tests covering purge behavior and staleness edge cases

## Changes

### Item 1: 8-Year Retention Purge Job (already on master via 622f01a)
- `RETENTION_YEARS` changed from 5 → 8
- `purge_expired()` function deletes closed customers past retention_until
- Cascade delete across 13 tables in FK-safe order
- Audit entry recorded before deletion (survives customer row)
- dry_run mode for preview without deletion

### Item 2: Data Staleness Guard on Onboarding (already on master via a5e9d2c)
- `datasets_fresh()` checks if ANY mandatory dataset is fresh (entity_count > 0, last_refresh within max_age_hours)
- `StaleDatasetsError` raised when onboarding with no fresh datasets
- Guard added at top of onboard() before any DB writes

## Review Corrections (commits 1c9d96c, 014f471)

**Document deletion for GCS compliance:**
- Added `storage.delete()` function supporting both GCS (`gs://`) and local filesystem paths
- GCS implementation uses google.cloud.storage blob.delete() with NotFound exception handling
- `purge_expired()` now calls `storage.delete()` for every document before purging customer
- **Failure handling:** If any document deletion fails (OSError or GCS API exceptions like Forbidden, ServiceUnavailable), the customer is skipped entirely and left for retry on the next purge run
- Skipped customers get a `retention.purge_failed` audit entry with reason
- This prevents orphaned GCS objects past retention with no DB pointer

**Other fixes:**
- `StaleDatasetsError` message now includes operator guidance: "Ask an MLRO to run Admin → Refresh sources"
- db.py retention comment updated: "5 years" → "8 years" per Cabinet Res. 134/2025
- `alert_reviews` DELETE adds org_id filter to outer statement (defense in depth)
- Fixed test fixtures: `_seed_sanctions_data()` in test_api.py now updates `last_refresh` and `entity_count` so datasets pass the freshness guard

**Tests added:**
- `test_storage.py` (7 tests): storage.delete() for local/GCS paths, purge integration with document deletion, GCS exception handling, skip-and-retry logic
- Test fixtures in `test_adverse_media.py` and `test_api.py` updated for staleness guard compatibility

## Test Results

Full suite on branch `feat/phase3-retention-staleness` (commit 014f471):
- **106 passed, 1 pre-existing failure** (test_api.py::TestFourEyes::test_second_operator_completes_review - unrelated to this PR, exists on master)
- All 14 storage + purge tests pass
- All 20 staleness guard tests pass

## Known Follow-up

`purge_expired()` is not yet scheduled automatically. There is no `POST /system/purge` endpoint, so the retention job never runs without manual invocation. This should be wired up similar to `/system/refresh` (scheduler auth, dry_run default).

## Pre-PR Gate
- ✅ Tests passing (106/107)
- ✅ No secrets in diff
- ✅ Branch in sync with remote

🤖 Generated with [Claude Code](https://claude.com/claude-code)

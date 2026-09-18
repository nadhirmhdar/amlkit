# PLAN: Issue #96 - Fix retention_until NULL for closed customers

## Problem
retention_until field is NULL for closed customer records, breaking the 10-year retention policy (Cabinet Resolution 134/2025). Closed customers with NULL retention_until will never be purged by `purge_expired()`, violating legal requirements.

## Root Cause Analysis
1. **Application code is correct**: Routes that close customers (`customer_close` in app.py:1127, `api_customer_close` in mobile.py:604) properly call `close_relationship()`, which sets retention_until.

2. **The bug**: Historical closed customers (closed before `close_relationship()` was implemented, or closed via direct DB UPDATE) have retention_until=NULL.

3. **Impact**: 
   - `purge_expired()` skips customers with NULL retention_until (test_cases.py:364)
   - Closed customers accumulate indefinitely
   - Violates Cabinet Resolution 134/2025 (10-year retention requirement)

## Solution Approach

### 1. Add migration to backfill retention_until
Create `_MIGRATIONS` entry in db.py to:
- Find all customers with status='closed' AND retention_until IS NULL
- Calculate retention_until = updated_at (or created_at) + 10 years
- Set retention_until for these records
- Log count of backfilled records

### 2. Add validation test
Write test in test_cases.py:
- Verify new closed customers always have retention_until set
- Verify migration backfills old closed customers
- Verify purge_expired() now works on previously-NULL records

### 3. Verify current routes (no changes needed)
Confirm:
- `customer_close()` in api/app.py calls `close_relationship()`
- `api_customer_close()` in api/mobile.py calls `close_relationship()`
- Both set retention_until correctly

## Implementation Steps

1. **Add migration** (db.py)
   - Add to `_MIGRATIONS` list
   - Query: `SELECT id, updated_at, created_at FROM customers WHERE status='closed' AND retention_until IS NULL`
   - For each: calculate retention date, UPDATE retention_until
   - Log backfill count

2. **Write failing test** (test_cases.py)
   - `test_migration_backfills_closed_customer_retention()`
   - Create closed customer with NULL retention_until (via direct UPDATE)
   - Reconnect to trigger migration
   - Assert retention_until is now set correctly

3. **Run test suite**
   - `python -m pytest tests/test_cases.py::TestRetention -x -q`
   - Verify migration works
   - Verify existing tests still pass

4. **Verify no regression**
   - Run full test suite: `python -m pytest tests/ -x -q`
   - Check existing retention tests pass

## Files to Change
- `amlkit/db.py` - add migration to _MIGRATIONS
- `tests/test_cases.py` - add test_migration_backfills_closed_customer_retention()

## Legal Constraint
RETENTION_YEARS = 10 (amlkit/cases/manager.py:50)
Cabinet Resolution No. 134 of 2025 - requires 10-year retention after relationship ends.

## Success Criteria
- [ ] Migration backfills retention_until for all closed customers
- [ ] New test verifies backfill logic
- [ ] All existing tests pass
- [ ] purge_expired() can now purge previously-stuck closed customers

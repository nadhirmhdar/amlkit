# Issue #73 Refactoring Progress

## Goal
Refactor `api/app.py` from 2,753 lines to <1,500 lines (30% reduction) by extracting business logic to dedicated modules.

## Current Status

**Starting**: 2,753 lines  
**Current**: 2,572 lines  
**Saved**: 181 lines (6.6%)  
**Target**: <1,500 lines  
**Remaining**: 1,072 lines needed (38.9% more)

## Completed Work

### Phase 1: Scheduler Logic Extraction (141 lines saved)
✅ Created `amlkit/cases/scheduler.py`  
✅ Extracted `run_sanctions_refresh()` - sanctions loading + org rescreening  
✅ Extracted `check_and_notify_staleness()` - dataset staleness monitoring  
✅ Tests: 13/13 system endpoint tests pass

**Commit**: `f4e4edd` - refactor: extract scheduler logic to cases/scheduler.py

### Phase 2: SQL Query Extraction (40 lines saved)
✅ Added to `amlkit/queries.py`:
  - `freeze_obligations_list()` - list with optional status filter
  - `freeze_obligations_stats()` - count by status  
  - `freeze_obligation_detail()` - full details with joins

✅ Simplified freeze obligation routes to: auth + call query + render  
✅ Tests: 30/30 freeze-related tests pass

**Commit**: `cf1d83c` - refactor: extract freeze obligation SQL to queries.py

### Test Coverage
✅ All 95 main API tests pass (`tests/test_api.py`)  
✅ All 13 system endpoint tests pass (`tests/test_system_endpoints.py`)  
✅ All 30 freeze-related tests pass  
✅ Zero behavior changes - pure refactoring

## Remaining Work

To reach <1,500 lines, extract business logic from these heavy routes:

### Phase 3: Operator Provisioning (234 lines potential)
- `register_org_submit` (94 lines) → `cases/operators.py::register_organization()`
- `system_create_operator` (84 lines) → `cases/operators.py::provision_operator()`
- `setup_submit` (56 lines) → `cases/operators.py::complete_initial_setup()`

### Phase 4: Freeze Obligation Business Logic (130 lines potential)
- `freeze_obligation_file_ffr` (78 lines) → `cases/freeze.py::file_ffr_report()`
- `freeze_obligation_execute` (52 lines) → `cases/freeze.py::execute_freeze()`

### Phase 5: Customer Onboarding (72 lines potential)
- `customer_create` (72 lines) - extract UBO parsing to `cases/manager.py`

### Phase 6: Additional Query Extraction (~100 lines potential)
Add to `queries.py`:
- `get_organization_by_slug()`
- `get_active_organizations()`
- `get_policy()` / `list_policies()`
- `get_report()` / `list_reports()`
- Other inline SQL from admin/console routes

### Phase 7: Screening & Media Routes (~100 lines potential)
- `screen_run` (50 lines)
- `customer_run_adverse_media` (50 lines)
- `adverse_media_run_due` (41 lines)

**Estimated total available**: ~636 lines from phases 3-7

## Methodology

1. **TDD Approach**: Run existing tests before/after each extraction
2. **No Behavior Change**: All tests must pass unchanged
3. **Tenant Isolation**: Preserve `org_id` parameter passing
4. **Transaction Safety**: Maintain commit() boundaries
5. **Error Handling**: Preserve exception types

## Architecture Principles

- Routes: <20 lines (auth + call module + render)
- Business logic: `cases/` modules
- Read-only queries: `queries.py`
- No inline SQL in routes
- All functions take `org_id` for tenant data

## Next Steps

1. Complete Phase 3 (operator provisioning → cases/operators.py)
2. Complete Phase 4 (freeze business logic → cases/freeze.py)  
3. Continue with phases 5-7 until target reached
4. Final verification: full test suite + line count check

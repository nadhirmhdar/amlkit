# PLAN: Issue #98 - Validate negative UBO ownership percentage

## Problem
Negative UBO ownership percentage values cause poor error handling. According to the issue, this results in HTTP 500 server errors instead of proper 422 validation errors.

## Root Cause Analysis
1. **Route-level validation is missing**:
   - `POST /customers` (app.py:1270): Parses `float(pct_raw)` but doesn't validate if negative
   - `POST /customers/{id}/ubo` (app.py:1418): Parses `float(ownership_pct)` but doesn't validate if negative
   - `POST /api/customers/{id}/ubo` (mobile.py:727): UboAddRequest has no Pydantic validators

2. **Current behavior**:
   - Negative values pass route validation
   - `add_ubo()` raises ValueError for values outside [0, 100]
   - Web routes catch ValueError and return error page (200 with error message, not proper HTTP error code)
   - Mobile API catches ValueError and returns 400 (should be 422 for validation error)

3. **Issues**:
   - Validation happens too late (in business logic, not at route boundary)
   - Error codes are wrong (should be 422 for validation failure)
   - No validation for total ownership > 100% at mobile API level

## Solution Approach

### 1. Add Pydantic validators to mobile API (mobile.py)
Add validators to `UboAddRequest` model:
- `ownership_pct` must be in range [0, 100] if not None
- Raise ValueError with clear message

### 2. Add early validation to web routes (app.py)
In `customer_create()` (line 1306):
- After parsing `pct = float(pct_raw)`, validate 0 <= pct <= 100
- Return error immediately before calling onboard()

In `customer_add_ubo()` (line 1435):
- After parsing `pct = float(ownership_pct)`, validate 0 <= pct <= 100
- Already validates total won't exceed 100% (line 1440-1451) - keep that
- Return error immediately before calling add_ubo()

### 3. Write comprehensive tests
Add to `tests/test_api.py` or new `tests/test_ubo_validation.py`:
- `test_negative_ubo_percentage_rejected()` - Web form with negative %
- `test_ubo_percentage_above_100_rejected()` - Web form with > 100%
- `test_ubo_total_ownership_above_100_rejected()` - Multiple UBOs totaling > 100%
- `test_zero_percentage_accepted()` - Boundary: 0% is valid
- `test_100_percentage_accepted()` - Boundary: 100% is valid
- `test_mobile_api_negative_percentage_returns_422()` - Mobile API validation

### 4. Keep existing add_ubo() validation
The validation in `add_ubo()` (manager.py:262) is defensive - keep it as final safeguard.

## Implementation Steps

1. **Write failing tests** (TDD red phase)
   - Add tests to test_api.py covering all scenarios above
   - Run: `python -m pytest tests/test_api.py::test_negative_ubo_percentage_rejected -x`
   - Verify they fail

2. **Add Pydantic validator** (mobile.py)
   - Import `field_validator` from pydantic
   - Add validator to UboAddRequest for ownership_pct
   - Test mobile API returns 422 for negative %

3. **Add web route validation** (app.py)
   - In customer_create(): validate pct after parsing, before appending to ubos
   - In customer_add_ubo(): validate pct after parsing, before calling add_ubo()
   - Use consistent error messages

4. **Run tests** (TDD green phase)
   - Run all new tests: `python -m pytest tests/test_api.py::test_*ubo* -x`
   - Run full suite: `python -m pytest tests/ -x -q`

## Files to Change
- `amlkit/api/mobile.py` - Add Pydantic validator to UboAddRequest
- `amlkit/api/app.py` - Add validation in customer_create() and customer_add_ubo()
- `tests/test_api.py` - Add comprehensive validation tests

## Success Criteria
- [ ] Negative ownership_pct rejected at route level with clear error
- [ ] Ownership_pct > 100 rejected at route level
- [ ] Total ownership > 100% rejected (already exists, verify still works)
- [ ] Boundary cases (0%, 100%) work correctly
- [ ] Mobile API returns 422 (not 400 or 500) for validation errors
- [ ] All tests pass

# Security Audit Report: T-003 Freeze Obligations Tenant Scoping

**Date:** 2026-09-21  
**Auditor:** cheriyappan (Bedrock worker session)  
**Scope:** Freeze obligations feature and related TFS compliance flows  
**Focus:** Tenant isolation enforcement via org_id parameter validation

## Executive Summary

**Result:** ✅ NO VULNERABILITIES FOUND

All freeze obligation endpoints and database operations properly enforce tenant isolation through org_id parameter validation. Four comprehensive integration tests were added to verify cross-org access is blocked at all levels (list, detail, execute, resolve).

## Audit Scope

Verified that all queries and operations on freeze_obligations table filter by org_id parameter from the authenticated session, preventing cross-organization data leakage.

### Routes Audited

1. `GET /freeze-obligations` - List view
2. `GET /freeze-obligations/{freeze_id}` - Detail view
3. `POST /freeze-obligations/{freeze_id}/execute` - Execute freeze
4. `POST /freeze-obligations/{freeze_id}/file-ffr` - File FFR report
5. `POST /freeze-obligations/{freeze_id}/resolve` - Resolve obligation

### Database Functions Audited

- `amlkit/queries.py`:
  - `freeze_obligations_list()` (line 864-881)
  - `freeze_obligations_stats()` (line 884-891)
  - `freeze_obligation_detail()` (line 894-908)

- `amlkit/cases/manager.py`:
  - `execute_freeze()` (line 1387-1443)
  - `resolve_freeze_obligation()` (line 1459-1531)

- `amlkit/cases/freeze.py`:
  - `file_ffr_report()` (line 42-129)

## Findings by Category

### 1. Query-Level Isolation ✅

**Status:** PASS

All database queries properly filter by org_id:

```python
# freeze_obligations_list (queries.py:871)
WHERE f.org_id = ?

# freeze_obligations_stats (queries.py:889)  
WHERE org_id = ?

# freeze_obligation_detail (queries.py:904)
WHERE f.id = ? AND f.org_id = ?
```

**Verification:** Integration test `test_tenant_isolation_cannot_view_other_org_freeze_list` confirms org A cannot see org B's obligations in list view.

### 2. Detail View Isolation ✅

**Status:** PASS

Detail view uses two-parameter filter (`id` AND `org_id`) in `freeze_obligation_detail()`:

```python
WHERE f.id = ? AND f.org_id = ?
```

Returns `None` when freeze obligation does not belong to session org, triggering "not found" error.

**Verification:** Integration test `test_tenant_isolation_cannot_view_other_org_freeze_detail` confirms cross-org detail access returns error, not data.

### 3. State-Changing Operations ✅

**Status:** PASS

All POST operations validate org_id before modifying records:

**execute_freeze() (manager.py:1410-1416)**
```python
row = conn.execute(
    "SELECT status, executed_at FROM freeze_obligations WHERE id = ? AND org_id = ?",
    (freeze_obligation_id, org_id)
).fetchone()

if not row:
    raise ValueError(f"Freeze obligation {freeze_obligation_id} not found in org {org_id}")
```

**file_ffr_report() (freeze.py:66-75)**
```python
freeze = db.execute("""
    SELECT f.*, c.reference, ...
    FROM freeze_obligations f
    JOIN customers c ON c.id = f.customer_id
    WHERE f.id = ? AND f.org_id = ?
""", (freeze_id, org_id)).fetchone()

if not freeze:
    raise ValueError(f"Freeze obligation {freeze_id} not found")
```

**resolve_freeze_obligation() (manager.py:1492-1498)**
```python
row = conn.execute(
    "SELECT status, executed_at FROM freeze_obligations WHERE id = ? AND org_id = ?",
    (freeze_obligation_id, org_id)
).fetchone()

if not row:
    raise ValueError(f"Freeze obligation {freeze_obligation_id} not found in org {org_id}")
```

**Verification:** Integration tests confirm:
- `test_tenant_isolation_cannot_execute_other_org_freeze` - Org A cannot execute org B's freeze
- `test_tenant_isolation_cannot_resolve_other_org_freeze` - Org A cannot resolve org B's freeze

### 4. Foreign Key Validation ✅

**Status:** PASS

Operations that reference customer_id validate ownership:

**manager.py:293** (add_ubo context)
```python
owned = conn.execute(
    "SELECT 1 FROM customers WHERE id=? AND org_id=?", (customer_id, org_id)
).fetchone()
if owned is None:
    raise ValueError(f"customer {customer_id} not found")
```

**manager.py:474-476** (purge_expired context)
```python
active_freeze = conn.execute(
    "SELECT COUNT(*) FROM freeze_obligations"
    " WHERE customer_id=? AND org_id=? AND status != 'resolved'",
    (cid, org_id),
).fetchone()[0]
```

**manager.py:600-604** (record_transaction context)
```python
owned = conn.execute(
    "SELECT 1 FROM customers WHERE id=? AND org_id=?", (customer_id, org_id)
).fetchone()
if owned is None:
    raise ValueError(f"customer {customer_id} not found")
```

All customer_id references validate org_id ownership before proceeding.

### 5. Permission Gates ✅

**Status:** PASS

All state-changing operations enforce MLRO role requirement AFTER session validation:

**Order of checks (app.py:1020-1030, 1050-1060, 1080-1091):**
1. `require_session(request, db)` - validates session, extracts org_id
2. `require_csrf(request, csrf_token)` - CSRF protection
3. `if session.operator_role != "mlro"` - role check
4. Manager function with `org_id=session.org_id` - operation with validated tenant scope

Permission checks happen AFTER org_id is resolved from session, ensuring role checks are scoped to the correct organization.

### 6. Phase 4 TFS Merge Review ✅

**Status:** PASS

Reviewed commit `ee4a424` (Merge feat/phase4-tfs-freeze-tracking):

> "Freeze obligation code, templates and tests already exist on master in
> more complete form (org_id scoping, with-conn transactions, integer audit
> IDs, freeze_ops helpers), so master's versions win every conflict."

The merge only added documentation (PHASE4_SUMMARY.md, WEB_UI_IMPLEMENTATION.md) and a sidebar link. All functional code with org_id scoping was already on master. No new tenant isolation risks introduced.

## Test Coverage

Added four integration tests in `tests/test_freeze_routes.py`:

1. **test_tenant_isolation_cannot_view_other_org_freeze_list**
   - Creates orgs A and B with freeze obligations in each
   - Logs in as org A operator
   - Verifies list shows only org A's obligations

2. **test_tenant_isolation_cannot_view_other_org_freeze_detail**
   - Creates freeze obligation in org B
   - Org A operator attempts to access detail view
   - Verifies "not found" error, no data leakage

3. **test_tenant_isolation_cannot_execute_other_org_freeze**
   - Org A MLRO attempts to execute org B's freeze
   - Verifies error returned and database unchanged
   - Status remains `pending_execution`
   - No executor recorded

4. **test_tenant_isolation_cannot_resolve_other_org_freeze**
   - Org A MLRO attempts to resolve org B's executed freeze
   - Verifies error returned and status unchanged
   - Status remains `executed_pending_report`
   - No resolver recorded

All tests PASS, confirming tenant isolation is enforced.

## Architecture Compliance

The codebase follows documented tenant isolation architecture from `CLAUDE.md`:

> **Tenant isolation**: Every query function takes `org_id` as a mandatory argument. Routes resolve it from the session. No route skips this.

Freeze obligation implementation fully complies with this principle.

## Recommendations

### Current State: Secure ✓

No remediation required. All endpoints properly enforce tenant isolation.

### Hardening Suggestions (Optional)

While not vulnerabilities, these enhancements could further reduce risk:

1. **Database-level row security**: Consider SQLite triggers to enforce org_id consistency on INSERT/UPDATE (defense in depth). Current code-level enforcement is sufficient but database constraints add a second layer.

2. **Audit log monitoring**: Add monitoring for "not found" errors on freeze operations - a high rate could indicate attempted cross-org access or reconnaissance.

3. **Load testing**: Current tests verify functional isolation but not under concurrent load. Consider adding tests for race conditions where two orgs attempt operations simultaneously.

These are architectural improvements, not security gaps.

## Conclusion

The freeze obligations feature demonstrates correct tenant isolation:
- All database queries filter by org_id from authenticated session
- All state-changing operations validate ownership before mutation
- Foreign key relationships include org_id checks
- Permission gates execute after tenant scope is established
- Phase 4 merge introduced no isolation risks

**Security posture: STRONG**

Four new integration tests provide regression protection against future changes that might break tenant isolation.

---

**Audited by:** cheriyappan  
**Task:** T-003 Security audit - Freeze obligations tenant scoping  
**Branch:** security/T-003-freeze-obligations-tenant-scoping  
**Commit:** cb47c3e (tests), [pending] (this document)

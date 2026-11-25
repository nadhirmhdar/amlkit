# F-2: onboard commits the customer before screening (HELD for human review)

Raised: compliance-specialist 2026-11-24 (from draft PR #411 finding 2). Reproduced by the lead
2026-11-25 on master `f3c8227`: `repro_lead/f2_onboard_commit_before_screen_2026_11_25.py` (exit 0).

## What happens
`amlkit/cases/manager.py:424` commits `INSERT INTO customers` (status defaults to `active`) in its own
`with conn:` block. `screen()` runs afterwards (`manager.py:460`), then UBO screening and `assess()`.
Pre-validation (manager.py ~381-415) already moves the *known* ValueErrors ahead of the INSERT, but any
other exception after the commit (lock timeout past `busy_timeout`, engine error, I/O) leaves:

```
F2  customer rows=[(1, 'active')] screenings=0 risk_assessments=0 alerts=0
F2  retry with same reference: IntegrityError: UNIQUE constraint failed: customers.org_id, customers.reference
```

Consequences: an active customer with no screening and no risk rating; the operator cannot retry with
the same reference; `due_for_review` (manager.py:1010) joins `risk_assessments`, so the customer never
appears in the periodic-review list. Bounded for screening only: `rescreen_all` (engine.py:569-570)
selects every active customer, so the next list refresh screens it; it never gets a risk rating.

## Proposed change (not applied)
Smallest safe option: on any exception after the customer commit, mark the row so it is visible and
does not count as an onboarded customer, then re-raise.

```diff
--- a/amlkit/cases/manager.py
+++ b/amlkit/cases/manager.py
@@ onboard(...)
-    # --- screen the customer, in both scripts where available --------------
-    all_nats = ...
-    ...  (screening, UBOs, assess)
+    try:
+        # --- screen the customer, in both scripts where available ----------
+        all_nats = ...
+        ...  (screening, UBOs, assess, unchanged)
+    except Exception:
+        with conn:
+            conn.execute(
+                "UPDATE customers SET status='onboarding_incomplete' WHERE id=? AND org_id=?",
+                (customer_id, org_id))
+            audit(conn, actor, "customer.onboarding_incomplete", ..., org_id=org_id)
+        raise
```

Plus: a "Resume onboarding" action (re-run screen + assess for an `onboarding_incomplete` row), and
include `onboarding_incomplete` in the dashboard's attention list. `status` has no CHECK constraint
(db.py:297), so no table rebuild. Alternative: make `onboard` a single transaction (requires `screen()`
and `assess()` to stop committing internally; larger change).

## Test to add
Wrap `manager.screen` to raise once (as the repro does); assert onboard re-raises, the row is
`onboarding_incomplete`, an audit row exists, and `rescreen_all` + resume produce a screening and a
risk assessment.

Severity (lead): LOW. Needs a fault mid-onboard; screening gap closes at the next refresh; rating gap persists.

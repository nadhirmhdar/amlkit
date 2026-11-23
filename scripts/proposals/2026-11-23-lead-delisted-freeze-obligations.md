# HELD: delisted entity behind a pending freeze obligation (DL1c, DL1d)

Status: HELD for human review. Nothing here is applied. It extends §2 of
`scripts/proposals/2026-11-22-lead-evidence-pdf-overlay-and-delisted-decisions.md`
(branch `routine/2026-11-22-lead`), which covers DL1/DL1b (a delisting
cascade-deletes the alert and its `alert_reviews`).

Repro: `repro_lead/dl1c_delisted_freeze_overdue_2026_11_23.py` (scratch SQLite,
no network, exit 0 = all three reproduce). Output on `c42c77c`:

```
DL1c  before delisting: in_scope UN=True OFAC=False; overdue ids=[1]
DL1c  after delisting: freeze rows=[(1, None, 'pending_execution'), (2, None, 'pending_execution')]; in_scope UN=True OFAC=True; overdue ids=[1, 2]
DL1c  delisted UN freeze still overdue/pending=True; legacy OFAC freeze flipped into scope=True
DL1d  resolve as 'delisted' refused: Cannot resolve freeze obligation 1 with reason 'delisted': obligation not executed. Use 'false_positive' to resolve without execution.
DL1d  resolve as 'false_positive' on a four-eyes-confirmed (now deleted) true_positive -> ('resolved', 'false_positive')
DL1d  only exit is mislabelling a confirmed match as false_positive=True
```

## What happens

1. **DL1c-a (UN, expected but silent).** The delisted UN obligation stays
   `pending_execution` and is still returned by
   `cases.manager.check_unexecuted_freeze_obligations` (`manager.py:2600-2617`
   selects on status and age only). The MLRO gets an "execute asset freeze"
   email for a person who is no longer listed, with nothing saying so.
2. **DL1c-b (legacy OFAC/EU/UK obligations flip into scope).**
   `sanctions_scope.freeze_obligation_in_scope` (`sanctions_scope.py:45-63`)
   treats `alert_id IS NULL` as "raised manually, in scope". The FK is
   `ON DELETE SET NULL` (`db.py:759`), so when an OFAC entity behind a legacy
   (pre-scope-rule) obligation is delisted, the obligation loses its alert and
   becomes in scope: it now gets the 24h overdue email and is eligible for a
   CNMR. Only legacy rows are affected (new OFAC alerts do not create
   obligations); how many exist in production is unknown.
3. **DL1d (no honest exit).** `resolve_freeze_obligation`
   (`manager.py:2505-2511`) refuses `delisted` unless the freeze was executed,
   and its "confirmed true positive cannot be closed as false positive" guard
   (`manager.py:2519-2524`) reads the alert's status through a LEFT JOIN, which
   is NULL once the alert is deleted. The MLRO's only way to close the
   obligation is therefore to record a four-eyes-confirmed UN match as
   `false_positive`, with no second reviewer.

## Proposed change (not applied)

Best fixed together with the soft-delist option in the 11-22 proposal §2: if
entities are marked `delisted_at` instead of deleted, the alert survives, the
guard keeps working, and the scope check keeps seeing the real dataset. On top
of that:

```diff
--- a/amlkit/cases/manager.py  (resolve_freeze_obligation)
-    # Allow resolving as false_positive without execution
-    if resolution_reason != "false_positive" and row["executed_at"] is None:
+    # false_positive, and delisted when the entity left the list before the
+    # freeze was executed, may close an obligation without execution.
+    if (resolution_reason not in ("false_positive", "delisted")
+            and row["executed_at"] is None):
```

```diff
--- a/amlkit/sanctions_scope.py  (freeze_obligation_in_scope)
-    if row["alert_id"] is None:
-        return True
+    if row["alert_id"] is None:
+        # Manual obligations have no alert from the start. One whose alert was
+        # deleted keeps its origin in the freeze.identified audit row.
+        origin = conn.execute(
+            "SELECT json_extract(detail, '$.alert_id') AS a FROM audit_log"
+            " WHERE action='freeze.identified' AND object_id=? AND org_id=?",
+            (str(freeze_id), org_id)).fetchone()
+        return origin is None or origin["a"] is None
```

(The audit fallback is only needed if hard delete is kept; `audit_log` columns
are `object_type/object_id/detail` per `db.py:840-849`, and `detail` is assumed
to be the JSON written by `db.audit()`; verify before applying. With soft-delist
it is unneeded.)

Plus: when a refresh delists an entity linked to a `pending_execution`
obligation, notify the MLRO ("listing removed; confirm with the authority and
resolve as delisted") instead of sending the overdue "execute" email.

Tests to add with the fix: the three assertions in the repro, inverted.

Decision needed from Nadhir: whether "delisted before execution" may close an
obligation without an authority reference, or must require `authority_ref`
like `authority_clearance`.

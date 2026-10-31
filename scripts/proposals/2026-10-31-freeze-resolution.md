# HELD: freeze-obligation resolution controls (L-95, L-96, L-97)

Status: HELD for Nadhir. It changes business logic in `amlkit/cases/manager.py`, so the lead may not apply it.
Repro: `repro_lead/checks_2026_10_31.py` (exit 0 = all three reproduce on `401da32`).

## Findings
- **L-95 (FZ1, MEDIUM).** `resolve_freeze_obligation` (`cases/manager.py:1927-1933`) lets one MLRO close a freeze obligation raised by a four-eyes-confirmed true-positive as `false_positive`, without executing it, with empty `authority_ref` and `notes`. The alert stays `true_positive`, so the two records contradict each other. Closing a wrong match without freezing is deliberate (the code comment says so). What is missing is a reason and a second person.
- **L-96 (FZ2, LOW).** `authority_ref` defaults to `""` and is never validated, including for `authority_clearance`.
- **L-97 (skeptic, LOW).** Check-then-act: the status `SELECT` (`manager.py:1917`) and the `UPDATE` (`:1944-1953`) are separate, and the `UPDATE` has no status guard. Two concurrent resolves both succeed. The second overwrites `resolved_by`/`authority_ref`, and two `freeze.resolved` audit rows are written. This is the same idiom as L-66/L-69/L-76/L-77.

## Proposed diff (minimal; not applied)
```diff
--- a/amlkit/cases/manager.py
+++ b/amlkit/cases/manager.py
@@ def resolve_freeze_obligation(
     if resolution_reason not in valid_reasons:
         raise ValueError(...)
+    authority_ref = (authority_ref or "").strip()
+    notes = (notes or "").strip()
+    if resolution_reason == "authority_clearance" and not authority_ref:
+        raise ValueError("authority_clearance requires the authority's reference")
+    if resolution_reason == "false_positive" and len(notes) < 20:
+        raise ValueError("Explain why the confirmed match is a false positive (at least 20 characters)")
@@
     with conn:
-        conn.execute(
+        cur = conn.execute(
             """UPDATE freeze_obligations
                SET status = 'resolved', ...
-               WHERE id = ? AND org_id = ?""",
+               WHERE id = ? AND org_id = ? AND status != 'resolved'""",
             (...),
         )
+        if cur.rowcount != 1:
+            raise ValueError(f"Freeze obligation {freeze_obligation_id} already resolved")
         audit(...)
```
The `with conn:` block must open the transaction before the `UPDATE`. It already does, and the `rowcount` check makes the operation atomic without a separate lock.

## Second approver (decision, not in the diff)
Option A: when the linked alert is `true_positive`, a `false_positive` resolution creates a pending review (reuse `cases/review.py`, like `propose_disposition`), and a different operator must confirm it. `AMLKIT_SINGLE_OPERATOR_MODE` keeps today's behaviour.
Option B: block `false_positive` while the alert is `true_positive`. The MLRO must first re-disposition the alert through four-eyes, and that disposition then closes the obligation.
Lead recommends **B**. It reuses the existing four-eyes path and removes the contradiction, and it needs no new review type.

Not decided here: whether UAE law requires dual approval to lift a freeze. The compliance role has no primary text (`corpus/` absent).

## Tests to add with the fix
- `false_positive` with empty notes -> ValueError; `authority_clearance` with empty ref -> ValueError.
- A second resolve after the first -> ValueError, one audit row (a sequential test is enough once the guard exists).
- Option B: `false_positive` on an obligation whose alert is `true_positive` -> ValueError.

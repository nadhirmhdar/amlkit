# Proposal (HELD for human review): status guard on alert disposition writes (F-1)

Raised by: compliance-specialist 2026-11-24 (from draft PR #411 audit doc, finding 1). Reproduced by the lead on master `f3c8227`.

## Defect
`amlkit/cases/review.py`:
- `propose_disposition` checks `status in ('open','pending_review')` with a SELECT (lines 310-320), then later runs `UPDATE alerts SET status=? ... WHERE id=? AND org_id=?` (line 359) with no status condition.
- `confirm_disposition` checks `status == 'pending_review'` with a SELECT, then runs the same unguarded UPDATE (line 465).

Between check and write the function runs `needs_independent_review` and `single_operator_mode` (both DB reads), and FastAPI serves sync routes from a thread pool, so two operators acting on one alert can interleave.

## Reproduction
`repro_lead/f1_disposition_race_2026_11_24.py` (scratch SQLite, two connections, gap opened by wrapping `needs_independent_review`; no app code changed). Exit 0, on `f3c8227`:
```
F1  op B in the gap: true_positive; freeze rows=[(1, 1, 'pending_execution')]
F1  op A after B: pending_review (no error raised)
F1  op C confirms: false_positive; final alert status=false_positive; freeze rows=[(1, 1, 'pending_execution')]
F1  alert_reviews trail=[('opB', 'propose', 'true_positive'), ('opA', 'propose', 'false_positive'), ('opC', 'confirm', 'false_positive')]
F1  confirmed true_positive overwritten to false_positive with live freeze obligation=True
```
Result: a confirmed UN match ends as a four-eyes "false positive" while its freeze obligation is still `pending_execution`. The `alert_reviews` trail keeps all three decisions, so the record is reconstructable, but the alert's current state is wrong.

## Proposed diff (not applied)
```diff
@@ propose_disposition
         cur = conn.execute(
             """UPDATE alerts SET status=?, disposition=?, reason_code=?,
                independent_review=?, dispositioned_by=?, dispositioned_at=?
-               WHERE id=? AND org_id=?""",
+               WHERE id=? AND org_id=? AND status IN ('open', ?)""",
             (applied_status, narrative.strip() or REASON_CODES[reason_code],
-             reason_code, independent, operator, now, alert_id, org_id),
+             reason_code, independent, operator, now, alert_id, org_id, PENDING),
         )
         if cur.rowcount == 0:
-            raise ReviewError(f"alert {alert_id} not found")
+            raise ReviewError(f"alert {alert_id} not found or already dispositioned")
@@ confirm_disposition
-               WHERE id=? AND org_id=?""",
-            (status, note or REASON_CODES.get(code, code), code, operator, now, alert_id, org_id),
+               WHERE id=? AND org_id=? AND status=?""",
+            (status, note or REASON_CODES.get(code, code), code, operator, now, alert_id, org_id, PENDING),
```
The UPDATE runs inside `with conn:` after the `alert_reviews` INSERT, so raising on `rowcount == 0` rolls back that INSERT too: the loser gets a clear error and writes nothing. Optional hardening: `BEGIN IMMEDIATE` before the check, so the SELECT and the UPDATE sit in one write transaction.

Note: `propose_disposition` today also allows a *second* propose on a `pending_review` alert (status in `('open', PENDING)`); the guard keeps that behaviour. Whether a staged dismissal should be re-proposable at all is a separate question.

## Test to add with the fix
Port the repro into `tests/test_review.py`: wrap `needs_independent_review` as the script does and assert that op A's propose raises `ReviewError` and the alert stays `true_positive`.

## Severity (lead)
LOW-MEDIUM. The interleaving is real (reproduced), and the outcome contradicts the true-positive guard, but the window is milliseconds, needs two operators on the same alert at once, and the audit trail keeps every decision.

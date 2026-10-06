# HELD: rescreen banner (G9), re-alert on decided matches (L-9 / G10 / CS-3), four-eyes legacy fallback

Status: HELD for human review. Lead, 2026-10-06, master `0129848`. Not applied: every fix
below edits route or business logic, which the routine's additive-only rule forbids.
Repro: `repro_lead/checks_2026_10_06.py` (exit 0 = G9 and L-9 both reproduce).

## 1. G9 - "Re-screen all active customers" always reports failure

`amlkit/api/app.py` (`/admin/rescreen`, around line 3712) builds its message from
`outcome['customers']`. `amlkit/match/engine.py:461` `rescreen_all` returns
`{"screened": ..., "alerts": ...}`. The `KeyError` is raised after `rescreen_all`
has run and `db.commit()` has committed, then caught by the route's broad
`except Exception`, so the MLRO sees "Re-screening failed: 'customers'" on
every run even though the rescreen worked and may have raised alerts.

Repro output on `0129848`:
```
G9  rescreen_all keys=['alerts', 'screened'] | route reads outcome['customers']=True -> reproduces=True
```

Proposed diff:
```diff
-        msg = f"Re-screened {outcome['customers']} customer(s)."
+        msg = f"Re-screened {outcome['screened']} customer(s) and beneficial owner(s)."
```
Test that would fail today (add with the fix, not before):
`tests/test_api.py::TestBatchRescreening` should assert
`"Re-screening failed" not in r.text` and `"Re-screened" in r.text`. The current
test asserts only `"admin" in r.text.lower()`, which the error redirect also
satisfies (`tests/test_api.py:1334-1340`).

## 2. L-9 / G10 / CS-3 - rescreen re-alerts matches already decided or in review

`amlkit/match/engine.py:369-375` skips a hit only when an alert for the same
entity and customer/UBO has `status = 'open'`. An alert in `pending_review`
(awaiting the second operator) or already dispositioned gets a new open alert
on every refresh-triggered rescreen.

Repro output on `0129848`:
```
L-9 before=[(1, 'pending_review'), (2, 'false_positive')]
    rescreen_all={'screened': 2, 'alerts': 2}
    after=[(1, 'pending_review'), (2, 'false_positive'), (3, 'open'), (4, 'open')]
```

Two cases with different answers:
- `pending_review`: always a defect. The match is already in the four-eyes
  workflow; a duplicate open alert lets a second operator dismiss it on its own
  and splits the evidence trail. Proposed: treat it like `open`.
- Dismissed (`false_positive`): a policy choice. Re-alerting on every refresh is
  noise (about one refresh per 20h), but suppressing it for ever would hide a
  list entry whose data changed (new DOB, new alias). Proposed: suppress only
  while the entity's `last_seen`-independent content is unchanged, e.g. compare
  the new hit's `score` with the dismissed alert's score and re-alert only when
  it is higher, or when the entity row was modified after the disposition.
  Needs Nadhir's decision.

Minimal diff for the uncontroversial half:
```diff
-                   WHERE a.org_id = ? AND a.entity_id = ? AND a.status = 'open'
+                   WHERE a.org_id = ? AND a.entity_id = ? AND a.status IN ('open', 'pending_review')
```

## 3. #426 four-eyes fix: legacy fallback (informational)

`confirm_disposition` (`amlkit/cases/review.py`, #426) compares operator ids
only when both the proposal and the confirm carry one, else falls back to the
display name. Every proposal staged before #426 deployed has
`alert_reviews.operator_id = NULL`, so for those rows the rename bypass still works:
```
4E  id path: self-confirm after rename refused -> independent review requires a different operator ...
4E  legacy NULL-operator_id row: same person confirmed after rename -> completed
```
Exposure is limited to alerts that were `pending_review` at deploy time. Options:
(a) one-off backfill `UPDATE alert_reviews SET operator_id = (SELECT id FROM operators o WHERE o.org_id = alert_reviews.org_id AND o.name = alert_reviews.operator)` where unambiguous, run before any rename;
(b) a query listing `pending_review` alerts whose proposal has a NULL operator_id,
for the MLRO to re-stage. Option (b) needs no code change.

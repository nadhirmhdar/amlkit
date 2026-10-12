# HELD: require a note when closing a transaction alert (TA1, 2026-10-12)

Status: HELD for Nadhir. Changes business logic in `cases/manager.py`, so the lead may not apply it.

## Defect
`disposition_transaction_alert` (`amlkit/cases/manager.py:822-846`, master `0129848`) accepts an empty or whitespace note. It stores `disposition = NULL` and audits `{"note": ""}`. The web route (`amlkit/api/app.py:2362-2383`) passes the form value straight through. A `large_cash` or `high_risk_country` alert can therefore be closed as `false_positive` by one operator with no recorded reason. The sanctions disposition flow requires a reason.

Repro: `repro_lead/checks_2026_10_12.py` (exit 0 = reproduces):
```
TA1  large_cash alert closed with blank note -> status=false_positive disposition=None -> reproduces=True
```

The "no four-eyes" half of the mlro-user finding is documented as deliberate (docstring at `manager.py:825-827`, pointing to `kyt.py`). This proposal does not change that.

## Proposed diff
```diff
--- a/amlkit/cases/manager.py
+++ b/amlkit/cases/manager.py
@@ def disposition_transaction_alert(
     if status not in ("true_positive", "false_positive"):
         raise ValueError(f"invalid disposition status: {status!r}")
+    if not note.strip():
+        raise ValueError("Add a note explaining why this alert is being closed.")
     with conn:
```
The route already catches `ValueError` and shows it as the error flash, so no route change is needed. Mobile callers of the same function (if any) get the same rule.

## Tests to add with the fix
- blank and whitespace-only note raises `ValueError`, and the alert stays `open`;
- a non-empty note still closes the alert and the audit row carries it.

Check existing tests that call `disposition_transaction_alert` without a note; they need a note added.

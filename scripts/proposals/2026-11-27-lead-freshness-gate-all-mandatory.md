# DS1: freshness gate passes on one fresh mandatory list (HELD for human review)

Raised: skeptic 2026-11-27. Reproduced: lead, `repro_lead/ds1_partial_stale_gate_2026_11_27.py` (exit 0 on master f3c8227).

## Defect
`amlkit/ingest/loader.py:267-297` `datasets_fresh()` returns `True` on the first mandatory, non-FATF
dataset with entities and age within `max_age_hours`. In code only two screenable sources are
mandatory: UN (`un.py:23`, `opensanctions.py:162`) and the UAE Local Terrorist List (`eocn.py:520`,
`opensanctions.py:157`). OFAC/EU/UK are `is_mandatory=False` and never feed the gate (the skeptic's
"OFAC, EU, UK" example does not apply; the real case is UAE list stale + UN fresh, or the reverse).

Repro: UAE list last refreshed 2026-01-01, UN fresh -> `datasets_fresh=True`,
`staleness_report()` breach=True for the UAE list, `onboard()` accepted with no warning.

Mitigations already present: stale entities are not deleted, so names already on the old UAE list
still hit (repro shows `candidates=1`); the dashboard breach banner (`dashboard.html:9-25`) shows.

## Proposed diff (behaviour change: needs Nadhir's decision)
```diff
-    for row in rows:
-        if row["entity_count"] == 0:
-            continue
-        if not row["last_refresh"]:
-            continue
-        try:
-            ts = datetime.fromisoformat(row["last_refresh"])
-            hours = (now - ts).total_seconds() / 3600
-            max_age = row["max_age_hours"] if row["max_age_hours"] else 24
-            if hours <= max_age:
-                return True
-        except (ValueError, TypeError):
-            continue
-
-    return False
+    if not rows:
+        return False
+    for row in rows:
+        if row["entity_count"] == 0 or not row["last_refresh"]:
+            return False
+        try:
+            ts = datetime.fromisoformat(row["last_refresh"])
+        except (ValueError, TypeError):
+            return False
+        hours = (now - ts).total_seconds() / 3600
+        max_age = row["max_age_hours"] if row["max_age_hours"] else 24
+        if hours > max_age:
+            return False
+    return True
```
Update the docstring to "every mandatory screenable dataset". Return the stale keys (or add
`stale_mandatory_keys()`) so `StaleDatasetsError` can name the list, which also fixes HP5's wording
in the same edit.

## Risk of the change
Stricter: one failing adapter (e.g. EOCN page change) blocks all onboarding until fixed. That is the
fail-closed rule onboarding already chose; alternative is "warn, don't block" for a partial outage
(record a `screenings.coverage_note`). Pick one; recommendation: block, matching existing fail-closed.

## Tests to add
- UAE stale + UN fresh -> False; both fresh -> True; existing `tests/test_cases.py:426-471` still pass
  (check `test_ubo_validation.py:50` and any fixture that loads only one mandatory list: they will
  need a second fresh mandatory dataset).
- Land with ST-1 (`2026-11-26-lead-adhoc-screen-stale-notice.md`): same freshness helper drives the
  `/screen` label.

# HELD: ad-hoc screening on stale lists shows no notice (ST-1) + refusal wording (HP5)

Status: HELD for human review. Lead 2026-11-26, master `f3c8227`. No application file edited.

## ST-1 (LOW-MEDIUM)
Onboarding fails closed when no mandatory sanctions dataset is fresh
(`amlkit/cases/manager.py:360-364`, `StaleDatasetsError`). The ad-hoc paths do not:

- `amlkit/match/engine.py:255` `screen()` has no freshness check and `ScreeningResult`
  (`engine.py:66-84`) has no field telling the caller the lists were stale.
- Web `POST /screen` (`amlkit/api/routers/screening.py:59-113`) and mobile `POST /api/v1/screen`
  (`amlkit/api/mobile.py:556`) call it directly.
- `screen.html` has no "lists as of" or stale text. The dashboard's 24-hour-rule banner
  (`dashboard.html:10-25`) is the only warning, and it is not on the page that shows the result.

Repro: `repro_lead/st1_adhoc_screen_on_stale_lists_2026_11_26.py` (exit 0): lists backdated to
2026-01-01, `datasets_fresh()` False, onboard refused, `screen()` returns
`CLEAR 'Zainab Omar Khalid' - 0 candidates` with no stale flag.

Why not refuse like onboarding: an ad-hoc check on old data is still better than none for a
walk-in; the defect is that the CLEAR is not labelled. Recommended fix is a label, not a block.
Nadhir may prefer the block (consistent with onboarding); say which.

### Proposed diff (label option)
```diff
--- a/amlkit/api/routers/screening.py
+++ b/amlkit/api/routers/screening.py
@@ def screen_run(
+    from ..ingest.loader import datasets_fresh
+    lists_stale = not datasets_fresh(db)
     result = screen(
@@
     return render(request, "screen.html", {
         "session": session, "query": name, "result": result, "hits": hits,
+        "lists_stale": lists_stale,
         "low_confidence": len(name.split()) < 2,
--- a/amlkit/web/templates/screen.html
+++ b/amlkit/web/templates/screen.html
@@ (above the result block)
+{% if result and lists_stale %}
+  <div class="alert alert-danger" role="alert"><strong>Sanctions lists are out of date.</strong>
+  This result was checked against lists not refreshed within 24 hours and is not reliable.
+  Re-screen after an MLRO runs Admin &rarr; Refresh sanctions lists now.</div>
+{% endif %}
--- a/amlkit/api/mobile.py
+++ b/amlkit/api/mobile.py
@@ def api_screen(
+    "lists_stale": not datasets_fresh(db),   # add to the JSON response
```
Optionally also record it in the audit row for the ad-hoc screening (`detail` JSON), so the
record shows the result was obtained on stale lists.

### Test to add (sketch)
Register via `_register()`, load one mandatory dataset, `UPDATE datasets SET last_refresh='2026-01-01T00:00:00+00:00'`,
POST `/screen` with a CSRF token; assert 200 and "Sanctions lists are out of date" in the body;
refresh `last_refresh` to now and assert the text is absent. Mobile: assert `lists_stale` is true/false.

## HP5 (LOW, wording)
`manager.py:363` says "Ask an MLRO to run Admin → Refresh sources"; the button is
"Refresh sanctions lists now" (`admin.html:235`, `dashboard.html:23`). One-line change:
```diff
-            "Ask an MLRO to run Admin → Refresh sources"
+            "Ask an MLRO to run Admin → Refresh sanctions lists now"
```
Grep tests for the old string before changing it (`grep -rn "Refresh sources" tests/`).

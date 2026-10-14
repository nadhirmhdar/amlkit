# HELD: blank customer name screens clear (L-53) and unknown sector scores as lowest tier (L-54)

Lead, 2026-10-14. Master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`. Not applied: both fixes change
business logic (`cases/manager.py`, `risk/model.py`, `match/engine.py`), which the routine may not edit.
Repro: `repro_lead/checks_2026_10_14.py` (exit 0 = still reproduces).

## L-53 blank full_name is onboarded and recorded as screened clear (MEDIUM)

Raised by mlro-user (C1, mobile API) and skeptic. Wider than reported: the web form also reaches it,
because `full_name: Form()` is required but `"   "` passes and `app.py:1843` passes `full_name.strip()`,
i.e. `""`, into `onboard()`.

- `datamodel.py:163-165` `validate_name_length` skips falsy values (`if value and ...`).
- `cases/manager.py:258` relies on it; nothing else rejects an empty name.
- `match/engine.py:291` flags `unscreenable` only when the name has letters, so `""` screens as
  `clear=True, unscreenable=False, candidates=0`.

Repro output on `0129848`:
```
EN   blank full_name onboarded id=3 stored='' clear=True unscreenable=False rating=low -> reproduces=True
```

Proposed diff (two layers; either alone closes the onboarding path, both are cheap):

```diff
--- a/amlkit/cases/manager.py
+++ b/amlkit/cases/manager.py
@@ def onboard(
-    validate_name_length("full_name", full_name)
+    if not (full_name or "").strip():
+        raise ValueError("full_name is required")
+    validate_name_length("full_name", full_name)
```
`onboard()` ValueErrors already map to 422 on mobile (`mobile.py:631`) and to a form error on web.

```diff
--- a/amlkit/match/engine.py
+++ b/amlkit/match/engine.py
-    if not blocking_keys(name) and any(ch.isalpha() for ch in name):
+    # No blocking keys means nothing was searched; never report that as clear.
+    # Covers empty/blank names as well as letters with no screenable tokens.
+    if not blocking_keys(name) and (any(ch.isalpha() for ch in name) or not name.strip()):
```
The engine change is the skeptic's "one rule" for the silent-clear family (L-53, CR-12/N4, N3). Before
widening it to digit/symbol-only names, check the existing tests that assert those stay clear.

Tests to add with the fix: `onboard(full_name="")` raises; `POST /api/v1/customers` with `full_name=""`
returns 422; `screen(conn, "")` returns `unscreenable=True`.

Existing data: `SELECT org_id, id, reference FROM customers WHERE trim(full_name)=''` lists any
nameless records already stored; they need a name and a re-screen.

## L-54 unknown sector accepted and scored 5 (LOW)

Raised by mlro-user (C2); skeptic corrected "zero risk" to "default 5 points". `validate_risk_inputs`
(`risk/model.py:85-91`) covers jurisdiction, delivery channel, cash level and structure, but not
sector; `risk/model.py:169-170` falls back to 5 points. A typo of `real_estate` (25) scores 5:

```
SEC  sector real_estate score=25.0 vs 'realestate' score=5.0 stored='realestate' validator_checks_sector=False -> reproduces=True
```

Proposed diff:
```diff
--- a/amlkit/risk/model.py
+++ b/amlkit/risk/model.py
 _ALLOWED_FACTOR_VALUES = (
     ("jurisdiction_tier", "jurisdiction", "points_by_tier"),
     ("delivery_channel", "delivery_channel", "points_by_channel"),
     ("cash_level", "cash_intensity", "points_by_level"),
     ("structure", "structure", "points_by_type"),
+    ("sector", "sector", "points_by_sector"),
 )
@@ def validate_risk_inputs(
     structure: str | None = None,
+    sector: str | None = None,
 ) -> None:
@@
         "structure": structure,
+        "sector": sector,
     }
```
Then pass `sector=` at the call sites (`mobile.py` risk-factors PATCH, `onboard()` if it calls the
validator, and the web onboarding/edit routes). Check first that every value the web sector dropdown
emits is a ruleset key, and list stored sectors that are not:
`SELECT sector, count(*) FROM customers GROUP BY sector`.

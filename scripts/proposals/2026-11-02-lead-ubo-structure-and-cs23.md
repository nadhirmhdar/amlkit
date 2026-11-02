# HELD proposal (lead, 2026-11-02): UBO structure validation (U4 + UBO1) and CS-23 wording

Status: **HELD for human review.** Not applied: both changes edit business logic
(`amlkit/cases/manager.py`, `amlkit/screening/pf.py`), which the routine may not touch.
Repro: `repro_lead/checks_2026_11_02.py` on master `e8ddf26` (exit 0 = all reproduce).
Red-team's U4-only proposal: `scripts/proposals/2026-11-02-new-findings.md` on `routine/2026-11-02-red-team`.

## 1. U4 + UBO1: one validation step in `add_ubo`, plus an iterative walk

Facts on `e8ddf26`:
- `_identified_ownership.eff()` (`amlkit/cases/manager.py:668-677`) recurses once per
  parent level. A 900-level chain works; 1100 raises `RecursionError` in `ownership_state()`.
- `add_ubo` (`amlkit/cases/manager.py:528-604`) validates percentages but not structure:
  no depth bound, no check that the owner is not the customer itself.
- Cycles cannot form today: a parent must already exist when a child is inserted and
  no code path updates `ubo_links.parent_ubo_id` (`grep -rn "UPDATE ubo_links" amlkit` is empty).
  The `eff()` cycle guard is therefore a safety net only; the skeptic's "a loop can be
  entered through the UI" is not reachable.

Proposed diff (sketch):

```diff
--- a/amlkit/cases/manager.py
+++ b/amlkit/cases/manager.py
@@
+MAX_UBO_CHAIN_DEPTH = 20  # real structures are a handful of levels deep
+
 def add_ubo(...):
@@
     with conn:
-        owned = conn.execute(
-            "SELECT 1 FROM customers WHERE id=? AND org_id=?", (customer_id, org_id)
-        ).fetchone()
+        owned = conn.execute(
+            "SELECT canonical_key FROM customers WHERE id=? AND org_id=?", (customer_id, org_id)
+        ).fetchone()
         if owned is None:
             raise ValueError(f"customer {customer_id} not found")
+        if owned[0] and canonical_key(person_name) == owned[0]:
+            raise ValueError("A customer cannot be recorded as its own beneficial owner.")
 
         if parent_ubo_id is not None:
             ...
+            depth, cur = 1, parent_ubo_id
+            while cur is not None:
+                depth += 1
+                if depth > MAX_UBO_CHAIN_DEPTH:
+                    raise ValueError(
+                        f"Ownership chains deeper than {MAX_UBO_CHAIN_DEPTH} levels are not supported.")
+                cur = conn.execute(
+                    "SELECT parent_ubo_id FROM ubo_links WHERE id=? AND org_id=?", (cur, org_id)
+                ).fetchone()[0]
@@ def _identified_ownership(rows) -> float:
-    def eff(r) -> float:
-        if r["id"] in eff_cache:
-            return eff_cache[r["id"]]
-        eff_cache[r["id"]] = 0.0  # cycle guard
-        parent = by_id.get(r["parent_ubo_id"]) if r["parent_ubo_id"] is not None else None
-        val = max(pct(r), 0.0)
-        if parent is not None:
-            val = val * eff(parent) / 100.0
-        eff_cache[r["id"]] = val
-        return val
+    def eff(r) -> float:
+        # Iterative: collect the uncached ancestors, then fold from the top down.
+        chain, seen, node = [], set(), r
+        while node is not None and node["id"] not in eff_cache and node["id"] not in seen:
+            seen.add(node["id"]); chain.append(node)
+            pid = node["parent_ubo_id"]
+            node = by_id.get(pid) if pid is not None else None
+        base = eff_cache.get(node["id"], 0.0) if node is not None else None  # cycle -> 0.0
+        for n in reversed(chain):
+            val = max(pct(n), 0.0)
+            if base is not None:
+                val = val * base / 100.0
+            eff_cache[n["id"]] = val
+            base = val
+        return eff_cache[r["id"]]
```

Note the cycle case: today a cycle member's parent evaluates to 0.0 via the guard; in the
sketch a chain that loops back into `seen` treats the loop entry as 0.0 too
(`eff_cache.get(..., 0.0)` returns 0.0 because the node is in `seen`, not the cache).
Keep that equivalence under test.

Name matching on `canonical_key` alone misses "Gulf Holdings LLC" vs "Gulf Holdings L.L.C."
if canonicalisation does not fold them; acceptable as a first guard, with the web form
surfacing the error as a banner (routes already map `ValueError` from `add_ubo`).

Tests to add with the fix (they fail on master today, so they are not committed here):
- `add_ubo` with the customer's own name -> `ValueError`.
- a chain of `MAX_UBO_CHAIN_DEPTH + 1` -> `ValueError` on the last insert.
- `_identified_ownership` on 5,000 synthetic chained rows returns 100.0 without RecursionError
  (rows built in memory; no DB needed), and an artificial 3-cycle returns the same value as before.
- existing `tests/test_ubo_property.py` must still pass unchanged.

## 2. CS-23: dataset check must come before the terrorism / proliferation branches

`obligation_note()` (`amlkit/screening/pf.py:89-114`) returns the freeze wording for
`terrorism`/`proliferation` before line 108 looks at the dataset. An OFAC SDGT-only entry
therefore says "Freeze without delay" while `is_uae_freeze_list('us_ofac_sdn')` is False
and the freeze gate raises no obligation.

```diff
 def obligation_note(categories: set[str], dataset: str | None = None) -> str:
+    non_uae = bool(dataset) and not is_uae_freeze_list(dataset)
-    if "proliferation" in categories:
+    if "proliferation" in categories and not non_uae:
         return (...)
-    if "terrorism" in categories:
+    if "terrorism" in categories and not non_uae:
         return (...)
-    if dataset and not is_uae_freeze_list(dataset):
+    if non_uae:
+        if "proliferation" in categories:
+            return NON_UAE_SANCTIONS_OBLIGATION + (
+                " Proliferation financing is a standalone offence under Federal "
+                "Decree-Law No. 10 of 2025; file via goAML where suspicion arises.")
         return NON_UAE_SANCTIONS_OBLIGATION
```

The proliferation-offence sentence is compliance's suggestion (Law 10/2025 Art 21, unverified);
wording needs Nadhir / the compliance adviser to sign off. Test: `obligation_note({'terrorism'}, 'us_ofac_sdn')`
contains no "freeze without delay"; `obligation_note({'terrorism'}, 'un_consolidated')` still does.

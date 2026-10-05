# Alert queue: category priority is lost past one page (HELD)

Status: HELD for Nadhir's review. Lead 2026-10-05, finding L-18. Raised by compliance-specialist CS-8 and mlro-user G2. Skeptic: CONFIRMED and wider than reported.

## Defect (master `448a19b`)
`amlkit/queries.py:488` `alert_queue` orders in SQL by `a.score DESC` with `LIMIT ? OFFSET ?` (`:540`). It sorts by `CATEGORY_RANK` only afterwards, within the returned page (`:568-572`). `CATEGORY_RANK` is documented at `:29-31` as "Proliferation first ... should never be buried". Once more than `limit` alerts are open, a lower-scoring proliferation or terrorism alert falls outside the first page:

- Mobile `GET /api/v1/alerts`, paged in #402.
- The web `/alerts` queue (`app.py:2544`, default `limit=200`, when there is no category filter).
- The dashboard (`queries.py:314-315`, `DASHBOARD_ALERT_CAP=200`).

Repro: `repro_skeptic/queue_paging_category.py` on `routine/2026-10-05-skeptic`. The lead re-ran it on `448a19b`, exit 0:
```
page1 200 {'sanction': 200} | page2 7 {'proliferation': 1, 'sanction': 6}
```

## Proposed diff (not applied)
Rank the category in SQL so that `LIMIT/OFFSET` cut an already category-ordered list. Category derives from JSON `topics`/`programs` (`_category`, `:185`), and `classify_programs` maps program names in Python. The smallest safe change is to fetch the whole status-filtered set when sorting by score, then sort and slice in Python. That is the path the `category` filter already takes (`:545-546`):

```diff
-    for row in conn.execute(sql, (*params, -1 if category else limit, 0 if category else offset)):
+    score_sort = sort_by not in ("age_asc", "age_desc")
+    fetch_all = bool(category) or score_sort
+    for row in conn.execute(sql, (*params, -1 if fetch_all else limit, 0 if fetch_all else offset)):
 ...
-    if category:
-        out = [a for a in out if a["category"] == category][offset:offset + limit]
-    # When using age-based sorting, preserve SQL sort order; otherwise apply category/score sort
-    if sort_by not in ("age_asc", "age_desc"):
-        out.sort(key=lambda a: (CATEGORY_RANK.get(a["category"], 9), -a["score"]))
+    if category:
+        out = [a for a in out if a["category"] == category]
+    if score_sort:
+        out.sort(key=lambda a: (CATEGORY_RANK.get(a["category"], 9), -a["score"], a["id"]))
+    if fetch_all:
+        out = out[offset:offset + limit]
     return out
```
Cost: the score-sorted path loads every alert of that status for the org (it already does so when filtering by category). If that is too slow for large orgs, the alternative is a stored `category_rank` column on `alerts`, set at insert time. That is a schema change and needs a migration.

Also fix the mobile docstring (`mobile.py:1185`, "highest score first") to say "category, then score".

Test to add with the fix: 204 alerts at score 0.85 or higher plus one proliferation alert at 0.80. Assert that it is row 0 on page 1 of both `alert_queue(limit=200)` and `GET /api/v1/alerts?limit=200`.

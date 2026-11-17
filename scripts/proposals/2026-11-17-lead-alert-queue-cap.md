# HELD proposal: alert queue and alert CSV exports silently stop at 200 (L-156 / QU1)

Status: **HELD for human review** (route logic; lead routine is additive-only).
Master: `9219e2623b3a3ba7e73a20e44c703ab80df7e900`. Repro: `repro_lead/checks_2026_11_17.py`.

## Defect
`queries.alert_queue(..., limit=200, offset=0)` (`amlkit/queries.py:480-483`) caps at 200.
Three callers pass neither `limit` nor `offset` and show no notice:

| Caller | File:line | Effect with 205 open alerts (lead run) |
|---|---|---|
| Web queue `/alerts` (and `alert_queue_grouped`, `queries.py:592-597`) | `api/routers/alerts.py:138,147` | 200 rows, no notice; dashboard says "205 waiting" |
| Web export `/alerts.csv` (default `status=all`, so closed alerts count too) | `api/routers/alerts.py:281` | 200 rows |
| Mobile export `/api/v1/alerts.csv` | `api/mobile.py:1492` | 200 rows |

Only the mobile list (`mobile.py:1331`) pages. The export audit row records `rows: 200`,
so the audit trail itself shows the truncated count as if complete.

Because ordering is category priority first, the 200 shown are the highest priority, which
limits harm in the queue. The CSV is worse: with the default `status=all` any org with more
than 200 alerts in its history (open + closed) gets an incomplete export, which is the file
an inspector or auditor would be handed.

## Proposed diff (sketch)
```diff
--- a/amlkit/api/routers/alerts.py
+++ b/amlkit/api/routers/alerts.py
@@ def alerts(request: Request, db: DB, status: str = "open", sort: str = "age_asc", group_by: str = "",
-           category: str = ""):
+           category: str = "", page: int = 1):
+    PAGE = 200
+    page = max(1, page)
@@
-    queue = queries.alert_queue(db, session.org_id, status=effective_status, sort_by=sort_by, category=cat)
+    total = queries.alert_queue_count(db, session.org_id, status=effective_status, category=cat)
+    queue = queries.alert_queue(db, session.org_id, status=effective_status, sort_by=sort_by,
+                                category=cat, limit=PAGE, offset=(page - 1) * PAGE)
     ...
-        "session": session, "alerts": queue, ...
+        "session": session, "alerts": queue, "total": total, "page": page, "page_size": PAGE, ...
@@ def alerts_csv(...):
-    queue = queries.alert_queue(db, session.org_id, status=None if status == "all" else status,
-                                category=cat)
+    queue = queries.alert_queue(db, session.org_id, status=None if status == "all" else status,
+                                category=cat, limit=None)  # new: None = uncapped
--- a/amlkit/api/mobile.py
+++ b/amlkit/api/mobile.py
@@ def api_alerts_csv(db: DB, session: Session, status: str = "all"):
-    queue = queries.alert_queue(db, session.org_id, status=None if status == "all" else status)
+    queue = queries.alert_queue(db, session.org_id, status=None if status == "all" else status,
+                                limit=None)
```
Template (`alerts.html`): when `total > alerts|length`, show
"Showing {{ (page-1)*page_size + 1 }}-{{ ... }} of {{ total }}" with previous/next links,
`role="status"`, same styling as the existing `unknown_filter` line. Grouped view: same
notice (or page by customer). `alert_queue_count` is a new read-only helper taking `org_id`
(same WHERE as `alert_queue`).

`alert_queue` pages in Python (`queries.py:554`: `ranked[offset:offset + max(0, int(limit))]`),
so `limit=-1` would return **nothing**. Add `limit: int | None = 200` and slice
`ranked[offset:]` when `limit is None`:
```diff
-    page_ids = [t[0] for t in ranked[offset:offset + max(0, int(limit))]]
+    end = None if limit is None else offset + max(0, int(limit))
+    page_ids = [t[0] for t in ranked[offset:end]]
```

## Tests to add with the fix
- 205 open alerts: `/alerts` shows the notice and 200 rows; `/alerts?page=2` shows 5.
- `/alerts.csv` and `/api/v1/alerts.csv` return 205 data rows; audit `rows` = 205.
- Ordering: no proliferation/terrorism/sanction alert appears on page 2 while a lower
  category is on page 1 (existing invariant).

## Open question for Nadhir
Is an uncapped CSV acceptable for very large orgs, or stream it (`StreamingResponse`)?
Search by customer name in the queue (mlro-user's `?q=`) is a separate UX request, not part
of this fix.

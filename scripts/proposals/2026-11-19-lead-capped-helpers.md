# HELD: L-162 — 200-row caps outside the screening-alert queue (extends 2026-11-17-lead-alert-queue-cap.md)

Status: **HELD** (queries/routes). Master `cdf3801`. Repro: `repro_lead/checks_l162_caps_2026_11_19.py`
(250 rows seeded per table; output in the lead report, 4/4 reproduce).

| Id | Where | Effect at 250 rows |
|---|---|---|
| T1 | `queries.transaction_alert_queue` (`queries.py:912-945`, `limit=200`), mobile `/api/v1/transaction-alerts` (`mobile.py:1410-1416`), web alerts page | 200 returned, no total, no paging params |
| T2 | `queries.dashboard` (`queries.py:344-345`): `sorted(transaction_alert_queue(..., status="open"), key=created_at)[:5]` over a **newest-first** capped list | "Oldest open transaction alerts" shows the 196th-200th newest (2026-02-23..27), not the oldest (2026-01-01..05). Wrong output, not just truncation |
| A1 | `queries.adverse_media_queue` (`queries.py:1184-1215`), mobile `/api/v1/adverse-media` (`mobile.py:1401-1407`) | 200 of 250 |
| X1 | `queries.transactions_for_customer` (`queries.py:903-909`), case file and mobile customer transactions (`mobile.py:1088-1094`) | 200 of 250 |

## Proposed diff (minimal; T2 is the one that is wrong rather than incomplete)
```diff
--- a/amlkit/queries.py
+++ b/amlkit/queries.py
@@ def dashboard(
-    txn_alerts = transaction_alert_queue(conn, org_id, status="open")
-    oldest_open_txn = sorted(txn_alerts, key=lambda a: a["created_at"])[:5]
+    txn_alerts = transaction_alert_queue(conn, org_id, status="open")
+    oldest_open_txn = transaction_alert_queue(
+        conn, org_id, status="open", limit=5, oldest_first=True)
@@ def transaction_alert_queue(
-    conn: sqlite3.Connection, org_id: int, status: str | None = "open", limit: int = 200,
-    customer_id: int | None = None
+    conn: sqlite3.Connection, org_id: int, status: str | None = "open", limit: int = 200,
+    customer_id: int | None = None, oldest_first: bool = False, offset: int = 0,
@@
-    sql += " ORDER BY ta.created_at DESC LIMIT ?"
+    sql += (" ORDER BY ta.created_at ASC, ta.id ASC" if oldest_first
+            else " ORDER BY ta.created_at DESC, ta.id DESC") + " LIMIT ? OFFSET ?"
@@
-    for row in conn.execute(sql, (*params, limit)):
+    for row in conn.execute(sql, (*params, limit, offset)):
```
Mobile (T1, A1, X1): add `limit: int = Query(200, ge=1, le=500)`, `offset: int = Query(0, ge=0)`
and return `{"...": rows, "total": <COUNT(*) with same filters>, "next_offset": offset+len(rows) if more}`,
mirroring whatever shape is chosen for L-156. Web: show "Showing 200 of N" with a link to the
next page or CSV, as proposed for L-156.

## Tests
```python
def test_dashboard_oldest_txn_alerts_are_oldest_even_past_cap(seeded_250):
    d = queries.dashboard(conn, oid)
    assert [a["created_at"][:10] for a in d["oldest_open_transaction_alerts"]] == [
        "2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]

def test_mobile_transaction_alerts_reports_total(client_mobile, seeded_250):
    r = client_mobile.get("/api/v1/transaction-alerts")
    assert r.json()["total"] == 250
```

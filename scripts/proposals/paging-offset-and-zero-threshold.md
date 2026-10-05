# Unbounded paging offsets give a 500; a zero alert threshold is silently read as 0.85 (HELD)

Status: HELD for Nadhir's review. Lead 2026-10-05, findings L-21 and L-22. Raised by red-team N1 and N2. Skeptic: both CONFIRMED, Low; N1 is wider than reported.

## L-21: OverflowError on a huge offset/page (master `448a19b`)
- `mobile.py:1192` clamps `offset` below only. `alert_queue` passes it to SQLite, which raises `OverflowError`, and the request returns HTTP 500.
- `app.py:2958` (feedback list) and `app.py:3019` (`/audit`) compute `offset = (page - 1) * 50` with no upper bound on `page`.

The lead re-ran `repro_skeptic/offset_overflow.py` on `448a19b`, exit 0:
```
alert_queue OverflowError: Python int too large to convert to SQLite INTEGER
audit_trail OverflowError: Python int too large to convert to SQLite INTEGER
feedback_list OverflowError: Python int too large to convert to SQLite INTEGER
```
Only authenticated users can trigger it. Impact is a 500 and log noise; no data is exposed.

Proposed diff (not applied):
```diff
--- a/amlkit/api/mobile.py
-    offset = max(0, int(offset))
+    offset = max(0, min(int(offset), 2**31))
--- a/amlkit/api/app.py   (both sites)
-    offset = (page - 1) * per_page
+    page = max(1, min(page, 10**6))
+    offset = (page - 1) * per_page
```

## L-22: threshold 0.0 is stored but read back as the default
`mobile.py:1437` accepts `0.0`. `queries.org_alert_threshold` returns `0.0`. Six call sites then use `... or DEFAULT_THRESHOLD` (`mobile.py:531,614,910`; `app.py:1690,1848,2286`), and `0.0` is falsy. The audit log records "threshold 0.0" while screening runs at 0.85. Code-read only; not run end to end.

Proposed diff (not applied): replace each `x or DEFAULT_THRESHOLD` with `DEFAULT_THRESHOLD if x is None else x`. Also consider a floor (for example 0.5) on both the web and mobile setters, because a near-zero threshold floods the queue. Whether a floor is wanted is a product decision.

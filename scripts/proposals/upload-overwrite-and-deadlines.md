# HELD: document upload overwrite (L-43) and compliance-deadline API gaps (L-44)

Status: HELD for human review. Both fixes change existing route or storage logic, which the lead routine may not edit. Lead 2026-10-10, master `0129848`.

## 1. L-43: a same-name upload overwrites the earlier document (red-team U1, skeptic CONFIRMED)

**Defect.** `storage._gcs_object_name` (`amlkit/storage.py:66-67`) and `_upload_local` (`:101-106`) key the stored object by `{org}/{customer}/{filename}`. A second upload of `scan.pdf` for the same customer writes over the first. The first `documents` row keeps its original sha256, but the bytes it points at are now the second file. The only caller is the mobile route `POST /api/v1/customers/{id}/documents` (`mobile.py:1117`).

**Repro.** `repro_skeptic/upload_overwrite.py` (branch `routine/2026-10-10-skeptic`), re-run by the lead on `0129848`:
```
same stored_path: True | first doc's recorded sha256 matches stored bytes: False
'..' IsADirectoryError
'' IsADirectoryError
exit 0
```

**Proposed diff.** Make the key unique and keep the user's filename as display metadata only. This also removes the `..` / empty-name / ENAMETOOLONG 500s (U2):
```diff
--- a/amlkit/storage.py
+++ b/amlkit/storage.py
@@ def upload(content: bytes, org_id: int, customer_id: int, filename: str) -> str:
+    import secrets
+    from pathlib import PurePath
+    suffix = PurePath(filename).suffix.lower()[:10]   # ".pdf", "" for "..", etc.
+    filename = f"{secrets.token_hex(16)}{suffix}"      # unique key; original name lives in documents.filename
```
Callers already store the original filename in `documents`. Download headers should use the `documents` row's name, not the basename of `stored_path`. Check `mobile.py:1156-1160` before applying.

**Test to add with the fix:** upload `scan.pdf` twice for one customer. Assert two distinct `stored_path`s, and assert that each download's sha256 equals its row's recorded sha256.

**Open fact (BLOCKED for the routine):** check whether the production documents bucket has object versioning. If it does, earlier overwrites can be recovered and severity drops to Low. If it does not, any overwrite that has already happened is permanent. Nadhir can check this with one `gsutil versioning get gs://<bucket>`.

## 2. L-44: the compliance-deadline API (mlro E1/E2 and skeptic's "team missed" #1)

**Defects** (`amlkit/api/app.py:4463-4527`), each reproduced by `repro_lead/checks_2026_10_10.py` (exit 0):
- PATCH accepts `due_date`, `description` and `recurrence` but only updates `title`. A due-date correction returns 200 and changes nothing.
- PATCH and DELETE write no audit row; only create is audited.
- None of the routes has a role gate (session and CSRF only), so an officer can delete the MLRO's deadlines. This was established by reading the code, not by running it.
- `due_date` and `recurrence` are unvalidated free text. Because `is_overdue` compares strings (`app.py:4452`), a value like `31/12/2026` is never shown as overdue.
- No template posts to `/compliance/deadlines`, so the calendar page cannot create a deadline (E1). No reminder path reads this table (only `queries.py:1291-1310`), so E2's "may break reminders" has no consumer today.

**Proposed diff (sketch):**
```diff
 class _DeadlineCreate(BaseModel):
     title: str = ""
-    due_date: str = ""
+    title: constr(min_length=1, max_length=200)
+    due_date: datetime.date
     description: str = ""
-    recurrence: str = "none"
+    recurrence: Literal["none", "monthly", "quarterly", "annually"] = "none"
@@ compliance_deadlines_update
-    if body.title:
-        db.execute("UPDATE compliance_deadlines SET title=? WHERE id=? AND org_id=?", ...)
-        db.commit()
+    changes = body.model_dump(exclude_none=True)
+    if changes:
+        sets = ", ".join(f"{k}=?" for k in changes)        # keys come from the model, not the client
+        db.execute(f"UPDATE compliance_deadlines SET {sets} WHERE id=? AND org_id=?",
+                   (*changes.values(), deadline_id, session.org_id))
+        audit(db, session.operator_name, "compliance.deadline_updated", "compliance_deadline",
+              deadline_id, {"before": existing, "after": changes}, org_id=session.org_id)
+        db.commit()
@@ compliance_deadlines_delete
+    audit(db, session.operator_name, "compliance.deadline_deleted", "compliance_deadline",
+          deadline_id, {"before": existing}, org_id=session.org_id)
```
Add an MLRO role check to create, update and delete, matching `/audit/export`. Add a small create form to `compliance_calendar.html`. Check the allowed `recurrence` values against the tests in `tests/test_t15_compliance_calendar.py` and `tests/test_p21_compliance_cal.py` before tightening them.

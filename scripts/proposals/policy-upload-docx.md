# Proposal (HELD): policy upload promises DOCX but the route rejects every real DOCX

Finding: mlro-user P1 (2026-10-13), strengthened by the skeptic. Lead id **L-52**, severity LOW-MEDIUM.
Repro: `repro_lead/checks_2026_10_13.py` (exit 0 = reproduces) on master `0129848`.

## Defect
- `web/templates/policies.html:42-43` labels the field "PDF or DOCX, max 10MB", `accept=".pdf,.docx"`.
- `cases/manager.py:2347` `upload_policy` accepts `.pdf` and `.docx`.
- But `api/app.py:3848-3850` runs `validation.validate_file_mime` first, and its allow-list
  (`validation.py:11-15`) is PDF, PNG and JPEG only. A DOCX is a zip (`PK\x03\x04`), so it is always
  refused with "Allowed types: PDF, PNG, JPEG.". The route wins; DOCX policies can never be stored.

## Options (Nadhir to pick)
**(a) Support DOCX for policies only (recommended if firms keep policies in Word).**
Do NOT add the zip signature to the shared `ALLOWED_MIME_TYPES`: customer documents use the same
validator and would then accept arbitrary zips. Add a policy-specific check instead:

```diff
--- a/amlkit/validation.py
+++ b/amlkit/validation.py
@@
+DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
+
+
+def validate_policy_file(content: bytes, filename: str) -> str:
+    """PDF via validate_file_mime, or a genuine DOCX (zip holding word/document.xml)."""
+    if filename.lower().endswith(".docx"):
+        import io, zipfile
+        if not content.startswith(b"PK\x03\x04"):
+            raise ValueError(f"File content is not a DOCX: {filename}")
+        try:
+            with zipfile.ZipFile(io.BytesIO(content)) as z:
+                names = set(z.namelist())
+        except zipfile.BadZipFile:
+            raise ValueError(f"File content is not a DOCX: {filename}")
+        if "word/document.xml" not in names or "[Content_Types].xml" not in names:
+            raise ValueError(f"File content is not a DOCX: {filename}")
+        return DOCX_MIME
+    mime = validate_file_mime(content, filename)
+    if mime != "application/pdf":
+        raise ValueError(f"Only PDF and DOCX allowed: {filename}")
+    return mime
--- a/amlkit/api/app.py   (policy upload route, ~3848)
-        from ..validation import validate_file_mime
+        from ..validation import validate_policy_file
         try:
-            detected_mime = validate_file_mime(file_content, file.filename or "upload.pdf")
+            detected_mime = validate_policy_file(file_content, file.filename or "upload.pdf")
```
Check the policy download route serves the stored MIME (DOCX must go out as `attachment`, `nosniff`,
which mlro-user saw for PDF). Add a test with a stdlib-built DOCX (see the repro) and a zip without
`word/document.xml` (must be refused). Do the size check (`MAX_POLICY_SIZE_BYTES`) before opening the zip.

**(b) PDF only.** Change the label to "File (PDF, max 10MB)", `accept=".pdf"`, and the manager message
and suffix check at `manager.py:2346-2347` to PDF only. Smallest change; no new parser surface.

Either way the two layers then agree. Not applied: it changes route and business logic (rule 3).

## Related (skeptic, 2026-10-13)
Customer document upload (`mobile.py:1088-1128`) has no size cap while policies cap at 10 MB
(`manager.py:2232`, checked at `:2350`); that is red-team U3 / mlro DOC1, already HELD. A single
upload validator returning (mime, canonical extension, safe filename) would close P1, U2 and U3 together.

# HELD: findings from the 2026-10-10 run (not applied; additive-only)
Evidence: reports/daily/2026-10-10/evidence/probe_upload_on_0129848.txt (probe: repro_redteam/probe_upload.py)

## U1 Same-name upload silently replaces the earlier blob (storage.py `_upload_local` / `_upload_gcs`)
Blobs are keyed `{org}/{customer}/{filename}`. Uploading `same.pdf` twice leaves two `documents` rows and two audit rows with different sha256, but one object: downloading the first document returns the second file's bytes (recorded sha256 `2f618e3d83b2...`, served sha256 `56725b400814...`). For a KYC evidence store this lets a later upload overwrite earlier evidence without a trace in the file itself.
```diff
-    dest = dest_dir / filename
+    dest = dest_dir / f"{int(time.time()*1000)}-{secrets.token_hex(4)}-{filename}"
```
(same for the GCS object name), or key by sha256. On download, verify `sha256(content) == documents.sha256` and fail loudly on mismatch.

## U2 Filename edge cases crash with HTTP 500 (mobile.py `api_customer_upload_document`)
`Path(file.filename).name` yields `..` for `..` and `""` for `.`; `_upload_local` then writes to a directory (IsADirectoryError). A 300-character name raises ENAMETOOLONG. Proposal: reject names that are empty, `.` or `..`, longer than 200 characters, or contain control characters/NUL/backslashes, with a 400.

## U3 Extension not constrained, no size cap, `doc_type` unvalidated
`validate_file_mime` only checks the extension when it is pdf/png/jpg/jpeg, so PNG- or PDF-magic files named `.html`, `.svg`, `.php` or `x‮gnp.exe` are accepted. Downloads are forced to `application/octet-stream` with `attachment` and `nosniff`, which contains it. No upload size limit: a 40 MB body was read fully into memory (`file.file.read()`) and accepted in 1.0 s. `doc_type` accepts any string (4 KB and an HTML payload accepted). Proposal: allow-list extensions to the detected type, cap bodies (for example 10 MB, checked while streaming), allow-list `doc_type`.

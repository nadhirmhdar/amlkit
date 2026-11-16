# HELD: finding from the 2026-10-13 run (not applied; additive-only)

## G1 GCS download/delete do not pin the bucket or prefix (storage.py `_download_gcs`, `_delete_gcs`) -- code reading only, not exercised (no GCS credentials)
Both functions take the bucket and object name from the `stored_path` value (`gs://<bucket>/<object>`) with no check against `GCS_BUCKET` or the `documents/{org}/{customer}/` or `policies/{org}/` prefix. Today `stored_path` is only written by `upload()`/`upload_policy()`, so this is defence in depth: a tampered or restored `documents`/`policies` row could make the service account read or delete an object in any bucket it can reach, and `purge_expired` would delete it.
```diff
 def _parse_gs(stored_path, expected_prefix):
     without_scheme = stored_path[len("gs://"):]
     bucket_name, _, obj_name = without_scheme.partition("/")
+    if bucket_name != _GCS_BUCKET or not obj_name.startswith(expected_prefix):
+        raise ValueError("stored_path is outside this deployment's document store")
     return bucket_name, obj_name
```
The local backend has the same shape (`Path(stored_path).read_bytes()` / `.unlink()` with no confinement to `DOCS_DIR`).

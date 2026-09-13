"""Document storage abstraction.

Two backends, selected by environment:

* **GCS** (production) — when `GCS_BUCKET` is set. Objects are stored at
  `gs://{bucket}/documents/{org_id}/{customer_id}/{filename}`. Cloud Run
  containers are ephemeral; any file written to the local container disk is
  lost the moment the instance is recycled. GCS is the only durable store.

* **Local** (development) — falls back to the local filesystem under
  `DOCS_DIR` when `GCS_BUCKET` is not set. Never use this in a deployment
  where the app runs as a container.

The `stored_path` column on the `documents` table holds either:
  - A `gs://` URI  (GCS backend)
  - An absolute local filesystem path (local backend)

The download path checks the prefix and routes accordingly, so old local
rows and new GCS rows coexist without a migration.
"""

from __future__ import annotations

import os
from pathlib import Path

from .db import DB_PATH

DOCS_DIR = DB_PATH.parent / "documents"

_GCS_BUCKET: str | None = os.environ.get("GCS_BUCKET")
_GCS_PREFIX = "documents"


def _gcs_client():
    from google.cloud import storage
    return storage.Client()


def upload(content: bytes, org_id: int, customer_id: int, filename: str) -> str:
    """Store document content and return the stored_path to record in the DB."""
    if _GCS_BUCKET:
        return _upload_gcs(content, org_id, customer_id, filename)
    return _upload_local(content, org_id, customer_id, filename)


def download(stored_path: str) -> bytes:
    """Retrieve document bytes from wherever stored_path points."""
    if stored_path.startswith("gs://"):
        return _download_gcs(stored_path)
    return Path(stored_path).read_bytes()


def delete(stored_path: str) -> None:
    """Delete a document from wherever stored_path points.

    Silently succeeds if the file/blob doesn't exist (idempotent).
    Raises OSError for other failures (e.g., permission denied).
    """
    if stored_path.startswith("gs://"):
        _delete_gcs(stored_path)
    else:
        Path(stored_path).unlink(missing_ok=True)


def _gcs_object_name(org_id: int, customer_id: int, filename: str) -> str:
    return f"{_GCS_PREFIX}/{org_id}/{customer_id}/{filename}"


def _upload_gcs(content: bytes, org_id: int, customer_id: int, filename: str) -> str:
    client = _gcs_client()
    bucket = client.bucket(_GCS_BUCKET)
    blob = bucket.blob(_gcs_object_name(org_id, customer_id, filename))
    blob.upload_from_string(content)
    return f"gs://{_GCS_BUCKET}/{blob.name}"


def _download_gcs(stored_path: str) -> bytes:
    # stored_path: gs://bucket/documents/org_id/customer_id/filename
    without_scheme = stored_path[len("gs://"):]
    bucket_name, _, obj_name = without_scheme.partition("/")
    client = _gcs_client()
    blob = client.bucket(bucket_name).blob(obj_name)
    return blob.download_as_bytes()


def _delete_gcs(stored_path: str) -> None:
    # stored_path: gs://bucket/documents/org_id/customer_id/filename
    from google.cloud.exceptions import NotFound

    without_scheme = stored_path[len("gs://"):]
    bucket_name, _, obj_name = without_scheme.partition("/")
    client = _gcs_client()
    blob = client.bucket(bucket_name).blob(obj_name)
    try:
        blob.delete()
    except NotFound:
        # Idempotent: already deleted
        pass


def _upload_local(content: bytes, org_id: int, customer_id: int, filename: str) -> str:
    dest_dir = DOCS_DIR / str(org_id) / str(customer_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_bytes(content)
    return str(dest)


# ------------------------------------------------------------------------
# Policy Document Storage (Phase 4 enhancement)
# ------------------------------------------------------------------------

POLICIES_DIR = DB_PATH.parent / "policies"


def upload_policy(content: bytes, org_id: int, filename: str) -> str:
    """Store policy document content and return stored_path.

    Policies are org-wide (no customer_id). Stored at:
        - Local: data/policies/{org_id}/{filename}
        - GCS: gs://{bucket}/policies/{org_id}/{filename}
    """
    if _GCS_BUCKET:
        return _upload_policy_gcs(content, org_id, filename)
    return _upload_policy_local(content, org_id, filename)


def download_policy(stored_path: str) -> bytes:
    """Retrieve policy bytes from wherever stored_path points.

    Same backend-agnostic download as regular documents.
    """
    if stored_path.startswith("gs://"):
        return _download_gcs(stored_path)
    return Path(stored_path).read_bytes()


def _upload_policy_local(content: bytes, org_id: int, filename: str) -> str:
    dest_dir = POLICIES_DIR / str(org_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_bytes(content)
    return str(dest)


def _upload_policy_gcs(content: bytes, org_id: int, filename: str) -> str:
    client = _gcs_client()
    bucket = client.bucket(_GCS_BUCKET)
    object_name = f"policies/{org_id}/{filename}"
    blob = bucket.blob(object_name)
    blob.upload_from_string(content)
    return f"gs://{_GCS_BUCKET}/{blob.name}"

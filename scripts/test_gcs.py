#!/usr/bin/env python3
"""Verify GCS bucket connectivity for amlkit.

Usage:
    export GCS_BUCKET=your-bucket-name
    python scripts/test_gcs.py

Tests: bucket access, object write, object read, object delete.
Exits 0 on success, 1 on any failure.
"""

from __future__ import annotations

import os
import sys
import time

GCS_BUCKET = os.environ.get("GCS_BUCKET")


def main() -> int:
    if not GCS_BUCKET:
        print("ERROR: GCS_BUCKET environment variable is not set.", file=sys.stderr)
        print("  export GCS_BUCKET=your-bucket-name", file=sys.stderr)
        return 1

    try:
        from google.cloud import storage
        from google.cloud.exceptions import NotFound
    except ImportError:
        print("ERROR: google-cloud-storage is not installed.", file=sys.stderr)
        print("  pip install google-cloud-storage>=2.18", file=sys.stderr)
        return 1

    print(f"Testing GCS connectivity to bucket: {GCS_BUCKET}")

    client = storage.Client()

    # 1. Bucket exists and is accessible
    print("  [1/4] Checking bucket access...", end=" ", flush=True)
    try:
        bucket = client.bucket(GCS_BUCKET)
        bucket.reload()
        print(f"OK  (location: {bucket.location}, storage class: {bucket.storage_class})")
    except NotFound:
        print(f"FAIL\nERROR: Bucket '{GCS_BUCKET}' does not exist.", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"FAIL\nERROR: {exc}", file=sys.stderr)
        return 1

    # 2. Write a test object
    test_key = f"amlkit-connectivity-test/{int(time.time())}.txt"
    test_content = b"amlkit GCS connectivity test"
    print(f"  [2/4] Writing test object ({test_key})...", end=" ", flush=True)
    try:
        blob = bucket.blob(test_key)
        blob.upload_from_string(test_content)
        print("OK")
    except Exception as exc:
        print(f"FAIL\nERROR: Upload failed: {exc}", file=sys.stderr)
        return 1

    # 3. Read the object back
    print(f"  [3/4] Reading test object...", end=" ", flush=True)
    try:
        got = bucket.blob(test_key).download_as_bytes()
        if got != test_content:
            print(f"FAIL\nERROR: Read back {got!r}, expected {test_content!r}", file=sys.stderr)
            return 1
        print("OK")
    except Exception as exc:
        print(f"FAIL\nERROR: Download failed: {exc}", file=sys.stderr)
        return 1

    # 4. Delete the test object
    print(f"  [4/4] Deleting test object...", end=" ", flush=True)
    try:
        bucket.blob(test_key).delete()
        print("OK")
    except Exception as exc:
        print(f"FAIL\nERROR: Delete failed: {exc}", file=sys.stderr)
        return 1

    print(f"\nAll checks passed. GCS bucket '{GCS_BUCKET}' is fully accessible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

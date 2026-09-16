"""Tests for amlkit.storage document storage abstraction."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from amlkit import storage
from amlkit.db import connect, upsert_dataset, utcnow


@pytest.fixture()
def conn():
    c = connect(":memory:")
    ds = upsert_dataset(c, "test_list", "Synthetic Test List", is_mandatory=True)
    now = utcnow()
    c.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    c.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           countries, birth_date, gender, topics, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "TEST-001", "Person", "Test Entity", "AE", None, None, "sanctions", "{}", now, now)
    )
    c.commit()
    return c


@pytest.fixture()
def org_id(conn) -> int:
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
        " RETURNING id",
        ("Test Firm", "test-firm", "active", utcnow()),
    ).fetchone()
    conn.commit()
    return row["id"]


class TestStorageDelete:
    """Test storage.delete() for both local and GCS paths."""

    def test_delete_local_path_removes_file(self, tmp_path):
        """delete() removes a local filesystem file."""
        test_file = tmp_path / "test_doc.pdf"
        test_file.write_bytes(b"test content")
        assert test_file.exists()

        storage.delete(str(test_file))

        assert not test_file.exists()

    def test_delete_local_path_missing_file_no_error(self, tmp_path):
        """delete() silently succeeds if local file doesn't exist."""
        missing_file = tmp_path / "nonexistent.pdf"
        assert not missing_file.exists()

        # Should not raise
        storage.delete(str(missing_file))

    @patch('amlkit.storage._gcs_client')
    def test_delete_gcs_path_calls_blob_delete(self, mock_gcs_client):
        """delete() parses gs:// path and calls blob.delete()."""
        mock_client = Mock()
        mock_bucket = Mock()
        mock_blob = Mock()
        mock_gcs_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        gcs_path = "gs://my-bucket/documents/1/123/passport.pdf"
        storage.delete(gcs_path)

        # Verify GCS client was used correctly
        mock_client.bucket.assert_called_once_with("my-bucket")
        mock_bucket.blob.assert_called_once_with("documents/1/123/passport.pdf")
        mock_blob.delete.assert_called_once()

    @patch('amlkit.storage._gcs_client')
    def test_delete_gcs_path_handles_not_found(self, mock_gcs_client):
        """delete() silently succeeds if GCS blob doesn't exist."""
        from google.cloud.exceptions import NotFound

        mock_client = Mock()
        mock_bucket = Mock()
        mock_blob = Mock()
        mock_gcs_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.delete.side_effect = NotFound("blob not found")

        gcs_path = "gs://my-bucket/documents/1/123/missing.pdf"
        # Should not raise
        storage.delete(gcs_path)


class TestPurgeExpiredWithDocuments:
    """Test that purge_expired actually deletes stored documents."""

    @patch('amlkit.storage.delete')
    def test_purge_expired_deletes_gcs_documents(self, mock_storage_delete, conn, org_id):
        """purge_expired calls storage.delete for gs:// document paths."""
        from amlkit.cases.manager import onboard, purge_expired

        # Onboard and attach a GCS document
        res = onboard(conn, org_id=org_id, reference="DOC-1", full_name="Doc Customer")
        cid = res.customer_id
        conn.execute(
            "INSERT INTO documents (customer_id, org_id, doc_type, filename, stored_path, sha256, uploaded_at) "
            "VALUES (?, ?, 'passport', 'passport.pdf', 'gs://prod-bucket/documents/1/456/passport.pdf', 'abc123', datetime('now'))",
            (cid, org_id)
        )
        conn.execute(
            "UPDATE customers SET status='closed', retention_until='2020-01-01' WHERE id=?",
            (cid,)
        )
        conn.commit()

        purge_expired(conn, org_id)

        # Verify storage.delete was called with the GCS path
        mock_storage_delete.assert_called_with("gs://prod-bucket/documents/1/456/passport.pdf")

    @patch('amlkit.storage.delete')
    def test_purge_expired_deletes_local_documents(self, mock_storage_delete, conn, org_id):
        """purge_expired calls storage.delete for local paths."""
        from amlkit.cases.manager import onboard, purge_expired

        res = onboard(conn, org_id=org_id, reference="DOC-2", full_name="Local Doc Customer")
        cid = res.customer_id
        conn.execute(
            "INSERT INTO documents (customer_id, org_id, doc_type, filename, stored_path, sha256, uploaded_at) "
            "VALUES (?, ?, 'emirates_id', 'id.pdf', '/var/data/documents/1/789/id.pdf', 'def456', datetime('now'))",
            (cid, org_id)
        )
        conn.execute(
            "UPDATE customers SET status='closed', retention_until='2020-01-01' WHERE id=?",
            (cid,)
        )
        conn.commit()

        purge_expired(conn, org_id)

        mock_storage_delete.assert_called_with("/var/data/documents/1/789/id.pdf")

    @patch('amlkit.storage.delete')
    def test_purge_expired_logs_delete_failure_and_continues(self, mock_storage_delete, conn, org_id):
        """purge_expired logs storage.delete failures but continues purging."""
        from amlkit.cases.manager import onboard, purge_expired

        # Create two customers with documents
        res1 = onboard(conn, org_id=org_id, reference="DOC-3", full_name="Customer 1")
        res2 = onboard(conn, org_id=org_id, reference="DOC-4", full_name="Customer 2")

        for cid in [res1.customer_id, res2.customer_id]:
            conn.execute(
                "INSERT INTO documents (customer_id, org_id, doc_type, filename, stored_path, sha256, uploaded_at) "
                "VALUES (?, ?, 'passport', 'doc.pdf', 'gs://bucket/doc.pdf', 'ghi789', datetime('now'))",
                (cid, org_id)
            )
            conn.execute(
                "UPDATE customers SET status='closed', retention_until='2020-01-01' WHERE id=?",
                (cid,)
            )
        conn.commit()

        # First delete fails, second succeeds
        mock_storage_delete.side_effect = [OSError("Permission denied"), None]

        result = purge_expired(conn, org_id)

        # Both customers should be purged despite the first delete failure
        assert result["purged"] == 2
        assert mock_storage_delete.call_count >= 2

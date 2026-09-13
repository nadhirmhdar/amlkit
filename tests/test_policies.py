"""Policy repository tests (Phase 4 enhancement)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import (  # noqa: E402
    get_policy,
    list_policies,
    upload_policy,
)
from amlkit.db import connect, utcnow  # noqa: E402


@pytest.fixture()
def conn():
    c = connect(":memory:")
    yield c
    c.close()


@pytest.fixture()
def org_id(conn) -> int:
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
        " RETURNING id",
        ("Test Firm", "test-firm", "active", utcnow()),
    ).fetchone()
    conn.commit()
    return row["id"]


class TestListPolicies:
    """Tests for list_policies()."""

    def test_list_policies_empty(self, conn, org_id) -> None:
        """Empty org returns empty dict."""
        result = list_policies(conn, org_id)

        assert result == {}

    def test_list_policies_groups_by_title(self, conn, org_id) -> None:
        """Multiple versions grouped by title."""
        # Upload v1 and v2 of same title
        policy_id_1, version_1 = upload_policy(
            conn,
            org_id,
            title="AML Policy",
            category="AML_Policy",
            filename="aml-v1.pdf",
            file_content=b"version 1",
            uploaded_by="John Smith",
        )
        conn.commit()

        policy_id_2, version_2 = upload_policy(
            conn,
            org_id,
            title="AML Policy",
            category="AML_Policy",
            filename="aml-v2.pdf",
            file_content=b"version 2",
            uploaded_by="Jane Doe",
        )
        conn.commit()

        result = list_policies(conn, org_id)

        assert "AML Policy" in result
        assert len(result["AML Policy"]) == 2
        # Should be sorted by version descending (v2 first)
        assert result["AML Policy"][0]["version"] == 2
        assert result["AML Policy"][1]["version"] == 1

    def test_list_policies_marks_current_version(self, conn, org_id) -> None:
        """Highest version has is_current=True."""
        upload_policy(
            conn,
            org_id,
            title="AML Policy",
            category="AML_Policy",
            filename="aml-v1.pdf",
            file_content=b"v1",
            uploaded_by="John",
        )
        conn.commit()

        upload_policy(
            conn,
            org_id,
            title="AML Policy",
            category="AML_Policy",
            filename="aml-v2.pdf",
            file_content=b"v2",
            uploaded_by="Jane",
        )
        conn.commit()

        result = list_policies(conn, org_id)

        # v2 should be current
        assert result["AML Policy"][0]["is_current"] is True
        # v1 should not be current
        assert result["AML Policy"][1]["is_current"] is False

    def test_list_policies_filters_by_category(self, conn, org_id) -> None:
        """Category filter works."""
        upload_policy(
            conn,
            org_id,
            title="AML Policy",
            category="AML_Policy",
            filename="aml.pdf",
            file_content=b"aml",
            uploaded_by="John",
        )
        conn.commit()

        upload_policy(
            conn,
            org_id,
            title="CDD Procedures",
            category="CDD_Procedures",
            filename="cdd.pdf",
            file_content=b"cdd",
            uploaded_by="Jane",
        )
        conn.commit()

        result = list_policies(conn, org_id, category="AML_Policy")

        assert "AML Policy" in result
        assert "CDD Procedures" not in result


class TestUploadPolicy:
    """Tests for upload_policy()."""

    def test_upload_policy_creates_version_1(self, conn, org_id) -> None:
        """First upload sets version=1."""
        policy_id, version = upload_policy(
            conn,
            org_id,
            title="AML Policy",
            category="AML_Policy",
            filename="aml-policy.pdf",
            file_content=b"test content",
            uploaded_by="John Smith",
        )
        conn.commit()

        assert version == 1
        assert policy_id > 0

    def test_upload_policy_increments_version(self, conn, org_id) -> None:
        """Same title increments version."""
        _, v1 = upload_policy(
            conn,
            org_id,
            title="AML Policy",
            category="AML_Policy",
            filename="aml-v1.pdf",
            file_content=b"v1",
            uploaded_by="John",
        )
        conn.commit()

        _, v2 = upload_policy(
            conn,
            org_id,
            title="AML Policy",
            category="AML_Policy",
            filename="aml-v2.pdf",
            file_content=b"v2",
            uploaded_by="Jane",
        )
        conn.commit()

        assert v1 == 1
        assert v2 == 2

    def test_upload_policy_validates_category(self, conn, org_id) -> None:
        """Invalid category raises ValueError."""
        with pytest.raises(ValueError, match="category"):
            upload_policy(
                conn,
                org_id,
                title="Test",
                category="InvalidCategory",
                filename="test.pdf",
                file_content=b"test",
                uploaded_by="John",
            )

    def test_upload_policy_validates_file_type(self, conn, org_id) -> None:
        """.txt file raises ValueError."""
        with pytest.raises(ValueError, match="file type"):
            upload_policy(
                conn,
                org_id,
                title="Test",
                category="AML_Policy",
                filename="test.txt",
                file_content=b"test",
                uploaded_by="John",
            )

    def test_upload_policy_validates_file_size(self, conn, org_id) -> None:
        """11MB file raises ValueError."""
        large_content = b"x" * (11 * 1024 * 1024)  # 11 MB

        with pytest.raises(ValueError, match="size"):
            upload_policy(
                conn,
                org_id,
                title="Test",
                category="AML_Policy",
                filename="large.pdf",
                file_content=large_content,
                uploaded_by="John",
            )

    def test_upload_policy_logs_audit(self, conn, org_id) -> None:
        """Audit entry created."""
        upload_policy(
            conn,
            org_id,
            title="AML Policy",
            category="AML_Policy",
            filename="aml.pdf",
            file_content=b"test",
            uploaded_by="John Smith",
        )
        conn.commit()

        audit_row = conn.execute(
            "SELECT action FROM audit_log WHERE action='policy.upload'"
        ).fetchone()

        assert audit_row is not None


class TestGetPolicy:
    """Tests for get_policy()."""

    def test_get_policy_returns_metadata_and_content(self, conn, org_id) -> None:
        """Returns full dict with file_content."""
        policy_id, version = upload_policy(
            conn,
            org_id,
            title="AML Policy",
            category="AML_Policy",
            filename="aml.pdf",
            file_content=b"test content",
            uploaded_by="John Smith",
        )
        conn.commit()

        policy = get_policy(conn, policy_id, org_id=org_id)

        assert policy["id"] == policy_id
        assert policy["title"] == "AML Policy"
        assert policy["category"] == "AML_Policy"
        assert policy["filename"] == "aml.pdf"
        assert policy["version"] == 1
        assert policy["uploaded_by"] == "John Smith"
        assert policy["file_content"] == b"test content"

    def test_get_policy_logs_download_audit(self, conn, org_id) -> None:
        """Audit entry created."""
        policy_id, _ = upload_policy(
            conn,
            org_id,
            title="Test",
            category="AML_Policy",
            filename="test.pdf",
            file_content=b"test",
            uploaded_by="John",
        )
        conn.commit()

        get_policy(conn, policy_id, org_id=org_id)
        conn.commit()

        audit_row = conn.execute(
            "SELECT action FROM audit_log WHERE action='policy.download'"
        ).fetchone()

        assert audit_row is not None

    def test_get_policy_rejects_wrong_org(self, conn, org_id) -> None:
        """org_id mismatch raises ValueError."""
        policy_id, _ = upload_policy(
            conn,
            org_id,
            title="Test",
            category="AML_Policy",
            filename="test.pdf",
            file_content=b"test",
            uploaded_by="John",
        )
        conn.commit()

        with pytest.raises(ValueError, match="not found"):
            get_policy(conn, policy_id, org_id=org_id + 999)

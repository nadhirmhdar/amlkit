"""Policy storage tests (Phase 4 enhancement, Item 2)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.storage import upload_policy, download_policy  # noqa: E402


class TestPolicyStorage:
    """Tests for policy-specific storage functions."""

    def test_upload_policy_creates_directory(self) -> None:
        """data/policies/{org_id} created if needed."""
        content = b"test policy content"
        org_id = 123
        filename = "test-policy.pdf"

        stored_path = upload_policy(content, org_id, filename)

        assert stored_path is not None
        assert "policies" in stored_path
        assert str(org_id) in stored_path
        assert filename in stored_path

        # Cleanup
        if os.path.exists(stored_path):
            os.remove(stored_path)

    def test_upload_policy_writes_file(self) -> None:
        """File exists at returned path."""
        content = b"policy file content"
        org_id = 456
        filename = "aml-policy.pdf"

        stored_path = upload_policy(content, org_id, filename)

        assert os.path.exists(stored_path)

        # Cleanup
        os.remove(stored_path)

    def test_download_policy_returns_content(self) -> None:
        """Bytes match original upload."""
        content = b"original policy content"
        org_id = 789
        filename = "cdd-procedures.pdf"

        stored_path = upload_policy(content, org_id, filename)
        retrieved_content = download_policy(stored_path)

        assert retrieved_content == content

        # Cleanup
        os.remove(stored_path)

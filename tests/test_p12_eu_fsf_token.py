"""Test p12: Remove hardcoded EU FSF demo token."""

import os
import pytest


def test_eu_fsf_token_required():
    """EU adapter must raise AdapterError if AMLKIT_EU_FSF_TOKEN is unset."""
    from amlkit.ingest.eu import list_url
    from amlkit.ingest.base import AdapterError

    # Clear env var if set
    original = os.environ.pop("AMLKIT_EU_FSF_TOKEN", None)

    try:
        with pytest.raises(AdapterError, match="EU FSF token not configured"):
            list_url()
    finally:
        # Restore original value
        if original:
            os.environ["AMLKIT_EU_FSF_TOKEN"] = original


def test_eu_fsf_token_used_when_set():
    """EU adapter uses AMLKIT_EU_FSF_TOKEN when present."""
    from amlkit.ingest.eu import list_url

    original = os.environ.get("AMLKIT_EU_FSF_TOKEN")
    os.environ["AMLKIT_EU_FSF_TOKEN"] = "test-token-abc123"

    try:
        url = list_url()
        assert "token=test-token-abc123" in url
    finally:
        if original:
            os.environ["AMLKIT_EU_FSF_TOKEN"] = original
        else:
            os.environ.pop("AMLKIT_EU_FSF_TOKEN", None)

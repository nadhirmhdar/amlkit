"""Tests for EU FSF token requirement - p12.

The EU adapter must not fall back to the demo token. AMLKIT_EU_FSF_TOKEN
must be set, or the adapter should raise a clear configuration error.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestEuTokenRequired:
    """Tests for EU FSF token requirement."""

    def test_list_url_raises_when_token_unset(self, monkeypatch) -> None:
        """list_url() raises ValueError when AMLKIT_EU_FSF_TOKEN is unset."""
        monkeypatch.delenv("AMLKIT_EU_FSF_TOKEN", raising=False)

        # Need to reload module after env change
        import importlib
        from amlkit.ingest import eu
        importlib.reload(eu)

        with pytest.raises(ValueError, match="AMLKIT_EU_FSF_TOKEN environment variable is required"):
            eu.list_url()

    def test_list_url_raises_when_token_empty(self, monkeypatch) -> None:
        """list_url() raises ValueError when AMLKIT_EU_FSF_TOKEN is empty string."""
        monkeypatch.setenv("AMLKIT_EU_FSF_TOKEN", "")

        import importlib
        from amlkit.ingest import eu
        importlib.reload(eu)

        with pytest.raises(ValueError, match="AMLKIT_EU_FSF_TOKEN environment variable is required"):
            eu.list_url()

    def test_list_url_raises_when_token_whitespace(self, monkeypatch) -> None:
        """list_url() raises ValueError when AMLKIT_EU_FSF_TOKEN is only whitespace."""
        monkeypatch.setenv("AMLKIT_EU_FSF_TOKEN", "   ")

        import importlib
        from amlkit.ingest import eu
        importlib.reload(eu)

        with pytest.raises(ValueError, match="AMLKIT_EU_FSF_TOKEN environment variable is required"):
            eu.list_url()

    def test_list_url_works_with_valid_token(self, monkeypatch) -> None:
        """list_url() returns URL when AMLKIT_EU_FSF_TOKEN is set."""
        monkeypatch.setenv("AMLKIT_EU_FSF_TOKEN", "my-production-token-12345")

        import importlib
        from amlkit.ingest import eu
        importlib.reload(eu)

        url = eu.list_url()
        assert "my-production-token-12345" in url
        assert "webgate.ec.europa.eu" in url

    def test_adapter_initialization_raises_when_token_unset(self, monkeypatch) -> None:
        """EUSanctionsAdapter.__init__() raises when token unset."""
        monkeypatch.delenv("AMLKIT_EU_FSF_TOKEN", raising=False)

        import importlib
        from amlkit.ingest import eu
        importlib.reload(eu)

        # Adapter's __init__ calls list_url(), which should raise
        with pytest.raises(ValueError, match="AMLKIT_EU_FSF_TOKEN environment variable is required"):
            eu.EUSanctionsAdapter()

    def test_adapter_initialization_works_with_valid_token(self, monkeypatch) -> None:
        """EUSanctionsAdapter.__init__() succeeds when token is set."""
        monkeypatch.setenv("AMLKIT_EU_FSF_TOKEN", "my-production-token-12345")

        import importlib
        from amlkit.ingest import eu
        importlib.reload(eu)

        adapter = eu.EUSanctionsAdapter()
        assert adapter.key == "eu_sanctions"
        assert "my-production-token-12345" in adapter.source_url

    def test_error_message_includes_registration_url(self, monkeypatch) -> None:
        """Error message includes the FSF registration URL."""
        monkeypatch.delenv("AMLKIT_EU_FSF_TOKEN", raising=False)

        import importlib
        from amlkit.ingest import eu
        importlib.reload(eu)

        with pytest.raises(ValueError) as exc_info:
            eu.list_url()

        assert "webgate.ec.europa.eu/fsd/fsf" in str(exc_info.value)
        assert "Register" in str(exc_info.value) or "register" in str(exc_info.value)

    def test_no_demo_token_constant_in_module(self, monkeypatch) -> None:
        """Verify DEFAULT_TOKEN constant has been removed."""
        monkeypatch.setenv("AMLKIT_EU_FSF_TOKEN", "test-token")

        import importlib
        from amlkit.ingest import eu
        importlib.reload(eu)

        # DEFAULT_TOKEN should not exist anymore
        assert not hasattr(eu, "DEFAULT_TOKEN"), "DEFAULT_TOKEN constant should be removed"

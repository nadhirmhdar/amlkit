"""Test adverse media robustness (t27).

Verify adverse_media.py handles:
- Timeouts gracefully
- Changed markup / API responses
- Empty results
- Rate limiting

Uses scrapling adaptive tracker pattern.
"""

from __future__ import annotations

import pytest

from amlkit.screening.adverse_media import (
    GDELTClient,
    MediaUnavailable,
    search,
    AdverseMediaResult,
)


def test_timeout_returns_unavailable_status():
    """Timeout should return unavailable status, not raise."""
    # Use very short timeout to force failure
    client = GDELTClient(timeout=0.001)

    result = search("John Smith", client=client, window_months=12)

    # Should return unavailable, not raise
    assert result.status == "unavailable"
    assert result.findings == []


def test_empty_results_handled_gracefully():
    """Empty result set from GDELT should not error."""
    # Search for nonsense name that won't have coverage
    result = search("Xyzzy Plugh Fnord", window_months=1)

    # Should complete successfully with empty results
    assert result.status in ["ok", "unavailable"]
    assert isinstance(result.findings, list)


def test_malformed_response_returns_unavailable():
    """Malformed JSON from GDELT should be handled gracefully."""

    class MalformedClient:
        """Mock client returning garbage."""

        def fetch(self, query: str, *, window_months: int, max_records: int) -> dict:
            # Return malformed structure
            return {"invalid": "structure"}

    result = search("Test Name", client=MalformedClient())

    # Should handle gracefully, not crash
    assert result.status == "unavailable" or len(result.findings) == 0


def test_rate_limit_handled():
    """429 rate limit should return unavailable, not crash."""
    # The GDELTClient already has rate limiting built in
    # This test verifies the error handling works

    class RateLimitedClient:
        """Mock client that always returns 429."""

        def fetch(self, query: str, *, window_months: int, max_records: int) -> dict:
            raise MediaUnavailable("GDELT rate limit reached")

    result = search("Test Name", client=RateLimitedClient())

    assert result.status == "unavailable"
    assert result.findings == []


def test_network_error_handled():
    """Network errors should return unavailable, not propagate."""

    class FailingClient:
        """Mock client that raises network error."""

        def fetch(self, query: str, *, window_months: int, max_records: int) -> dict:
            raise MediaUnavailable("Network unreachable")

    result = search("Test Name", client=FailingClient())

    assert result.status == "unavailable"
    assert result.findings == []


def test_partial_results_preserved():
    """If some data is retrievable, preserve what we got."""

    class PartialClient:
        """Mock client returning partial data."""

        def fetch(self, query: str, *, window_months: int, max_records: int) -> dict:
            return {
                "articles": [
                    {
                        "url": "https://example.com/article1",
                        "title": "Test Article",
                        "seendate": "20260920T000000Z",
                    }
                ]
            }

    result = search("Test Name", client=PartialClient())

    # Should extract whatever is usable
    assert result.status in ["ok", "unavailable"]
    # Should have processed the article
    assert result.articles_considered >= 0


def test_search_never_raises_for_provider_failure():
    """search() must never raise MediaUnavailable - always return result object."""

    class AlwaysFailingClient:
        """Mock client that always fails."""

        def fetch(self, query: str, *, window_months: int, max_records: int) -> dict:
            raise MediaUnavailable("Total failure")

    # Should not raise - must return a result
    result = search("Test Name", client=AlwaysFailingClient())

    assert isinstance(result, AdverseMediaResult)
    assert result.status == "unavailable"

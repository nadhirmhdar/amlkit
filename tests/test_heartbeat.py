"""Tests for the heartbeat connectivity script."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scripts.heartbeat import heartbeat


def _make_adapter(key: str, is_mandatory: bool, should_fail: bool = False):
    """Return a factory that produces a mock adapter."""
    def factory():
        adapter = MagicMock()
        adapter.key = key
        adapter.is_mandatory = is_mandatory
        if should_fail:
            from amlkit.ingest.base import AdapterError
            adapter.fetch.side_effect = AdapterError(f"{key} unreachable")
        else:
            adapter.fetch.return_value = b"<ok/>"
        return adapter
    return factory


class TestHeartbeat:
    """Heartbeat exit-code behaviour."""

    def test_all_succeed_exit_0(self):
        sources = [
            _make_adapter("src_a", is_mandatory=True),
            _make_adapter("src_b", is_mandatory=True),
            _make_adapter("src_c", is_mandatory=False),
        ]
        assert heartbeat(sources) == 0

    def test_mandatory_fail_exit_1(self):
        sources = [
            _make_adapter("src_a", is_mandatory=True),
            _make_adapter("src_b", is_mandatory=True, should_fail=True),
            _make_adapter("src_c", is_mandatory=False),
        ]
        assert heartbeat(sources) == 1

    def test_optional_fail_exit_0(self):
        sources = [
            _make_adapter("src_a", is_mandatory=True),
            _make_adapter("src_b", is_mandatory=False, should_fail=True),
        ]
        assert heartbeat(sources) == 0

    def test_multiple_mandatory_failures(self):
        sources = [
            _make_adapter("src_a", is_mandatory=True, should_fail=True),
            _make_adapter("src_b", is_mandatory=True, should_fail=True),
        ]
        assert heartbeat(sources) == 1

    def test_all_optional_succeed(self):
        """Only optional sources, all passing — should exit 0."""
        sources = [
            _make_adapter("src_a", is_mandatory=False),
            _make_adapter("src_b", is_mandatory=False),
        ]
        assert heartbeat(sources) == 0

    def test_all_optional_fail(self):
        """Only optional sources, all failing — still exit 0."""
        sources = [
            _make_adapter("src_a", is_mandatory=False, should_fail=True),
            _make_adapter("src_b", is_mandatory=False, should_fail=True),
        ]
        assert heartbeat(sources) == 0

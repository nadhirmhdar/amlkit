"""Tests for the retry_on_lock decorator.

SQLite's busy_timeout PRAGMA waits for a lock but eventually gives up with
OperationalError. This decorator retries the entire operation with exponential
backoff, covering the case where a long-running refresh holds the WAL lock
beyond the busy_timeout window.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import retry_on_lock


class TestRetryOnLock:
    def test_succeeds_without_error(self) -> None:
        calls = []

        @retry_on_lock()
        def do_write():
            calls.append(1)
            return "ok"

        assert do_write() == "ok"
        assert len(calls) == 1

    def test_retries_on_locked_error(self) -> None:
        attempts = []

        @retry_on_lock(max_retries=3, base_delay=0.01)
        def do_write():
            attempts.append(1)
            if len(attempts) < 3:
                raise sqlite3.OperationalError("database is locked")
            return "recovered"

        assert do_write() == "recovered"
        assert len(attempts) == 3

    def test_gives_up_after_max_retries(self) -> None:
        @retry_on_lock(max_retries=2, base_delay=0.01)
        def do_write():
            raise sqlite3.OperationalError("database is locked")

        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            do_write()

    def test_does_not_retry_other_errors(self) -> None:
        calls = []

        @retry_on_lock(max_retries=3, base_delay=0.01)
        def do_write():
            calls.append(1)
            raise sqlite3.OperationalError("no such table: foo")

        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            do_write()
        assert len(calls) == 1

    def test_preserves_function_signature(self) -> None:
        @retry_on_lock()
        def my_func(a, b, c=3):
            """My docstring."""
            return a + b + c

        assert my_func.__name__ == "my_func"
        assert my_func(1, 2) == 6

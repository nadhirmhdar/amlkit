"""Connection-level configuration tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect  # noqa: E402


class TestBusyTimeout:
    def test_busy_timeout_is_configured(self) -> None:
        """Without this, two connections writing at once fail immediately
        with 'database is locked' instead of one waiting for the other --
        exactly what happened in production when a scheduled refresh
        (which now holds a connection open for the whole synchronous
        refresh) overlapped with another write."""
        conn = connect(":memory:")
        try:
            timeout_ms = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert timeout_ms >= 30000
        finally:
            conn.close()


class TestCrossThreadTeardown:
    def test_connection_survives_close_from_a_different_thread(self) -> None:
        """A connection from connect() must tolerate being closed on a
        different thread than the one that created and used it.

        Regression test for finding #7 (2026-09-21 deployed-site review,
        QA-04): api/deps.py's get_db() is a sync generator FastAPI
        dependency. Starlette runs a sync generator dependency's setup
        (everything before `yield`) and its teardown (the `finally` block
        after `yield`) as separate calls into the threadpool, which are not
        guaranteed to land on the same worker thread. With sqlite3's default
        check_same_thread=True, a request whose teardown happened to land on
        a different thread than its setup raised sqlite3.ProgrammingError
        ("SQLite objects created in a thread can only be used in that same
        thread") -- an intermittent 500 under concurrent load. Reproduces
        the same shape directly (create + query on thread A, close on
        thread B) rather than relying on FastAPI's actual thread scheduling
        being nondeterministic in a test.
        """
        import threading

        # The creating thread must still be alive (not joined) while the
        # other thread acts, or the OS can recycle its thread id onto the
        # second thread by the time it runs -- which would make the "same
        # thread" check trivially pass and silently defeat this test.
        state: dict = {}
        ready = threading.Event()
        release = threading.Event()

        def create_and_hold() -> None:
            conn = connect(":memory:")
            conn.execute("SELECT 1").fetchone()
            state["conn"] = conn
            ready.set()
            release.wait()

        creator = threading.Thread(target=create_and_hold)
        creator.start()
        ready.wait(timeout=5)

        errors: list[Exception] = []

        def use_and_close_on_other_thread() -> None:
            try:
                state["conn"].execute("SELECT 1").fetchone()
                state["conn"].close()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        other = threading.Thread(target=use_and_close_on_other_thread)
        other.start()
        other.join(timeout=5)
        release.set()
        creator.join(timeout=5)

        assert not errors, f"using/closing on a different thread raised: {errors!r}"

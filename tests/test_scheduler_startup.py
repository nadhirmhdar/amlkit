"""In-process sanctions-refresh scheduler startup tests.

An APScheduler IntervalTrigger with no explicit `next_run_time` waits a full
interval (23h) before its first fire. On Cloud Run every fresh container
start (a redeploy, or a cold start after scaling to zero) began a brand new
23-hour wait instead of refreshing right away -- one of the ways the 24-hour
rule was breaching even with this scheduler "running". This locks in that
the startup job is now scheduled to fire immediately, not 23h out.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _FakeScheduler:
    """Records add_job calls instead of actually running a thread pool --
    keeps this test hermetic (no real background thread, no network call)."""

    instances: list["_FakeScheduler"] = []

    def __init__(self, *a, **kw) -> None:
        self.jobs: list[dict] = []
        _FakeScheduler.instances.append(self)

    def add_job(self, func, **kwargs) -> None:
        self.jobs.append({"func": func, **kwargs})

    def start(self) -> None:
        pass

    def shutdown(self, wait: bool = True) -> None:
        pass


class TestSchedulerFiresImmediatelyOnStartup:
    def test_next_run_time_is_now_not_23_hours_out(self, monkeypatch) -> None:
        import apscheduler.schedulers.background as bg_module

        monkeypatch.setattr(bg_module, "BackgroundScheduler", _FakeScheduler)
        _FakeScheduler.instances.clear()

        from amlkit.api.app import app

        with __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app):
            pass

        assert _FakeScheduler.instances, "BackgroundScheduler was never constructed"
        jobs = _FakeScheduler.instances[-1].jobs
        assert jobs, "no job was scheduled"
        job = jobs[0]

        assert job["trigger"] == "interval"
        assert job["hours"] == 23
        next_run_time = job.get("next_run_time")
        assert next_run_time is not None, (
            "job must set next_run_time explicitly -- without it, IntervalTrigger "
            "waits a full 23h before its first fire"
        )
        assert abs((next_run_time - datetime.now()).total_seconds()) < 5

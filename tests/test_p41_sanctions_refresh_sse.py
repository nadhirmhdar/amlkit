"""p41: Sanctions refresh streams per-list progress via SSE."""
import json


def test_sse_endpoint_exists():
    """The /admin/refresh-stream endpoint should exist and return text/event-stream."""
    from amlkit.api.app import app
    routes = {r.path for r in app.routes if hasattr(r, 'path')}
    assert "/admin/refresh-stream" in routes


def test_sse_generator_yields_events(monkeypatch):
    """The SSE generator should yield progress events for each adapter."""
    monkeypatch.setenv("AMLKIT_DB", ":memory:")

    from amlkit.cases.scheduler import refresh_with_progress

    events = []
    class FakeConn:
        def execute(self, *a, **kw):
            class FakeResult:
                def fetchall(self): return []
                def fetchone(self): return None
            return FakeResult()
        def commit(self): pass

    class FakeAdapter:
        title = "Test List"
        key = "test"
        is_mandatory = True
        def __call__(self): return self

    fake_adapters = [FakeAdapter()]

    def fake_load(conn, adapter, actor="system"):
        class Result:
            entities = 42
        return Result()

    monkeypatch.setattr("amlkit.ingest.loader.load", fake_load)

    def noop_invalidate(): pass
    monkeypatch.setattr("amlkit.match.cache.invalidate", noop_invalidate)

    for event in refresh_with_progress(FakeConn(), "test-actor", adapters=fake_adapters):
        events.append(event)

    # Should have at least one adapter event and a done event
    assert len(events) >= 2
    assert any(e.get("type") == "adapter_done" for e in events)
    assert any(e.get("type") == "complete" for e in events)


def test_sse_generator_reports_failures(monkeypatch):
    """If an adapter fails, the SSE generator should yield an error event."""
    from amlkit.cases.scheduler import refresh_with_progress
    from amlkit.ingest.base import AdapterError

    class FakeConn:
        def execute(self, *a, **kw):
            class FakeResult:
                def fetchall(self): return []
                def fetchone(self): return None
            return FakeResult()
        def commit(self): pass

    class FakeAdapter:
        title = "Failing List"
        key = "fail"
        is_mandatory = True
        def __call__(self): return self

    fake_adapters = [FakeAdapter()]

    def failing_load(conn, adapter, actor="system"):
        raise AdapterError("connection timeout")

    monkeypatch.setattr("amlkit.ingest.loader.load", failing_load)
    monkeypatch.setattr("amlkit.db.record_dataset_error", lambda *a, **kw: None)
    monkeypatch.setattr("amlkit.db.audit", lambda *a, **kw: None)
    monkeypatch.setattr("amlkit.match.cache.invalidate", lambda: None)

    events = list(refresh_with_progress(FakeConn(), "test-actor", adapters=fake_adapters))

    assert any(e.get("type") == "adapter_error" for e in events)
    error_event = next(e for e in events if e.get("type") == "adapter_error")
    assert "connection timeout" in error_event.get("error", "")

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
        publisher = "Test Publisher"
        source_url = "https://example.test/fail"
        licence = "Public Domain"
        is_mandatory = True
        def __call__(self): return self

    fake_adapters = [FakeAdapter()]

    def failing_load(conn, adapter, actor="system"):
        raise AdapterError("connection timeout")

    monkeypatch.setattr("amlkit.ingest.loader.load", failing_load)
    monkeypatch.setattr("amlkit.db.record_dataset_error", lambda *a, **kw: None)
    monkeypatch.setattr("amlkit.db.upsert_dataset", lambda *a, **kw: None)
    monkeypatch.setattr("amlkit.db.audit", lambda *a, **kw: None)
    monkeypatch.setattr("amlkit.match.cache.invalidate", lambda: None)

    events = list(refresh_with_progress(FakeConn(), "test-actor", adapters=fake_adapters))

    assert any(e.get("type") == "adapter_error" for e in events)
    error_event = next(e for e in events if e.get("type") == "adapter_error")
    assert "connection timeout" in error_event.get("error", "")


def test_adapter_without_source_url_attribute_does_not_crash_refresh(monkeypatch):
    """A real adapter that never sets self.source_url must not crash the loop.

    EUSanctionsAdapter (amlkit/ingest/eu.py) resolves its URL at fetch() time
    (it embeds a rotatable token) and never assigns self.source_url. Before
    this fix, the failure-path upsert_dataset() call read adapter.source_url
    directly, so an EU FSF failure (missing/rotated token -- the exact
    scenario the adapter's own docstring calls realistic) raised an
    uncaught AttributeError instead of AdapterError, aborting the whole
    refresh loop before later sources (UK, CIA, FATF, Interpol) ever ran.
    """
    from amlkit.cases.scheduler import refresh_with_progress
    from amlkit.ingest.eu import EUSanctionsAdapter
    from amlkit.db import connect

    monkeypatch.delenv("AMLKIT_EU_FSF_TOKEN", raising=False)
    monkeypatch.setattr("amlkit.match.cache.invalidate", lambda: None)

    conn = connect(":memory:")
    conn.execute("DELETE FROM datasets")
    conn.commit()

    # Must not raise AttributeError.
    events = list(refresh_with_progress(conn, "test-actor", adapters=[EUSanctionsAdapter]))

    assert any(e.get("type") == "adapter_error" for e in events)
    row = conn.execute(
        "SELECT last_error, is_mandatory FROM datasets WHERE key='eu_sanctions'"
    ).fetchone()
    assert row is not None
    assert row["last_error"]
    conn.close()


def test_eu_adapter_sets_source_url_at_init():
    """EUSanctionsAdapter must satisfy SourceAdapter's source_url contract.

    Every other adapter sets self.source_url in __init__; EU alone deferred
    it to fetch() time (it embeds a rotatable token there), which meant
    every caller that reads adapter.source_url before fetch() -- including
    loader.load()'s own success path, which is the untokenised call the
    fetch-time comment did not anticipate -- got an AttributeError instead
    of a URL. The stored value must also never carry the live token.
    """
    from amlkit.ingest.eu import EUSanctionsAdapter, BASE_URL

    adapter = EUSanctionsAdapter()
    assert adapter.source_url == BASE_URL
    assert "token=" not in adapter.source_url


def test_load_success_path_does_not_crash_on_eu_adapter(monkeypatch):
    """loader.load()'s success path reads adapter.source_url directly (no
    getattr fallback there, unlike the failure paths in scheduler.py) -- a
    successful EU refresh must not crash it."""
    from amlkit.ingest.eu import EUSanctionsAdapter
    from amlkit.ingest.loader import load
    from amlkit.ingest.base import SourceEntity
    from amlkit.db import connect

    adapter = EUSanctionsAdapter()
    monkeypatch.setattr(adapter, "fetch", lambda: b"<fake/>")
    monkeypatch.setattr(
        adapter, "parse",
        lambda payload: iter([SourceEntity(source_id="1", schema_type="Person",
                                            caption="Test Entity")]),
    )

    conn = connect(":memory:")
    conn.execute("DELETE FROM datasets")
    conn.commit()

    result = load(conn, adapter, actor="test-actor")  # must not raise
    assert result.entities == 1

    row = conn.execute("SELECT source_url FROM datasets WHERE key='eu_sanctions'").fetchone()
    assert row["source_url"] == adapter.source_url
    conn.close()


def test_first_ever_failure_still_creates_a_visible_dataset_row(monkeypatch):
    """A mandatory source that has NEVER loaded successfully must still show
    up as a failed/breach row, not disappear from the compliance dashboard.

    Finding #1 (2026-09-21 deployed-site review): load() only calls
    upsert_dataset() on success, so a source whose very first refresh fails
    has no `datasets` row at all -- record_dataset_error() then silently
    no-ops (see test_record_on_missing_dataset_is_noop), and the compliance
    dashboard shows nothing for it instead of a failure. Uses a real
    in-memory DB (not the FakeConn used above) so staleness_report() runs
    for real against what refresh_with_progress() actually wrote.
    """
    from amlkit.cases.scheduler import refresh_with_progress
    from amlkit.ingest.base import AdapterError
    from amlkit.ingest.loader import staleness_report
    from amlkit.db import connect

    conn = connect(":memory:")
    conn.execute("DELETE FROM datasets")  # ignore FATF's connect()-time seed
    conn.commit()

    class NeverLoadedAdapter:
        title = "Never Loaded Sanctions List"
        key = "never_loaded_sanctions_list"
        publisher = "Test Publisher"
        source_url = "https://example.test/never-loaded"
        licence = "Public Domain"
        is_mandatory = True
        def __call__(self): return self

    def failing_load(conn, adapter, actor="system"):
        raise AdapterError("HTTP 403 Forbidden")

    monkeypatch.setattr("amlkit.ingest.loader.load", failing_load)
    monkeypatch.setattr("amlkit.match.cache.invalidate", lambda: None)

    list(refresh_with_progress(conn, "test-actor", adapters=[NeverLoadedAdapter()]))

    row = conn.execute(
        "SELECT is_mandatory, last_error, last_refresh FROM datasets WHERE key=?",
        ("never_loaded_sanctions_list",),
    ).fetchone()
    assert row is not None, "failed source must get a dataset row even on its first-ever refresh"
    assert row["is_mandatory"] == 1
    assert "403" in row["last_error"]
    assert row["last_refresh"] is None

    report = {d["key"]: d for d in staleness_report(conn)}
    assert report["never_loaded_sanctions_list"]["breach"] is True
    conn.close()

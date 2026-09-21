"""Concurrency regression test for the per-request SQLite connection.

QA-04 (2026-09-21 deployed-site review): under parallel load, a fraction of
authenticated GETs returned HTTP 500 with

    sqlite3.ProgrammingError: SQLite objects created in a thread can only be
    used in that same thread

FastAPI runs a sync generator dependency (deps.get_db) through
contextmanager_in_threadpool, which opens the connection on one threadpool
worker and can run the request body -- and the teardown close() -- on a
different worker. sqlite3 connections opened with the default
check_same_thread=True reject that cross-thread use. connect() now opens with
check_same_thread=False, which is safe because each request gets its own
connection that is never shared between concurrent requests.

This test drives a real uvicorn server (the TestClient serialises requests
through a single event-loop portal, so it cannot reproduce the race) and
fires ~40 concurrent authenticated GETs, asserting none return 5xx.
"""

from __future__ import annotations

import concurrent.futures
import socket
import threading
import time
from collections import Counter
from pathlib import Path

import httpx
import pytest

from conftest import register_org, seed_fresh_dataset, settle_mfa


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def live_server(tmp_path, monkeypatch):
    """A real uvicorn server bound to a throwaway DB, torn down after the test."""
    import uvicorn

    from amlkit.db import connect

    db_file = tmp_path / "conc.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    conn = connect(db_file)
    seed_fresh_dataset(conn)
    conn.close()

    from amlkit.api.app import app

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started, "uvicorn server did not start in time"

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_parallel_authenticated_gets_never_5xx(live_server) -> None:
    base = live_server

    # Authenticate one client (single-threaded) and reuse its cookies.
    auth = httpx.Client(base_url=base, follow_redirects=True)
    register_org(auth, "Conc Firm", "alice", "alice@concfirm.ae")
    settle_mfa(auth)
    warmup = auth.get("/")
    assert warmup.status_code == 200, warmup.text[:300]
    cookies = dict(auth.cookies)
    auth.close()

    n = 40

    def hit(_: int) -> int:
        # A fresh client per thread: httpx.Client is not safe to share across
        # threads, and the point of the test is server-side concurrency.
        with httpx.Client(base_url=base, cookies=cookies) as h:
            return h.get("/").status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        codes = list(pool.map(hit, range(n)))

    server_errors = [c for c in codes if c >= 500]
    assert not server_errors, f"got 5xx under concurrency: {Counter(codes)}"
    assert all(c == 200 for c in codes), f"unexpected statuses: {Counter(codes)}"

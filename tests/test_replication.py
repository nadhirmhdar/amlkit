"""amlkit.replication.sync_replica: best-effort `litestream sync -wait`.

It must never raise into the request it follows, must be a no-op wherever
litestream isn't installed or running (tests, dev), and must be called after
the sanctions refresh, report finalisation and freeze execution.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit import replication  # noqa: E402
from test_api import client, _csrf  # noqa: E402,F401
from test_freeze_cnmr_lifecycle import (  # noqa: E402
    _db, _ffr_form, _freeze_row, _seed_executed_freeze_in_test_db,
)


@pytest.fixture()
def live(tmp_path, monkeypatch):
    """Environment where a sync would actually run: enabled, a litestream
    binary on PATH, a control socket present. Returns the recorded calls."""
    sock = tmp_path / "litestream.sock"
    sock.touch()
    monkeypatch.setenv("AMLKIT_SYNC_REPLICA", "1")
    monkeypatch.setenv("AMLKIT_LITESTREAM_SOCKET", str(sock))
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "aml.db"))
    monkeypatch.setattr(replication.shutil, "which", lambda name: "/usr/bin/litestream")
    calls: list[dict] = []

    def ok(cmd, **kw):
        calls.append({"cmd": cmd, **kw})
        return SimpleNamespace(returncode=0, stdout="db_path: x\ntxid: 7\nreplica_txid: 7\n", stderr="")

    monkeypatch.setattr(replication.subprocess, "run", ok)
    return SimpleNamespace(calls=calls, sock=sock, tmp=tmp_path)


# ------------------------------------------------------------------ gating

@pytest.mark.parametrize("flag,replica,expected", [
    (None, None, False),
    (None, "gs://b/litestream-v3/amlkit.db", True),
    ("0", "gs://b/litestream-v3/amlkit.db", False),
    ("off", "gs://b/litestream-v3/amlkit.db", False),
    ("1", None, True),
    ("true", None, True),
])
def test_enabled_by_default_only_with_a_replica(monkeypatch, flag, replica, expected):
    for name, value in (("AMLKIT_SYNC_REPLICA", flag), ("LITESTREAM_REPLICA_URL", replica)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    assert replication.sync_enabled() is expected


def test_disabled_never_runs_anything(live, monkeypatch):
    monkeypatch.setenv("AMLKIT_SYNC_REPLICA", "0")
    assert replication.sync_replica() is False
    assert live.calls == []


def test_noop_when_litestream_not_installed(live, monkeypatch):
    monkeypatch.setattr(replication.shutil, "which", lambda name: None)
    assert replication.sync_replica() is False
    assert live.calls == []


def test_noop_when_litestream_not_running(live, caplog):
    live.sock.unlink()
    with caplog.at_level(logging.WARNING, logger="amlkit.replication"):
        assert replication.sync_replica(reason="t") is False
    assert live.calls == []
    assert "no litestream control socket" in caplog.text


def test_noop_in_plain_test_environment(monkeypatch):
    """No replica configured, no flag: the default in tests and dev."""
    monkeypatch.delenv("AMLKIT_SYNC_REPLICA", raising=False)
    monkeypatch.delenv("LITESTREAM_REPLICA_URL", raising=False)
    monkeypatch.setattr(replication.subprocess, "run", lambda *a, **k: pytest.fail("ran litestream"))
    assert replication.sync_replica() is False


# ------------------------------------------------------------------ the call

def test_runs_litestream_sync_wait_against_the_socket_and_db(live):
    assert replication.sync_replica(timeout=12) is True
    (call,) = live.calls
    assert call["cmd"] == [
        "/usr/bin/litestream", "sync", "-wait", "-timeout", "12",
        "-socket", str(live.sock), str(live.tmp / "aml.db"),
    ]
    # Hard stop a little past litestream's own best-effort timeout.
    assert call["timeout"] == 17


def test_default_socket_matches_litestream_yml():
    cfg = (Path(__file__).resolve().parent.parent / "litestream.yml").read_text()
    assert f"path: {replication.DEFAULT_SOCKET}" in cfg
    assert "enabled: true" in cfg


def test_timeout_is_logged_not_raised(live, monkeypatch, caplog):
    def hang(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr(replication.subprocess, "run", hang)
    with caplog.at_level(logging.WARNING, logger="amlkit.replication"):
        assert replication.sync_replica(timeout=1, reason="t") is False
    assert "timed out" in caplog.text


def test_nonzero_exit_is_logged_not_raised(live, monkeypatch, caplog):
    monkeypatch.setattr(
        replication.subprocess, "run",
        lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="", stderr="sync failed: context deadline exceeded"),
    )
    with caplog.at_level(logging.WARNING, logger="amlkit.replication"):
        assert replication.sync_replica(reason="t") is False
    assert "exit 1" in caplog.text and "context deadline exceeded" in caplog.text


def test_unexpected_error_is_logged_not_raised(live, monkeypatch, caplog):
    def boom(cmd, **kw):
        raise OSError("exec format error")

    monkeypatch.setattr(replication.subprocess, "run", boom)
    with caplog.at_level(logging.ERROR, logger="amlkit.replication"):
        assert replication.sync_replica(reason="t") is False
    assert "errored" in caplog.text


# ------------------------------------------------------------------ call sites

@pytest.fixture()
def recorded(monkeypatch):
    reasons: list[str] = []
    monkeypatch.setattr(replication, "sync_replica",
                        lambda timeout=30, *, reason="": reasons.append(reason) or True)
    return reasons


def test_system_refresh_syncs_the_replica(tmp_path, monkeypatch, recorded):
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("SCHEDULER_SECRET", "s3cret")
    from amlkit.api import app as app_module
    from fastapi.testclient import TestClient

    monkeypatch.setattr(app_module, "run_sanctions_refresh", lambda conn, actor: {
        "mandatory_failures": [], "failures": [], "rescreen_failures": [],
    })
    monkeypatch.setattr(app_module, "check_and_notify_staleness", lambda conn: {})
    r = TestClient(app_module.app).post("/system/refresh", headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200, r.text
    assert recorded == ["sanctions refresh"]


def test_unauthorised_refresh_does_not_sync(tmp_path, monkeypatch, recorded):
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("SCHEDULER_SECRET", "s3cret")
    from amlkit.api.app import app
    from fastapi.testclient import TestClient

    assert TestClient(app).post("/system/refresh").status_code == 401
    assert recorded == []


def test_freeze_execution_and_report_finalisation_sync(client, recorded):  # noqa: F811
    fid = _seed_executed_freeze_in_test_db()
    conn = _db()
    conn.execute("UPDATE freeze_obligations SET status='pending_execution', executed_at=NULL WHERE id=?", (fid,))
    conn.commit()
    conn.close()

    r = client.post(f"/freeze-obligations/{fid}/execute", data={
        "csrf_token": _csrf(client), "asset_type_1": "cash",
        "asset_identifier_1": "safe-1", "asset_amount_1": "1000",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert recorded == ["freeze executed"]

    client.post(f"/freeze-obligations/{fid}/file-ffr", data=_ffr_form(client))
    conn = _db()
    report_id = _freeze_row(conn, fid)["report_id"]
    conn.close()
    assert recorded == ["freeze executed"]  # a draft is not worth a sync

    r = client.post(f"/reports/{report_id}/submit", data={"csrf_token": _csrf(client)},
                    follow_redirects=True)
    assert r.status_code == 200
    assert recorded == ["freeze executed", "report finalized"]

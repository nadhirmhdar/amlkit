"""Boot-path tests for scripts/entrypoint.sh.

The script runs for real under sh, with /app/ redirected to a temp dir, the
integrity timeouts cut to 1s, and litestream/gsutil/envsubst/sqlite3 replaced
by stubs on a PATH that contains nothing else.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="entrypoint.sh is a POSIX sh script for the Linux container"
)

ENTRYPOINT = Path(__file__).resolve().parent.parent / "scripts" / "entrypoint.sh"
SYSTEM_TOOLS = ["sh", "mkdir", "cat", "date", "mv", "rm", "grep", "timeout", "sleep", "touch"]

SQLITE_STUB = r"""#!/bin/sh
case "$2" in
  *quick_check*) mode="$STUB_QUICK" ;;
  *) mode="$STUB_INTEGRITY" ;;
esac
case "$mode" in
  ok) echo ok ;;
  problems) printf '*** in database main ***\nPage 7575: btree page has 0 cells\n' ;;
  malformed) echo "Error: database disk image is malformed" >&2; exit 1 ;;
  unopenable) echo "Error: unable to open database file" >&2; exit 1 ;;
  hang) exec sleep 30 ;;
  ignore_term) trap '' TERM; sleep 30 ;;
esac
"""

LITESTREAM_STUB = r"""#!/bin/sh
for last; do :; done
case "$1" in
  restore)
    case "$STUB_RESTORE" in
      db) echo restored > "$last" ;;
      none) ;;
      fail) echo "decode page 7575: EOF" >&2; exit 1 ;;
    esac ;;
  replicate) echo "APP STARTED" ;;
esac
"""

GSUTIL_STUB = r"""#!/bin/sh
for last; do :; done
echo "$@" >> "$STUB_GSUTIL_LOG"
case "$STUB_LEGACY" in
  present) echo legacy > "$last" ;;
  *) exit 1 ;;
esac
"""


def _run(tmp_path: Path, *, restore="db", integrity="ok", quick="ok",
         legacy="missing", sqlite_installed=True):
    app = tmp_path / "app"
    (app / "data").mkdir(parents=True)
    (app / "litestream.yml").write_text("dbs: []\n")

    script = ENTRYPOINT.read_text()
    script = script.replace("/app/", f"{app}/")
    script = script.replace("INTEGRITY_TIMEOUT=60", "INTEGRITY_TIMEOUT=1")
    script = script.replace("INTEGRITY_KILL_AFTER=10", "INTEGRITY_KILL_AFTER=1")
    assert "INTEGRITY_TIMEOUT=1" in script and "INTEGRITY_KILL_AFTER=1" in script
    entry = tmp_path / "entrypoint.sh"
    entry.write_text(script)

    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in SYSTEM_TOOLS:
        found = shutil.which(tool)
        if found is None:
            pytest.skip(f"{tool} not available")
        (bindir / tool).symlink_to(found)
    stubs = {"litestream": LITESTREAM_STUB, "gsutil": GSUTIL_STUB, "envsubst": "#!/bin/sh\ncat\n"}
    if sqlite_installed:
        stubs["sqlite3"] = SQLITE_STUB
    for name, body in stubs.items():
        path = bindir / name
        path.write_text(body)
        path.chmod(0o755)

    gsutil_log = tmp_path / "gsutil.log"
    env = {
        "PATH": str(bindir),
        "HOME": str(tmp_path),
        "GCS_BUCKET": "test-bucket",
        "LITESTREAM_REPLICA_URL": "gs://test-bucket/litestream/amlkit.db",
        "STUB_RESTORE": restore,
        "STUB_INTEGRITY": integrity,
        "STUB_QUICK": quick,
        "STUB_LEGACY": legacy,
        "STUB_GSUTIL_LOG": str(gsutil_log),
    }
    proc = subprocess.run(
        ["sh", str(entry)], env=env, capture_output=True, text=True, timeout=60
    )
    data = app / "data"
    return {
        "rc": proc.returncode,
        "out": proc.stdout + proc.stderr,
        "db_present": (data / "amlkit.db").exists(),
        "quarantined": sorted(p.name for p in data.glob("amlkit.db.unverified-*")),
        "gsutil_calls": gsutil_log.read_text().splitlines() if gsutil_log.exists() else [],
    }


@pytest.mark.parametrize(
    "integrity, quick",
    [
        ("ok", "ok"),
        ("hang", "ok"),          # timed out (124), quick_check gives the verdict
        ("ignore_term", "ok"),   # needed SIGKILL (137): no verdict, not corruption
    ],
)
def test_verified_database_starts(tmp_path, integrity, quick):
    r = _run(tmp_path, integrity=integrity, quick=quick)
    assert r["rc"] == 0, r["out"]
    assert "APP STARTED" in r["out"]
    assert r["db_present"]
    assert r["gsutil_calls"] == []


@pytest.mark.parametrize(
    "integrity, quick, status",
    [
        ("hang", "hang", "unverifiable"),
        ("ignore_term", "ignore_term", "unverifiable"),
        ("problems", "ok", "corrupt"),
        ("malformed", "ok", "corrupt"),
        ("unopenable", "ok", "tool_error"),
    ],
)
def test_unverified_database_refuses_to_start(tmp_path, integrity, quick, status):
    r = _run(tmp_path, integrity=integrity, quick=quick)
    assert r["rc"] == 1, r["out"]
    assert "APP STARTED" not in r["out"]
    assert f"status: {status}" in r["out"]
    assert "gs://test-bucket/litestream/amlkit.db" in r["out"]
    # Moved aside, not deleted, and no fallback to the stale legacy snapshot.
    assert not r["db_present"]
    assert r["quarantined"] and r["quarantined"][0].startswith("amlkit.db.unverified-")
    assert r["gsutil_calls"] == []


def test_missing_sqlite3_refuses_without_deleting(tmp_path):
    r = _run(tmp_path, sqlite_installed=False)
    assert r["rc"] == 1, r["out"]
    assert "status: tool_error, exit 127" in r["out"]
    assert r["quarantined"]
    assert r["gsutil_calls"] == []


def test_failed_restore_refuses_without_stale_fallback(tmp_path):
    r = _run(tmp_path, restore="fail", legacy="present")
    assert r["rc"] == 1, r["out"]
    assert "status: restore_failed" in r["out"]
    assert "APP STARTED" not in r["out"]
    assert r["gsutil_calls"] == []
    assert not r["db_present"]


def test_no_replica_and_no_snapshot_starts_fresh(tmp_path):
    r = _run(tmp_path, restore="none", legacy="missing")
    assert r["rc"] == 0, r["out"]
    assert "starting fresh" in r["out"]
    assert "APP STARTED" in r["out"]
    assert len(r["gsutil_calls"]) == 1


def test_corrupt_legacy_snapshot_refuses_and_names_it(tmp_path):
    r = _run(tmp_path, restore="none", legacy="present", integrity="problems")
    assert r["rc"] == 1, r["out"]
    assert "legacy snapshot gs://test-bucket/amlkit.db" in r["out"]
    assert r["quarantined"]

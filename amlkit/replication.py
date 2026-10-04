"""Push the latest commits to the litestream replica before a response returns.

In production the app runs as `litestream replicate -exec`'s child process
(scripts/entrypoint.sh). Litestream ships the WAL to GCS from a 1-second
monitor loop, but Cloud Run throttles the container's CPU outside requests, so
the WAL written by the last request before an idle spell can sit unreplicated
until the next request wakes the instance. If the instance is replaced in that
gap, the write is gone.

`sync_replica()` closes that gap for the few writes that must not be lost: it
asks litestream, over its control socket (`socket:` in litestream.yml), to
sync now and wait until the replica has the current transaction
(`litestream sync -wait`, cmd/litestream/sync.go in litestream v0.5.x). It is
called after the sanctions refresh, report finalisation and freeze
execution -- not on ordinary page views, since it adds a GCS round trip.

Best-effort by design: it never raises, only logs. The write it follows is
already committed locally and litestream replicates it anyway; this only
shortens the window. It is a no-op when disabled (see `sync_enabled`), when
the litestream binary is not installed, or when its control socket is absent
(litestream not running), which covers tests and local development.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

# Must match `socket.path` in litestream.yml.
DEFAULT_SOCKET = "/tmp/litestream.sock"

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def sync_enabled() -> bool:
    """AMLKIT_SYNC_REPLICA wins when set; otherwise on iff a replica is configured."""
    value = os.environ.get("AMLKIT_SYNC_REPLICA", "").strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return bool(os.environ.get("LITESTREAM_REPLICA_URL", "").strip())


def _db_path() -> str:
    # Same resolution as api.deps.db_path(), without importing the web layer.
    # litestream matches the path exactly against its config's `dbs[].path`.
    from .db import DB_PATH

    override = os.environ.get("AMLKIT_DB")
    return os.path.abspath(Path(override) if override else DB_PATH)


def sync_replica(timeout: int = 30, *, reason: str = "") -> bool:
    """Block (up to about `timeout` seconds) until litestream has replicated
    the database's current transaction. Returns True on a confirmed sync,
    False otherwise. Never raises."""
    try:
        if not sync_enabled():
            return False
        exe = shutil.which("litestream")
        if exe is None:
            log.debug("replica sync skipped: litestream not installed")
            return False
        socket = os.environ.get("AMLKIT_LITESTREAM_SOCKET", "").strip() or DEFAULT_SOCKET
        if not os.path.exists(socket):
            log.warning("replica sync skipped (%s): no litestream control socket at %s", reason, socket)
            return False

        timeout = max(1, int(timeout))
        cmd = [exe, "sync", "-wait", "-timeout", str(timeout), "-socket", socket, _db_path()]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                # litestream's own -timeout is best-effort; this is the hard stop.
                timeout=timeout + 5,
            )
        except subprocess.TimeoutExpired:
            log.warning("replica sync (%s) timed out after %ss", reason, timeout + 5)
            return False

        if proc.returncode != 0:
            log.warning(
                "replica sync (%s) failed (exit %s): %s",
                reason, proc.returncode, (proc.stderr or proc.stdout or "").strip()[:500],
            )
            return False
        log.info("replica sync (%s) ok: %s", reason, " ".join((proc.stdout or "").split()))
        return True
    except Exception:  # best-effort: must never fail the request it follows
        log.exception("replica sync (%s) errored", reason)
        return False

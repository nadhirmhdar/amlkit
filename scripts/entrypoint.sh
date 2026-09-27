#!/bin/sh
set -e

mkdir -p /app/data

# Restore, then hand off to litestream for CONTINUOUS replication -- not just
# a one-time restore. Every write made between deploys used to live only on
# this container's ephemeral disk and vanish the moment Cloud Run recycled
# the instance (min-instances=0 makes that routine, not rare). litestream
# replicate -exec runs the app as its child process and streams the SQLite
# WAL to GCS as it's written, so a restart picks up from litestream's own
# replica rather than losing everything since the last manual snapshot.
# Map Cloud Run's PORT to the env var the app reads (AMLKIT_PORT).
# Cloud Run always injects PORT=8080; fall back to 8080 if absent.
export AMLKIT_PORT="${PORT:-8080}"

# Default to the original hardcoded bucket if not set
export LITESTREAM_REPLICA_URL="${LITESTREAM_REPLICA_URL:-gs://gen-lang-client-0153967509-aml-data/litestream/amlkit.db}"

# Template the litestream config (litestream doesn't do env-var substitution itself)
LITESTREAM_CFG=/tmp/litestream.yml
envsubst < /app/litestream.yml > "$LITESTREAM_CFG"

# Shared budget for the `PRAGMA integrity_check` calls in check_integrity()
# below (both the freshly-restored db and, if that one's rejected, the
# flat-file fallback).
INTEGRITY_TIMEOUT=60
INTEGRITY_KILL_AFTER=10

# Discard a database file together with its WAL-mode sidecar files. amlkit
# runs SQLite in WAL mode, so even a read-only `PRAGMA integrity_check` can
# create -wal/-shm files next to it; a plain `rm -f amlkit.db` can leave
# those behind, and a stale -wal/-shm sitting next to a freshly `gsutil cp`'d
# replacement db can make SQLite try to apply a WAL that doesn't match the
# file it now sits beside.
discard_db() {
    rm -f /app/data/amlkit.db /app/data/amlkit.db-wal /app/data/amlkit.db-shm
}

# Run `PRAGMA $2` (default: integrity_check) against $1, bounded by
# INTEGRITY_TIMEOUT/INTEGRITY_KILL_AFTER, and classify the result into one of
# five outcomes (left in $INTEGRITY_STATUS; exit code/output in
# $INTEGRITY_CODE/$INTEGRITY_OUTPUT for logging):
#   ok         -- confirmed healthy (exit 0, output contains "ok")
#   corrupt    -- confirmed bad (non-zero exit, or output does not match "ok")
#   timeout    -- check hit the timeout (exit 124); caller may retry
#   tool_error -- timeout/sqlite3 binary missing or broken (exit 125|126|127)
#   unverifiable -- quick_check also timed out after retry (used by verify_db)
#
# Plain `VAR=$(cmd)` would NOT survive `set -e`: `|| INTEGRITY_CODE=$?` puts
# the assignment in an or-list, exempting it from set -e (same pattern as
# `litestream restore ... || { }` below).
check_integrity() {
    local PRAGMA="${2:-integrity_check}"
    INTEGRITY_CODE=0
    INTEGRITY_OUTPUT=$(timeout -k "${INTEGRITY_KILL_AFTER}s" "${INTEGRITY_TIMEOUT}s" sqlite3 "$1" "PRAGMA $PRAGMA" 2>&1) || INTEGRITY_CODE=$?

    # Exit code classification:
    # 124: timeout itself killed the process (SIGTERM accepted)
    # 125: timeout's own failure (bad args, etc.)
    # 126: sqlite3 not executable
    # 127: sqlite3 not found
    # 137: timeout escalated to SIGKILL (target ignored SIGTERM); treat as corrupt
    #      per 2026-09-27: wedged in broken btree suggests corruption, not just slow
    if [ $INTEGRITY_CODE -eq 124 ]; then
        INTEGRITY_STATUS=timeout
    elif [ $INTEGRITY_CODE -eq 125 ] || [ $INTEGRITY_CODE -eq 126 ] || [ $INTEGRITY_CODE -eq 127 ]; then
        INTEGRITY_STATUS=tool_error
    elif [ $INTEGRITY_CODE -eq 0 ] && echo "$INTEGRITY_OUTPUT" | grep -q "^ok$"; then
        INTEGRITY_STATUS=ok
    elif [ $INTEGRITY_CODE -ne 0 ]; then
        INTEGRITY_STATUS=corrupt
    else
        INTEGRITY_STATUS=corrupt
    fi
}

# Verify database integrity: run integrity_check, and if that times out, retry
# with quick_check (same timeout budget). Result in $INTEGRITY_STATUS ∈
# {ok, corrupt, unverifiable, tool_error}.
verify_db() {
    check_integrity "$1" integrity_check
    if [ "$INTEGRITY_STATUS" = "timeout" ]; then
        check_integrity "$1" quick_check
        if [ "$INTEGRITY_STATUS" = "timeout" ]; then
            INTEGRITY_STATUS=unverifiable
        fi
    fi
}

if [ -n "$GCS_BUCKET" ] && [ ! -f /app/data/amlkit.db ]; then
    echo "Restoring from litestream replica at gs://${GCS_BUCKET}/litestream/amlkit.db, if one exists..."
    # `|| { ... }`: this script runs under `set -e`, so a failed restore --
    # not just "no replica exists yet" (which litestream handles gracefully
    # via -if-replica-exists and leaves no file), but a genuine restore
    # FAILURE (a corrupted/truncated segment, decode error, etc.) -- would
    # otherwise kill the whole script right here and crash-loop the
    # container forever, never reaching the legacy-snapshot fallback below
    # that exists specifically to handle "there's no usable database yet".
    # A failed restore and a missing replica must both fall through to that
    # same fallback, not just one of them.
    litestream restore -config "$LITESTREAM_CFG" -if-replica-exists /app/data/amlkit.db || {
        echo "litestream restore failed (corrupted replica?) -- falling through to legacy snapshot."
        # A failed restore can still have written a partial/corrupt file
        # (and, in principle, sidecar WAL/SHM files) before erroring out.
        # Remove it so the check below (which only asks "does a file
        # exist") isn't fooled into treating a broken half-written
        # database as a database that's already there.
        discard_db
    }

    if [ ! -f /app/data/amlkit.db ]; then
        echo "No litestream replica yet. Falling back to the legacy flat-file"
        echo "snapshot at gs://${GCS_BUCKET}/amlkit.db (pre-litestream data)..."
        gsutil cp "gs://${GCS_BUCKET}/amlkit.db" /app/data/amlkit.db \
            && echo "Restored legacy snapshot." \
            || echo "No snapshot found anywhere - starting fresh."
    fi

    if [ -f /app/data/amlkit.db ]; then
        echo "Checking database integrity..."
        verify_db /app/data/amlkit.db

        case "$INTEGRITY_STATUS" in
            ok)
                echo "Database integrity OK."
                ;;
            corrupt)
                echo "Database integrity check FAILED (exit $INTEGRITY_CODE). Output: $INTEGRITY_OUTPUT"
                echo "Falling back to legacy flat-file snapshot..."
                discard_db
                gsutil cp "gs://${GCS_BUCKET}/amlkit.db" /app/data/amlkit.db \
                    && echo "Restored from flat-file snapshot." \
                    || echo "Flat-file snapshot unavailable -- starting fresh."

                if [ -f /app/data/amlkit.db ]; then
                    echo "Verifying flat-file fallback..."
                    verify_db /app/data/amlkit.db
                    case "$INTEGRITY_STATUS" in
                        ok)
                            echo "Flat-file snapshot integrity verified."
                            ;;
                        corrupt)
                            echo "WARNING: Flat-file snapshot also corrupt (exit $INTEGRITY_CODE). Starting fresh."
                            discard_db
                            ;;
                        unverifiable|tool_error)
                            echo "FATAL: Cannot verify flat-file snapshot integrity (status: $INTEGRITY_STATUS, exit $INTEGRITY_CODE). File left in place untouched for investigation."
                            echo "Output: $INTEGRITY_OUTPUT"
                            exit 1
                            ;;
                    esac
                fi
                ;;
            unverifiable|tool_error)
                echo "FATAL: Cannot verify database integrity (status: $INTEGRITY_STATUS, exit $INTEGRITY_CODE). File left in place untouched for investigation."
                echo "Output: $INTEGRITY_OUTPUT"
                exit 1
                ;;
        esac
    fi
fi

echo "Starting amlkit web server under continuous litestream replication..."
exec litestream replicate -config "$LITESTREAM_CFG" -exec "python scripts/serve.py"

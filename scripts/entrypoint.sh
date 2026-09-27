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

# Shared budget for the `PRAGMA integrity_check` calls below (both the
# freshly-restored db and, if that one's rejected, the flat-file fallback).
# Defined once so the primary check and the fallback-verification check
# can't silently drift out of sync with each other.
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
        # 2026-09-27 incident: a corrupted replica made `PRAGMA integrity_check`
        # hang for 40+ minutes walking the broken btree/freelist. It never
        # returned, so the exit-code check below never fired, the fallback
        # path never ran, and Cloud Run crash-looped the container on every
        # retry. `timeout` bounds that: SIGTERM at ${INTEGRITY_TIMEOUT}s,
        # SIGKILL ${INTEGRITY_KILL_AFTER}s later via -k if it ignores that.
        #
        # Plain `VAR=$(cmd)` would NOT work here: under `set -e`, a failing
        # command substitution in a bare assignment kills the script right
        # here instead of falling through to the branches below -- verified
        # with `dash -c 'set -e; V=$(false); echo unreached'`. The
        # `|| INTEGRITY_CODE=$?` puts the assignment in an or-list, which
        # set -e exempts, the same way `litestream restore ... || { }`
        # above already relies on for the same reason.
        INTEGRITY_CODE=0
        INTEGRITY_OUTPUT=$(timeout -k "${INTEGRITY_KILL_AFTER}s" "${INTEGRITY_TIMEOUT}s" sqlite3 /app/data/amlkit.db "PRAGMA integrity_check" 2>&1) || INTEGRITY_CODE=$?

        if [ $INTEGRITY_CODE -eq 124 ]; then
            # A timeout is NOT proof of corruption -- litestream restore
            # itself already completed without error a few lines up; this
            # only means the verification step didn't finish in budget
            # (a large db, a slow/cold disk, CPU throttling on a cold
            # start...). amlkit retains AML records, so discarding a
            # possibly-healthy database and reverting to a stale flat-file
            # snapshot on nothing more than an ambiguous timeout would trade
            # a slow startup for silent data loss -- a worse outcome than
            # the thing we're fixing. Fail OPEN: log loudly and start with
            # the unverified database. Bounding the *hang* is what actually
            # fixes the 2026-09-27 crash-loop (worst case ~70s instead of
            # 40+ minutes); that's independent of how much we trust the
            # result once it's known to be inconclusive rather than bad.
            echo "WARNING: integrity check timed out after ${INTEGRITY_TIMEOUT}s -- inconclusive, NOT treated as confirmed corruption. Starting with the unverified database; investigate manually rather than assume corruption."
        elif [ $INTEGRITY_CODE -ne 0 ]; then
            echo "ERROR: sqlite3 command failed (exit code $INTEGRITY_CODE). Output: $INTEGRITY_OUTPUT"
            echo "Cannot verify integrity -- treating as potentially corrupt and falling back."
            discard_db
            gsutil cp "gs://${GCS_BUCKET}/amlkit.db" /app/data/amlkit.db \
                && echo "Restored from flat-file snapshot." \
                || echo "Flat-file snapshot unavailable -- starting fresh."
        elif echo "$INTEGRITY_OUTPUT" | grep -q "^ok$"; then
            echo "Database integrity OK."
        else
            echo "Database integrity check FAILED. Output: $INTEGRITY_OUTPUT"
            discard_db
            gsutil cp "gs://${GCS_BUCKET}/amlkit.db" /app/data/amlkit.db \
                && echo "Restored from flat-file snapshot." \
                || echo "Flat-file snapshot unavailable -- starting fresh."
        fi

        # Verify the flat-file fallback if we just restored it. Same
        # timeout-vs-confirmed-corrupt distinction as above: an inconclusive
        # check here starts with the unverified flat file rather than
        # wiping the database to empty.
        if [ -f /app/data/amlkit.db ]; then
            FALLBACK_CODE=0
            FALLBACK_CHECK=$(timeout -k "${INTEGRITY_KILL_AFTER}s" "${INTEGRITY_TIMEOUT}s" sqlite3 /app/data/amlkit.db "PRAGMA integrity_check" 2>&1) || FALLBACK_CODE=$?
            if [ $FALLBACK_CODE -eq 124 ]; then
                echo "WARNING: flat-file snapshot integrity check timed out after ${INTEGRITY_TIMEOUT}s -- inconclusive, starting with it anyway rather than wiping the database entirely."
            elif [ $FALLBACK_CODE -eq 0 ] && echo "$FALLBACK_CHECK" | grep -q "^ok$"; then
                echo "Flat-file snapshot integrity verified."
            else
                echo "WARNING: Flat-file snapshot also corrupt or unverifiable (exit: $FALLBACK_CODE). Starting fresh."
                discard_db
            fi
        fi
    fi
fi

echo "Starting amlkit web server under continuous litestream replication..."
exec litestream replicate -config "$LITESTREAM_CFG" -exec "python scripts/serve.py"

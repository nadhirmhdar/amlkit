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

if [ -n "$GCS_BUCKET" ] && [ ! -f /app/data/amlkit.db ]; then
    echo "Restoring from litestream replica at ${LITESTREAM_REPLICA_URL}, if one exists..."
    # `|| true`: this script runs under `set -e`, so a failed restore -- not
    # just "no replica exists yet" (which litestream handles gracefully via
    # -if-replica-exists and leaves no file), but a genuine restore FAILURE
    # (a corrupted/truncated segment, decode error, etc.) -- would otherwise
    # kill the whole script right here and crash-loop the container forever,
    # never reaching the legacy-snapshot fallback below that exists
    # specifically to handle "there's no usable database yet". A failed
    # restore and a missing replica must both fall through to that same
    # fallback, not just one of them.
    litestream restore -config "$LITESTREAM_CFG" -if-replica-exists /app/data/amlkit.db || {
        echo "litestream restore failed (corrupted replica?) -- falling through to legacy snapshot."
        # A failed restore can still have written a partial/corrupt file
        # before erroring out. Remove it so the check below (which only
        # asks "does a file exist") isn't fooled into treating a broken
        # half-written database as a database that's already there.
        rm -f /app/data/amlkit.db
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
        # `|| INTEGRITY_CODE=$?`: under `set -e` a failing $(...) assignment
        # kills the script on the spot with sqlite3's own exit code and no
        # message -- on 2026-09-27 that was a bare "exit(11)" (SQLITE_CORRUPT).
        INTEGRITY_CODE=0
        INTEGRITY_OUTPUT=$(sqlite3 /app/data/amlkit.db "PRAGMA integrity_check" 2>&1) || INTEGRITY_CODE=$?

        if [ "$INTEGRITY_CODE" -eq 0 ] && echo "$INTEGRITY_OUTPUT" | grep -q "^ok$"; then
            echo "Database integrity OK."
        else
            # Fail closed, deliberately. This used to fall back to the flat-file
            # snapshot (or an empty database), but that silently rolls
            # production back to the snapshot's date -- and litestream then
            # replicates the rolled-back state as the new truth. A loud crash
            # loses nothing; a quiet rollback loses everything since the
            # snapshot. Recover by hand: find the newest good point with
            # `litestream restore -txid <id> -o check.db <replica>` +
            # PRAGMA integrity_check, then seed a fresh replica from it.
            echo "FATAL: database failed its integrity check (sqlite3 exit $INTEGRITY_CODE): $INTEGRITY_OUTPUT"
            echo "FATAL: refusing to start rather than roll back to an older snapshot. Manual recovery required."
            exit 1
        fi
    fi
fi

echo "Starting amlkit web server under continuous litestream replication..."
exec litestream replicate -config "$LITESTREAM_CFG" -exec "python scripts/serve.py"

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
LITESTREAM_CFG=/app/litestream.yml

if [ -n "$GCS_BUCKET" ] && [ ! -f /app/data/amlkit.db ]; then
    echo "Restoring from litestream replica at gs://${GCS_BUCKET}/litestream/amlkit.db, if one exists..."
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
        INTEGRITY_OUTPUT=$(sqlite3 /app/data/amlkit.db "PRAGMA integrity_check" 2>&1)
        INTEGRITY_CODE=$?

        if [ $INTEGRITY_CODE -ne 0 ]; then
            echo "ERROR: sqlite3 command failed (exit code $INTEGRITY_CODE). Output: $INTEGRITY_OUTPUT"
            echo "Cannot verify integrity -- treating as potentially corrupt and falling back."
            rm -f /app/data/amlkit.db
            gsutil cp "gs://${GCS_BUCKET}/amlkit.db" /app/data/amlkit.db \
                && echo "Restored from flat-file snapshot." \
                || echo "Flat-file snapshot unavailable -- starting fresh."
        elif echo "$INTEGRITY_OUTPUT" | grep -q "^ok$"; then
            echo "Database integrity OK."
        else
            echo "Database integrity check FAILED. Output: $INTEGRITY_OUTPUT"
            rm -f /app/data/amlkit.db
            gsutil cp "gs://${GCS_BUCKET}/amlkit.db" /app/data/amlkit.db \
                && echo "Restored from flat-file snapshot." \
                || echo "Flat-file snapshot unavailable -- starting fresh."
        fi

        # Verify the flat-file fallback if we just restored it
        if [ -f /app/data/amlkit.db ]; then
            FALLBACK_CHECK=$(sqlite3 /app/data/amlkit.db "PRAGMA integrity_check" 2>&1)
            FALLBACK_CODE=$?
            if [ $FALLBACK_CODE -eq 0 ] && echo "$FALLBACK_CHECK" | grep -q "^ok$"; then
                echo "Flat-file snapshot integrity verified."
            else
                echo "WARNING: Flat-file snapshot also corrupt or unverifiable (exit: $FALLBACK_CODE). Starting fresh."
                rm -f /app/data/amlkit.db
            fi
        fi
    fi
fi

echo "Starting amlkit web server under continuous litestream replication..."
exec litestream replicate -config "$LITESTREAM_CFG" -exec "python scripts/serve.py"

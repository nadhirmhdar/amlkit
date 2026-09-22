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

# C2: Derive restore source from LITESTREAM_REPLICA_URL, not GCS_BUCKET.
# Hard-fail if no replica URL configured - cannot replicate to nowhere.
if [ -z "$LITESTREAM_REPLICA_URL" ]; then
    echo "FATAL: LITESTREAM_REPLICA_URL not set. Cannot restore or replicate database."
    echo "Set LITESTREAM_REPLICA_URL to gs://<bucket>/path/to/db"
    exit 1
fi

# Extract legacy snapshot bucket from LITESTREAM_REPLICA_URL for fallback
# gs://bucket-name/litestream/amlkit.db → gs://bucket-name/amlkit.db
LEGACY_BUCKET=$(echo "$LITESTREAM_REPLICA_URL" | sed -E 's|(gs://[^/]+)/.*|\1/amlkit.db|')

# Template the litestream config (litestream doesn't do env-var substitution itself)
LITESTREAM_CFG=/tmp/litestream.yml
envsubst < /app/litestream.yml > "$LITESTREAM_CFG"

if [ ! -f /app/data/amlkit.db ]; then
    echo "Restoring from litestream replica at $LITESTREAM_REPLICA_URL, if one exists..."
    # `|| {`: this script runs under `set -e`, so a failed restore -- not
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
        echo "snapshot at $LEGACY_BUCKET (pre-litestream data)..."
        gsutil cp "$LEGACY_BUCKET" /app/data/amlkit.db \
            && echo "Restored legacy snapshot." \
            || echo "No snapshot found anywhere - starting fresh."
    fi

    if [ -f /app/data/amlkit.db ]; then
        echo "Checking database integrity..."
        # H8 fix: Capture both output and exit code WITHOUT letting set -e kill the script
        INTEGRITY_OUTPUT=$(sqlite3 /app/data/amlkit.db "PRAGMA integrity_check" 2>&1) || INTEGRITY_CODE=$?

        if [ "${INTEGRITY_CODE:-0}" -ne 0 ]; then
            echo "ERROR: sqlite3 command failed (exit code $INTEGRITY_CODE). Output: $INTEGRITY_OUTPUT"
            echo "Cannot verify integrity -- treating as potentially corrupt and falling back."
            rm -f /app/data/amlkit.db
            gsutil cp "$LEGACY_BUCKET" /app/data/amlkit.db \
                && echo "Restored from flat-file snapshot." \
                || echo "Flat-file snapshot unavailable -- starting fresh."
        elif echo "$INTEGRITY_OUTPUT" | grep -q "^ok$"; then
            echo "Database integrity OK."
        else
            echo "Database integrity check FAILED. Output: $INTEGRITY_OUTPUT"
            rm -f /app/data/amlkit.db
            gsutil cp "$LEGACY_BUCKET" /app/data/amlkit.db \
                && echo "Restored from flat-file snapshot." \
                || echo "Flat-file snapshot unavailable -- starting fresh."
        fi

        # H8 fix: Verify the flat-file fallback if we just restored it
        if [ -f /app/data/amlkit.db ]; then
            FALLBACK_CHECK=$(sqlite3 /app/data/amlkit.db "PRAGMA integrity_check" 2>&1) || FALLBACK_CODE=$?
            if [ "${FALLBACK_CODE:-0}" -eq 0 ] && echo "$FALLBACK_CHECK" | grep -q "^ok$"; then
                echo "Flat-file snapshot integrity verified."
            else
                echo "WARNING: Flat-file snapshot also corrupt or unverifiable (exit: ${FALLBACK_CODE:-0}). Starting fresh."
                rm -f /app/data/amlkit.db
            fi
        fi
    fi
fi

# C2: Refuse to replicate an empty DB when a replica already exists (would clobber prod data)
if [ -f /app/data/amlkit.db ]; then
    ORG_COUNT=$(sqlite3 /app/data/amlkit.db "SELECT COUNT(*) FROM organizations WHERE 1" 2>/dev/null || echo "0")
    if [ "$ORG_COUNT" = "0" ]; then
        # Check if a replica generation already exists
        GENERATION_CHECK=$(litestream generations -config "$LITESTREAM_CFG" /app/data/amlkit.db 2>/dev/null | wc -l)
        if [ "$GENERATION_CHECK" -gt 1 ]; then
            echo "FATAL: Local DB has zero organizations but replica generation exists."
            echo "This would overwrite production data. Refusing to start."
            echo "Restore from backup or delete the replica first if intentional."
            exit 1
        fi
    fi
fi

echo "Starting amlkit web server under continuous litestream replication..."
exec litestream replicate -config "$LITESTREAM_CFG" -exec "python scripts/serve.py"

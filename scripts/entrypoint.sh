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
        # 2026-09-27 incident: a corrupted replica made `PRAGMA integrity_check`
        # hang for 40+ minutes walking the broken btree/freelist. It never
        # returned, so the exit-code check below never fired, the fallback
        # path never ran, and Cloud Run crash-looped the container on every
        # retry. `timeout` turns "hangs forever" into "fails after 60s"
        # (SIGTERM at 60s, SIGKILL 10s later via -k if it ignores that),
        # which the existing INTEGRITY_CODE -ne 0 branch already treats as
        # potentially corrupt and falls back from -- so a stuck check now
        # degrades exactly like a failed one instead of wedging startup.
        #
        # Plain `VAR=$(cmd)` would NOT work here: under `set -e`, a failing
        # command substitution in a bare assignment kills the script right
        # here instead of falling through to the `-ne 0` branch below --
        # verified with `dash -c 'set -e; V=$(false); echo unreached'`. The
        # `|| INTEGRITY_CODE=$?` puts the assignment in an or-list, which
        # set -e exempts, the same way the `litestream restore ... || { }`
        # above already relies on for the same reason.
        INTEGRITY_CODE=0
        INTEGRITY_OUTPUT=$(timeout -k 10s 60s sqlite3 /app/data/amlkit.db "PRAGMA integrity_check" 2>&1) || INTEGRITY_CODE=$?

        if [ $INTEGRITY_CODE -ne 0 ]; then
            if [ $INTEGRITY_CODE -eq 124 ]; then
                echo "ERROR: integrity check timed out after 60s (hung/severely corrupt replica)."
            fi
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
            FALLBACK_CODE=0
            FALLBACK_CHECK=$(timeout -k 10s 60s sqlite3 /app/data/amlkit.db "PRAGMA integrity_check" 2>&1) || FALLBACK_CODE=$?
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

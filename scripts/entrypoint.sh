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

# Temporary diagnostics: two prior deploys failed opaquely with
# "unknown replica type in config" and no further detail. Print exactly what
# litestream is actually parsing rather than keep guessing blind. Remove
# once replication is confirmed working end-to-end.
echo "--- litestream version ---"
litestream version || true
echo "--- litestream.yml as loaded in the image ---"
cat "$LITESTREAM_CFG" || true
echo "--- litestream config validation ---"
litestream databases -config "$LITESTREAM_CFG" || true
echo "--- end diagnostics ---"

if [ -n "$GCS_BUCKET" ] && [ ! -f /app/data/amlkit.db ]; then
    echo "Restoring from litestream replica at gs://${GCS_BUCKET}/litestream/amlkit.db, if one exists..."
    litestream restore -config "$LITESTREAM_CFG" -if-replica-exists /app/data/amlkit.db

    if [ ! -f /app/data/amlkit.db ]; then
        echo "No litestream replica yet. Falling back to the legacy flat-file"
        echo "snapshot at gs://${GCS_BUCKET}/amlkit.db (pre-litestream data)..."
        gsutil cp "gs://${GCS_BUCKET}/amlkit.db" /app/data/amlkit.db \
            && echo "Restored legacy snapshot." \
            || echo "No snapshot found anywhere - starting fresh."
    fi
fi

echo "Starting amlkit web server under continuous litestream replication..."
exec litestream replicate -config "$LITESTREAM_CFG" -exec "python scripts/serve.py"

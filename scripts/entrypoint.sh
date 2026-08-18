#!/bin/sh
set -e

mkdir -p /app/data

# Restore database snapshot directly from GCS if local DB does not exist
if [ -n "$GCS_BUCKET" ] && [ ! -f /app/data/amlkit.db ]; then
    echo "Attempting to restore database snapshot from gs://${GCS_BUCKET}/amlkit.db ..."
    gsutil cp "gs://${GCS_BUCKET}/amlkit.db" /app/data/amlkit.db && echo "Database restored from GCS snapshot." || echo "No GCS snapshot found - will start with a fresh database."
fi

echo "Starting amlkit web server..."
exec python scripts/serve.py

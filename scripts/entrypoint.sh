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

# No default replica. The old default was the litestream/ prefix abandoned as
# corrupt on 2026-09-27, and any hardcoded default lets a deploy that forgot
# the variable restore from -- and then replicate into -- the wrong place.
if [ -z "$LITESTREAM_REPLICA_URL" ]; then
    echo "FATAL: LITESTREAM_REPLICA_URL is not set. Refusing to start: without it there is no way to know which replica holds this deployment's data."
    exit 1
fi
export LITESTREAM_REPLICA_URL

# Template the litestream config (litestream doesn't do env-var substitution itself)
LITESTREAM_CFG=/tmp/litestream.yml
envsubst < /app/litestream.yml > "$LITESTREAM_CFG"

# Budget per PRAGMA run. verify_db runs at most two (integrity_check, then
# quick_check), so the worst case is ~2 x (60+10)s = 140s -- inside Cloud
# Run's default 240s startup window. Overrunning it matters: being killed by
# the startup probe mid-check is the silent crash-loop of 2026-09-27.
# AMLKIT_INTEGRITY_TIMEOUT raises the budget if the database outgrows it (a
# healthy check that times out twice refuses to start); keep 2 x (timeout +
# kill-after) under the service's startup window. Each check logs its duration
# so the trend is visible well before that.
INTEGRITY_TIMEOUT="${AMLKIT_INTEGRITY_TIMEOUT:-60}"
INTEGRITY_KILL_AFTER="${AMLKIT_INTEGRITY_KILL_AFTER:-10}"

# Refuse to start on a database we could not positively verify. Serving it
# would let `litestream replicate` stream it over the replica, and the old
# alternatives -- the months-old pre-litestream snapshot or an empty database
# -- would silently roll back AML records in the same way. A non-zero exit
# trips the amlkit_startup_failures alert instead. The local file (and WAL
# sidecars) is moved aside so a restart on a persistent volume can't skip
# verification: the restore/verify block below only runs when amlkit.db is
# absent.
refuse_to_start() {
    q="/app/data/amlkit.db.unverified-$(date -u +%Y%m%dT%H%M%SZ)"
    moved=""
    for f in amlkit.db amlkit.db-wal amlkit.db-shm; do
        if [ -f "/app/data/$f" ]; then
            # `|| true`: under set -e a failed mv (read-only volume,
            # permissions) would exit before the FATAL line below.
            mv "/app/data/$f" "$q${f#amlkit.db}" && moved=1 || true
        fi
    done
    echo "FATAL: $1 (status: $INTEGRITY_STATUS, exit $INTEGRITY_CODE). Refusing to start."
    if [ -n "$INTEGRITY_OUTPUT" ]; then
        echo "Output: $INTEGRITY_OUTPUT"
    fi
    if [ -n "$moved" ]; then
        echo "Local copy moved to $q -- container-local, so on Cloud Run it is gone with this instance; the durable evidence is the replica at ${LITESTREAM_REPLICA_URL}."
    fi
    echo "Recovery: investigate that replica, then seed a verified-clean database with the recovery-reseed workflow (.github/workflows/recovery-reseed.yml)."
    exit 1
}

# Run `PRAGMA $2` (default integrity_check) against $1, bounded by
# INTEGRITY_TIMEOUT/INTEGRITY_KILL_AFTER. Leaves $INTEGRITY_STATUS as one of
#   ok          the pragma ran and reported exactly "ok"
#   corrupt     the pragma reported problems, or sqlite3 said the file is
#               malformed / not a database
#   timeout     no verdict in time: 124 (died to SIGTERM) or 137 (needed the
#               -k SIGKILL -- wedged in uninterruptible I/O, or OOM-killed
#               under --memory 1Gi); says nothing about the file itself
#   tool_error  the check itself could not run: 125-127 (timeout/sqlite3
#               broken or missing), or any other sqlite3 error that is not a
#               corruption report ("unable to open database file", locked...)
# plus the raw $INTEGRITY_CODE / $INTEGRITY_OUTPUT for logging.
#
# Plain `VAR=$(cmd)` would NOT survive `set -e`: `|| INTEGRITY_CODE=$?` puts
# the assignment in an or-list, exempting it from set -e.
check_integrity() {
    INTEGRITY_PRAGMA="${2:-integrity_check}"
    INTEGRITY_CODE=0
    started=$(date +%s)
    INTEGRITY_OUTPUT=$(timeout -k "${INTEGRITY_KILL_AFTER}s" "${INTEGRITY_TIMEOUT}s" sqlite3 "$1" "PRAGMA $INTEGRITY_PRAGMA" 2>&1) || INTEGRITY_CODE=$?
    echo "PRAGMA $INTEGRITY_PRAGMA finished in $(( $(date +%s) - started ))s (limit ${INTEGRITY_TIMEOUT}s, exit $INTEGRITY_CODE)."

    case "$INTEGRITY_CODE" in
        0)
            if [ "$INTEGRITY_OUTPUT" = "ok" ]; then
                INTEGRITY_STATUS=ok
            else
                INTEGRITY_STATUS=corrupt
            fi
            ;;
        124|137)
            INTEGRITY_STATUS=timeout
            ;;
        125|126|127)
            INTEGRITY_STATUS=tool_error
            ;;
        *)
            # sqlite3 exits 1 for any error, so the code alone is not a
            # corruption verdict -- only its own wording is.
            if echo "$INTEGRITY_OUTPUT" | grep -qiE 'malformed|corrupt|not a database|\*\*\* in database'; then
                INTEGRITY_STATUS=corrupt
            else
                INTEGRITY_STATUS=tool_error
            fi
            ;;
    esac
}

# integrity_check, retried once as the cheaper quick_check if it produced no
# verdict. Leaves $INTEGRITY_STATUS as ok | corrupt | tool_error |
# unverifiable (both runs timed out).
verify_db() {
    check_integrity "$1" integrity_check
    if [ "$INTEGRITY_STATUS" = "timeout" ]; then
        check_integrity "$1" quick_check
        if [ "$INTEGRITY_STATUS" = "timeout" ]; then
            INTEGRITY_STATUS=unverifiable
        fi
    fi
}

# Keyed on the database file alone, not on GCS_BUCKET: a deploy missing that
# variable used to skip the restore and replicate an empty database over the
# real replica.
if [ ! -f /app/data/amlkit.db ]; then
    echo "Restoring from litestream replica at ${LITESTREAM_REPLICA_URL}..."
    # -if-replica-exists makes "no replica" a clean no-op, handled below; any
    # other failure (corrupted/truncated segment, decode error, auth) refuses
    # to start -- `|| { }` so set -e doesn't kill the script before it can
    # say why.
    litestream restore -config "$LITESTREAM_CFG" -if-replica-exists /app/data/amlkit.db || {
        INTEGRITY_CODE=$?
        INTEGRITY_STATUS=restore_failed
        INTEGRITY_OUTPUT=""
        refuse_to_start "litestream restore from ${LITESTREAM_REPLICA_URL} failed"
    }

    if [ ! -f /app/data/amlkit.db ]; then
        # No replica at that URL. For a brand-new deployment that is expected;
        # anywhere else it means a mistyped URL or an emptied prefix, and
        # starting would serve an empty (or, before this, a months-old
        # pre-litestream) database and replicate it as the new truth. So a
        # fresh start must be asked for explicitly, for one boot.
        if [ "${AMLKIT_ALLOW_FRESH_START:-}" = "1" ]; then
            echo "No replica at ${LITESTREAM_REPLICA_URL}; AMLKIT_ALLOW_FRESH_START=1, so starting with an empty database."
            echo "Unset AMLKIT_ALLOW_FRESH_START once this deployment has written its first replica."
        else
            INTEGRITY_CODE=0
            INTEGRITY_STATUS=no_replica
            INTEGRITY_OUTPUT=""
            refuse_to_start "no litestream replica found at ${LITESTREAM_REPLICA_URL} (set AMLKIT_ALLOW_FRESH_START=1 only for a brand-new deployment)"
        fi
    else
        echo "Checking database integrity..."
        verify_db /app/data/amlkit.db
        if [ "$INTEGRITY_STATUS" = "ok" ]; then
            echo "Database integrity OK."
        else
            refuse_to_start "database restored from litestream replica ${LITESTREAM_REPLICA_URL} failed verification"
        fi
    fi
fi

echo "Starting amlkit web server under continuous litestream replication..."
exec litestream replicate -config "$LITESTREAM_CFG" -exec "python scripts/serve.py"

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

# Run `PRAGMA integrity_check` against $1, bounded by INTEGRITY_TIMEOUT/
# INTEGRITY_KILL_AFTER, and classify the result into exactly one of three
# outcomes (left in $INTEGRITY_STATUS; raw exit code/output left in
# $INTEGRITY_CODE/$INTEGRITY_OUTPUT for logging) so callers make one
# decision instead of duplicating the exit-code/output parsing:
#   ok            -- confirmed healthy
#   corrupt       -- confirmed bad: explicit integrity errors, or sqlite3
#                    couldn't even open the file
#   inconclusive  -- check didn't finish in time; NOT evidence of
#                    corruption (see the call site for why that matters)
#
# 2026-09-27 incident: a corrupted replica made a bare, untimed
# `PRAGMA integrity_check` hang for 40+ minutes walking the broken
# btree/freelist, so a later exit-code check for "did it fail" never even
# ran, the fallback path never fired, and Cloud Run crash-looped the
# container on every retry. `timeout` bounds that.
#
# Plain `VAR=$(cmd)` would NOT survive `set -e` here: a failing command
# substitution in a bare assignment kills the script right at that line
# instead of falling through to the classification below -- verified with
# `dash -c 'set -e; V=$(false); echo unreached'`. `|| INTEGRITY_CODE=$?`
# puts the assignment in an or-list, which set -e exempts, the same way
# `litestream restore ... || { }` below already relies on for the same
# reason.
check_integrity() {
    INTEGRITY_CODE=0
    INTEGRITY_OUTPUT=$(timeout -k "${INTEGRITY_KILL_AFTER}s" "${INTEGRITY_TIMEOUT}s" sqlite3 "$1" "PRAGMA integrity_check" 2>&1) || INTEGRITY_CODE=$?

    # `timeout` exits 124 when its own SIGTERM is what stopped the process,
    # but 137 (128+SIGKILL) when the process ignored SIGTERM and only died
    # to the `-k` grace-period SIGKILL instead -- verified empirically:
    # `timeout -k 2s 1s sh -c 'trap "" TERM; sleep 5'` exits 137, not 124.
    # These are NOT equivalent: a plain sqlite3 process has no SIGTERM
    # handler, so a *healthy-but-slow* check dies cleanly to the first
    # signal (124). Needing the -k escalation to SIGKILL (137) means
    # something was wrong beyond "just slow" -- wedged in an uninterruptible
    # read walking corrupted structures, or dying to an unrelated fatal
    # condition like an OOM kill triggered by that same corruption. Either
    # way that's grounds to distrust the file, not fail open on it, so only
    # 124 is treated as merely inconclusive; 137 is treated as corrupt.
    if [ $INTEGRITY_CODE -eq 124 ]; then
        INTEGRITY_STATUS=inconclusive
    elif [ $INTEGRITY_CODE -ne 0 ]; then
        INTEGRITY_STATUS=corrupt
    elif echo "$INTEGRITY_OUTPUT" | grep -q "^ok$"; then
        INTEGRITY_STATUS=ok
    else
        INTEGRITY_STATUS=corrupt
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
        check_integrity /app/data/amlkit.db

        case "$INTEGRITY_STATUS" in
            ok)
                echo "Database integrity OK."
                ;;
            inconclusive)
                # NOT proof of corruption -- litestream restore itself
                # already completed without error a few lines up; this only
                # means the verification step didn't finish in budget (a
                # large db, a slow/cold disk, CPU throttling on a cold
                # start...). amlkit retains AML records, so discarding a
                # possibly-healthy database and reverting to a stale
                # flat-file snapshot on nothing more than an ambiguous
                # timeout would trade a slow startup for silent data loss --
                # a worse outcome than the thing we're fixing. Fail OPEN:
                # log loudly and start with the unverified database.
                # Bounding the *hang* (not this decision) is what actually
                # fixes the 2026-09-27 crash-loop -- worst case is now one
                # ~70s check, not 40+ minutes of retries.
                echo "WARNING: integrity check timed out after ${INTEGRITY_TIMEOUT}s -- inconclusive, NOT treated as confirmed corruption. Starting with the unverified database; investigate manually rather than assume corruption."
                ;;
            corrupt)
                echo "Database integrity check FAILED (exit $INTEGRITY_CODE). Output: $INTEGRITY_OUTPUT"
                echo "Falling back to legacy flat-file snapshot..."
                discard_db
                gsutil cp "gs://${GCS_BUCKET}/amlkit.db" /app/data/amlkit.db \
                    && echo "Restored from flat-file snapshot." \
                    || echo "Flat-file snapshot unavailable -- starting fresh."

                # Verify the fallback we just restored -- but only if we
                # actually replaced the file. A same-file re-check belongs
                # only here (confirmed-corrupt path), not on every startup:
                # re-running the identical bounded check against the exact
                # file that just timed out would double the worst-case
                # startup delay (~140s instead of ~70s) for no new
                # information, so the `inconclusive` case above deliberately
                # does not fall into this block.
                if [ -f /app/data/amlkit.db ]; then
                    echo "Verifying flat-file fallback..."
                    check_integrity /app/data/amlkit.db
                    case "$INTEGRITY_STATUS" in
                        ok)
                            echo "Flat-file snapshot integrity verified."
                            ;;
                        inconclusive)
                            echo "WARNING: flat-file snapshot integrity check timed out after ${INTEGRITY_TIMEOUT}s -- inconclusive, starting with it anyway rather than wiping the database entirely."
                            ;;
                        corrupt)
                            echo "WARNING: Flat-file snapshot also corrupt (exit $INTEGRITY_CODE). Starting fresh."
                            discard_db
                            ;;
                    esac
                fi
                ;;
        esac
    fi
fi

echo "Starting amlkit web server under continuous litestream replication..."
exec litestream replicate -config "$LITESTREAM_CFG" -exec "python scripts/serve.py"

#!/usr/bin/env bash
# Run every monitoring script in order. Safe to re-run.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
for s in 01-uptime-check.sh 02-log-metrics.sh 03-alert-policies.sh 04-dashboard.sh; do
  echo "== $s"; bash "$HERE/$s"
done

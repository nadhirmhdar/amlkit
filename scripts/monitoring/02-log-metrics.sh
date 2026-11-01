#!/usr/bin/env bash
# Log-based metrics. Idempotent (create, or update when present).
#   amlkit_freeze_overdue  one count per hourly /system/check-freeze-obligations
#                          run that found overdue_count > 0 (amlkit/ops.py).
#   amlkit_5xx             Cloud Run request-log entries with status >= 500.
source "$(dirname "$0")/common.sh"

upsert_metric() {
  local name="$1" desc="$2" filter="$3" tmp
  tmp="$(mktemp)"
  FILTER="$filter" DESC="$desc" python3 - >"$tmp" <<'PY'
import json, os
print(json.dumps({"description": os.environ["DESC"], "filter": os.environ["FILTER"]}))
PY
  if gcloud logging metrics describe "$name" --project "$PROJECT" >/dev/null 2>&1; then
    gcloud logging metrics update "$name" --project "$PROJECT" --config-from-file="$tmp" >/dev/null
    echo "updated metric: $name"
  else
    gcloud logging metrics create "$name" --project "$PROJECT" --config-from-file="$tmp" >/dev/null
    echo "created metric: $name"
  fi
  rm -f "$tmp"
}

upsert_metric amlkit_freeze_overdue \
  "Freeze-obligation check runs that found overdue (>24h) obligations" \
  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE\" AND jsonPayload.message=~\"^freeze_obligation_check \" AND jsonPayload.overdue_count>0"

upsert_metric amlkit_5xx \
  "Cloud Run requests answered with a 5xx status" \
  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE\" AND logName:\"run.googleapis.com%2Frequests\" AND httpRequest.status>=500"

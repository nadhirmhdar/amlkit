#!/usr/bin/env bash
# Four alert policies. Idempotent (create, or update by display name).
# Run 01 and 02 first: the uptime and freeze policies reference them.
source "$(dirname "$0")/common.sh"
CHANNEL="$(resolve_channel)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# 1. 5xx rate > 1% over 10 minutes (ratio of built-in request_count series).
cat >"$TMP/5xx.json" <<JSON
{
  "displayName": "groAML 5xx rate > 1% (10 min)",
  "combiner": "OR",
  "notificationChannels": ["$CHANNEL"],
  "conditions": [{
    "displayName": "5xx / all requests > 1%",
    "conditionThreshold": {
      "filter": "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\"",
      "denominatorFilter": "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE\" AND metric.type=\"run.googleapis.com/request_count\"",
      "aggregations": [{"alignmentPeriod": "600s", "perSeriesAligner": "ALIGN_SUM", "crossSeriesReducer": "REDUCE_SUM"}],
      "denominatorAggregations": [{"alignmentPeriod": "600s", "perSeriesAligner": "ALIGN_SUM", "crossSeriesReducer": "REDUCE_SUM"}],
      "comparison": "COMPARISON_GT", "thresholdValue": 0.01, "duration": "0s",
      "trigger": {"count": 1}
    }
  }]
}
JSON
upsert_policy "$TMP/5xx.json" "groAML 5xx rate > 1% (10 min)"

# 2. Overdue freeze obligations (TFS: 24h execution window).
cat >"$TMP/freeze.json" <<JSON
{
  "displayName": "groAML overdue freeze obligations > 0",
  "combiner": "OR",
  "notificationChannels": ["$CHANNEL"],
  "conditions": [{
    "displayName": "freeze check found overdue obligations",
    "conditionThreshold": {
      "filter": "metric.type=\"logging.googleapis.com/user/amlkit_freeze_overdue\" AND resource.type=\"cloud_run_revision\"",
      "aggregations": [{"alignmentPeriod": "3600s", "perSeriesAligner": "ALIGN_SUM", "crossSeriesReducer": "REDUCE_SUM"}],
      "comparison": "COMPARISON_GT", "thresholdValue": 0, "duration": "0s",
      "trigger": {"count": 1}
    }
  }],
  "alertStrategy": {"autoClose": "7200s"}
}
JSON
upsert_policy "$TMP/freeze.json" "groAML overdue freeze obligations > 0"

# 3. Uptime failure (needs the check created by 01-uptime-check.sh).
CHECK_ID="$(gcloud monitoring uptime list-configs --project "$PROJECT" \
  --filter='displayName="groAML /health"' --format='value(name)' | head -n1 | awk -F/ '{print $NF}')"
if [ -z "$CHECK_ID" ]; then echo "uptime check not found - run 01-uptime-check.sh first" >&2; exit 1; fi
cat >"$TMP/uptime.json" <<JSON
{
  "displayName": "groAML /health uptime failure",
  "combiner": "OR",
  "notificationChannels": ["$CHANNEL"],
  "conditions": [{
    "displayName": "uptime check failing",
    "conditionThreshold": {
      "filter": "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.labels.check_id=\"$CHECK_ID\" AND resource.type=\"uptime_url\"",
      "aggregations": [{"alignmentPeriod": "300s", "perSeriesAligner": "ALIGN_NEXT_OLDER", "crossSeriesReducer": "REDUCE_COUNT_FALSE", "groupByFields": ["resource.label.*"]}],
      "comparison": "COMPARISON_GT", "thresholdValue": 1, "duration": "0s",
      "trigger": {"count": 1}
    }
  }]
}
JSON
upsert_policy "$TMP/uptime.json" "groAML /health uptime failure"

# 4. Litestream sync failures: matches the warnings logged by
#    amlkit/replication.py ("replica sync (<reason>) failed / timed out / errored").
#    The "skipped" warning (no socket, e.g. dev) is deliberately not matched.
cat >"$TMP/sync.json" <<JSON
{
  "displayName": "groAML replica sync failure",
  "combiner": "OR",
  "notificationChannels": ["$CHANNEL"],
  "conditions": [{
    "displayName": "litestream sync failed",
    "conditionMatchedLog": {
      "filter": "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE\" AND jsonPayload.logger=\"amlkit.replication\" AND severity>=WARNING AND jsonPayload.message=~\"^replica sync \\\\(.*\\\\) (failed|timed out|errored)\""
    }
  }],
  "alertStrategy": {"notificationRateLimit": {"period": "3600s"}, "autoClose": "86400s"}
}
JSON
upsert_policy "$TMP/sync.json" "groAML replica sync failure"

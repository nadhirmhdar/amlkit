#!/usr/bin/env bash
# Shared settings for the groAML monitoring scripts. Edit PROJECT (or export it)
# before running; nothing else in this directory hard-codes a project.
set -euo pipefail

PROJECT="${PROJECT:-CHANGE-ME-gcp-project-id}"   # <-- the GCP project the Cloud Run service lives in
REGION="${REGION:-me-central1}"                    # Cloud Run region (vars.GCP_REGION in the deploy)
SERVICE="${SERVICE:-amlkit}"                       # Cloud Run service name
HOST="${HOST:-groaml.grovisor.ae}"                 # public host for the uptime check
ALERT_EMAIL="${ALERT_EMAIL:-info@grovisor.ae}"     # used only when NOTIFICATION_CHANNEL is unset
# Full channel resource name (projects/<p>/notificationChannels/<id>). When
# unset, 01-notification-channel.sh creates/finds an email channel for ALERT_EMAIL.
NOTIFICATION_CHANNEL="${NOTIFICATION_CHANNEL:-}"

if [ "$PROJECT" = "CHANGE-ME-gcp-project-id" ]; then
  echo "Set PROJECT (export PROJECT=<gcp-project-id>) or edit scripts/monitoring/common.sh" >&2
  exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Resolve the notification channel once (creating the email channel if needed).
resolve_channel() {
  if [ -n "$NOTIFICATION_CHANNEL" ]; then echo "$NOTIFICATION_CHANNEL"; return; fi
  local found
  found="$(gcloud monitoring channels list --project "$PROJECT" \
    --filter="type=\"email\" AND labels.email_address=\"$ALERT_EMAIL\"" \
    --format='value(name)' | head -n1)"
  if [ -z "$found" ]; then
    found="$(gcloud monitoring channels create --project "$PROJECT" \
      --display-name="groAML alerts ($ALERT_EMAIL)" --type=email \
      --channel-labels="email_address=$ALERT_EMAIL" --format='value(name)')"
  fi
  echo "$found"
}

# Create the alert policy in $1 (JSON file) or update it when one with the same
# displayName ($2) already exists.
upsert_policy() {
  local file="$1" name="$2" existing
  existing="$(gcloud monitoring policies list --project "$PROJECT" \
    --filter="displayName=\"$name\"" --format='value(name)' | head -n1)"
  if [ -n "$existing" ]; then
    gcloud monitoring policies update "$existing" --project "$PROJECT" --policy-from-file="$file" >/dev/null
    echo "updated policy: $name"
  else
    gcloud monitoring policies create --project "$PROJECT" --policy-from-file="$file" >/dev/null
    echo "created policy: $name"
  fi
}

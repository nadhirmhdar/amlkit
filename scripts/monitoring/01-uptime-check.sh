#!/usr/bin/env bash
# HTTPS uptime check on /health. Idempotent: updates the check if it exists.
source "$(dirname "$0")/common.sh"
NAME="groAML /health"
existing="$(gcloud monitoring uptime list-configs --project "$PROJECT" \
  --filter="displayName=\"$NAME\"" --format='value(name)' | head -n1)"
common=(--project "$PROJECT" --period=1 --timeout=10)
if [ -n "$existing" ]; then
  gcloud monitoring uptime update "$existing" "${common[@]}" --path=/health >/dev/null
  echo "updated uptime check: $NAME"
else
  gcloud monitoring uptime create "$NAME" "${common[@]}" \
    --resource-type=uptime-url \
    --resource-labels="host=$HOST,project_id=$PROJECT" \
    --protocol=https --port=443 --path=/health --validate-ssl=true >/dev/null
  echo "created uptime check: $NAME"
fi

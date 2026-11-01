#!/usr/bin/env bash
# Cloud Monitoring dashboard from dashboard.json. Idempotent by display name.
source "$(dirname "$0")/common.sh"
TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
sed "s/__SERVICE__/$SERVICE/g" "$HERE/dashboard.json" >"$TMP"
NAME="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["displayName"])' "$TMP")"
existing="$(gcloud monitoring dashboards list --project "$PROJECT" \
  --filter="displayName=\"$NAME\"" --format='value(name)' | head -n1)"
if [ -n "$existing" ]; then
  # update needs the current etag inside the config
  etag="$(gcloud monitoring dashboards describe "$existing" --project "$PROJECT" --format='value(etag)')"
  python3 - "$TMP" "$etag" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["etag"] = sys.argv[2]
json.dump(d, open(sys.argv[1], "w"))
PY
  gcloud monitoring dashboards update "$existing" --project "$PROJECT" --config-from-file="$TMP" >/dev/null
  echo "updated dashboard: $NAME"
else
  gcloud monitoring dashboards create --project "$PROJECT" --config-from-file="$TMP" >/dev/null
  echo "created dashboard: $NAME"
fi

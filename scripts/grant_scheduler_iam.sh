#!/bin/bash
# One-time setup: lets the CI deploy service account create/update the
# Cloud Scheduler job that hits /system/refresh (see .github/workflows/
# source-canary.yml's "Wire up Cloud Scheduler sanctions refresh" step).
#
# Run this once, from a terminal where `gcloud` is authenticated as an
# Owner/IAM Admin on the project (e.g. Cloud Shell, logged in as
# nadhirmhd.ar@gmail.com). It does two things a routine CI deploy
# deliberately doesn't do itself, to keep that service account narrowly
# scoped (see setup_github_deploy_auth.sh):
#
#   1. Enables the Cloud Scheduler API -- a one-time, project-level
#      setting, not something that needs re-doing on every deploy.
#   2. Grants the deploy service account roles/cloudscheduler.admin --
#      the minimum needed to create/update that one job, nothing broader
#      (specifically NOT roles/serviceusage.serviceUsageAdmin, which
#      would let it enable/disable arbitrary APIs on the project).
set -euo pipefail

PROJECT_ID="gen-lang-client-0153967509"
SA_EMAIL="github-deployer@${PROJECT_ID}.iam.gserviceaccount.com"

echo "== Enabling Cloud Scheduler API =="
gcloud services enable cloudscheduler.googleapis.com --project "$PROJECT_ID"

echo "== Granting roles/cloudscheduler.admin to ${SA_EMAIL} =="
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudscheduler.admin" \
  --condition=None \
  --quiet

echo ""
echo "========================================================================"
echo "DONE. The next deploy's 'Wire up Cloud Scheduler sanctions refresh' step"
echo "will now create the amlkit-sanctions-refresh job (every 20h, calling"
echo "/system/refresh) instead of failing with PERMISSION_DENIED."
echo "========================================================================"

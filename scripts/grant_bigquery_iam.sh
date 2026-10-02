#!/bin/bash
# One-time setup: lets the running amlkit Cloud Run service query BigQuery
# for the daily GDELT GKG net-cast (see ingest/gdelt_gkg.py and the
# "Wire up Cloud Scheduler GDELT watch" step in
# .github/workflows/source-canary.yml, which calls /system/gdelt-watch).
#
# Run this once, from a terminal where `gcloud` is authenticated as an
# Owner/IAM Admin on the project (e.g. Cloud Shell, logged in as
# nadhirmhd.ar@gmail.com).
#
# This grants the PROJECT'S DEFAULT COMPUTE SERVICE ACCOUNT, not
# github-deployer -- deploy's `gcloud run deploy` in the workflow never
# passes --service-account, so Cloud Run runs the deployed container under
# that default identity. github-deployer only ever creates/updates the
# Cloud Run service and the Scheduler job; it never runs inside the
# container, so it does not need (and does not get) BigQuery access itself.
#
# roles/bigquery.jobUser is the minimum that lets a principal RUN a query
# job and have it billed to this project -- it grants no access to any
# dataset's rows beyond what the query's own ACL/public-dataset grants
# already allow, which for gdelt-bq.gdeltv2.* is "public, anyone." There is
# no dataset-level grant to add here: that table is already public.
set -euo pipefail

PROJECT_ID="gen-lang-client-0153967509"
PROJECT_NUMBER="720622408077"
DEFAULT_COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "== Enabling the BigQuery API (one-time, project-level) =="
gcloud services enable bigquery.googleapis.com --project "$PROJECT_ID"

echo "== Granting roles/bigquery.jobUser to ${DEFAULT_COMPUTE_SA} =="
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEFAULT_COMPUTE_SA}" \
  --role="roles/bigquery.jobUser" \
  --condition=None \
  --quiet

echo ""
echo "========================================================================"
echo "DONE. The Cloud Run service can now run BigQuery query jobs billed to"
echo "$PROJECT_ID. Combined with AMLKIT_GCP_PROJECT_ID being set on the"
echo "service (added to the deploy step's --set-env-vars) and the"
echo "'Wire up Cloud Scheduler GDELT watch' step, the next deploy turns the"
echo "daily net-cast on end to end."
echo ""
echo "No dataset-level grant was needed: gdelt-bq.gdeltv2.gkg_partitioned is"
echo "a public BigQuery dataset. jobUser only lets this project RUN queries"
echo "and be billed for them -- verified live against this project's own"
echo "billing before ingest/gdelt_gkg.py was written (see that module's"
echo "docstring for the real cost numbers)."
echo "========================================================================"

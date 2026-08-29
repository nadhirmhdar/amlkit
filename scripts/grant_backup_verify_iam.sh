#!/bin/bash
# One-time setup: lets .github/workflows/backup-verify.yml restore the
# litestream replica to a scratch path in CI and verify it's not corrupted.
#
# Run this once, from a terminal where `gcloud` is authenticated as an
# Owner/IAM Admin on the project (e.g. Cloud Shell, logged in as
# nadhirmhd.ar@gmail.com). Creates a NEW, separate service account rather
# than widening github-deployer (see setup_github_deploy_auth.sh): that SA
# is deliberately scoped with no access to the app's data bucket, and this
# one exists for exactly the opposite, narrow purpose -- read-only access to
# one bucket, nothing else, so the two don't share a blast radius.
set -euo pipefail

PROJECT_ID="gen-lang-client-0153967509"
PROJECT_NUMBER="720622408077"
REPO="nadhirmhdar/amlkit"
BUCKET="gen-lang-client-0153967509-aml-data"
SA_NAME="backup-verifier"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
# Reuses the same Workload Identity Pool/provider setup_github_deploy_auth.sh
# already created -- one pool backing multiple narrowly-scoped service
# accounts, each with their own impersonation binding below, rather than a
# second pool for every new purpose.
POOL_ID="github-pool"

echo "== Creating backup-verifier service account (skips if it already exists) =="
gcloud iam service-accounts create "$SA_NAME" \
  --project "$PROJECT_ID" \
  --display-name "Backup restore verification (amlkit CI, read-only)" \
  || echo "(already exists, continuing)"

echo "== Granting read-only access to just gs://${BUCKET}, nothing else =="
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectViewer" \
  --condition=None

echo "== Allowing only this repo's workflows to impersonate the service account =="
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${REPO}" \
  --quiet

echo ""
echo "========================================================================"
echo "DONE. One value backup-verify.yml needs:"
echo ""
echo "  GCP_BACKUP_VERIFY_SA = ${SA_EMAIL}"
echo ""
echo "Either paste that back to Claude, or set it yourself with:"
echo ""
echo "  gh variable set GCP_BACKUP_VERIFY_SA -b \"${SA_EMAIL}\" -R ${REPO}"
echo ""
echo "GCP_WIF_PROVIDER, GCP_PROJECT_ID, and GCS_BUCKET are already set from"
echo "setup_github_deploy_auth.sh and are reused as-is -- nothing else to add."
echo "========================================================================"

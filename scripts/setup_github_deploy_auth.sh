#!/bin/bash
# One-time setup: lets GitHub Actions deploy amlkit to Cloud Run without any
# long-lived key file, via Workload Identity Federation (WIF). Run this once,
# from a terminal where `gcloud` is authenticated as an Owner/IAM Admin on the
# project (e.g. `gcloud auth login` as nadhirmhd.ar@gmail.com).
#
# After it finishes, it prints two values (WIF provider + service account
# email) -- give those back so the GitHub Actions workflow can be wired up,
# or run the `gh variable set` commands it prints yourself.
set -euo pipefail

PROJECT_ID="gen-lang-client-0153967509"
PROJECT_NUMBER="720622408077"
REPO="nadhirmhdar/amlkit"
REGION="me-central1"
BUCKET="gen-lang-client-0153967509-aml-data"
SA_NAME="github-deployer"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
POOL_ID="github-pool"
PROVIDER_ID="github-provider"

echo "== Enabling required APIs =="
gcloud services enable sts.googleapis.com iamcredentials.googleapis.com --project "$PROJECT_ID"

echo "== Creating deployer service account (skips if it already exists) =="
gcloud iam service-accounts create "$SA_NAME" \
  --project "$PROJECT_ID" \
  --display-name "GitHub Actions Deployer (amlkit CI/CD)" \
  || echo "(already exists, continuing)"

echo "== Granting deploy-only roles (no access to the app's data bucket) =="
for ROLE in roles/run.admin roles/iam.serviceAccountUser roles/artifactregistry.writer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$ROLE" \
    --condition=None \
    --quiet
done

echo "== Creating the Artifact Registry repo the workflow pushes images to =="
# The deploy workflow builds with Docker Buildx and pushes straight to
# Artifact Registry -- NOT 'gcloud builds submit' (tried first; abandoned
# after three confirmed-correct IAM grants -- storage.objectAdmin,
# serviceusage.serviceUsageConsumer, storage.admin on the Cloud Build staging
# bucket -- still left the identical "forbidden from accessing the bucket"
# error. Root cause was a confirmed gcloud/gsutil client bug, closed
# "not planned" upstream: that command's source-upload step does not
# correctly consume Workload Identity Federation credentials, so no amount of
# IAM on the intended service account could ever fix it). artifactregistry.writer
# (above) lets the SA push to a repo, but creating the repo itself needs
# artifactregistry.admin, which this SA deliberately does NOT have -- that's
# a one-time provisioning step for whoever runs this script, not something
# routine deploys should be able to do.
gcloud artifacts repositories create amlkit \
  --repository-format=docker \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --description="amlkit container images" \
  || echo "(already exists, continuing)"

echo "== Creating Workload Identity Pool =="
gcloud iam workload-identity-pools create "$POOL_ID" \
  --project="$PROJECT_ID" \
  --location="global" \
  --display-name="GitHub Actions Pool" \
  || echo "(already exists, continuing)"

echo "== Creating OIDC provider, restricted to this repo only =="
gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
  --project="$PROJECT_ID" \
  --location="global" \
  --workload-identity-pool="$POOL_ID" \
  --display-name="GitHub provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository=='${REPO}'" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  || echo "(already exists, continuing)"

echo "== Allowing only this repo's workflows to impersonate the service account =="
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${REPO}" \
  --quiet

WIF_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/providers/${PROVIDER_ID}"

echo ""
echo "========================================================================"
echo "DONE. Two values the GitHub Actions workflow needs:"
echo ""
echo "  GCP_WIF_PROVIDER    = ${WIF_PROVIDER}"
echo "  GCP_SERVICE_ACCOUNT = ${SA_EMAIL}"
echo ""
echo "Either paste those back to Claude, or set them yourself with:"
echo ""
echo "  gh variable set GCP_WIF_PROVIDER    -b \"${WIF_PROVIDER}\" -R ${REPO}"
echo "  gh variable set GCP_SERVICE_ACCOUNT -b \"${SA_EMAIL}\" -R ${REPO}"
echo "  gh variable set GCP_PROJECT_ID       -b \"${PROJECT_ID}\" -R ${REPO}"
echo "  gh variable set GCP_REGION           -b \"${REGION}\" -R ${REPO}"
echo "  gh variable set GCS_BUCKET           -b \"${BUCKET}\" -R ${REPO}"
echo "========================================================================"

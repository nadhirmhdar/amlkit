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
# serviceusage.serviceUsageConsumer: without it, 'gcloud builds submit' fails
# with "The user is forbidden from accessing the bucket [..._cloudbuild]" --
# a misleading error text (it reads like a storage permission problem, and
# the first fix attempted here targeted the bucket's own IAM policy instead)
# for what the gcloud error message itself actually points at: the SA isn't
# allowed to "use" enabled services against this project's quota/billing.
for ROLE in roles/run.admin roles/iam.serviceAccountUser roles/cloudbuild.builds.editor roles/artifactregistry.writer roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$ROLE" \
    --condition=None \
    --quiet
done

echo "== Granting access to the Cloud Build staging bucket =="
# 'gcloud builds submit' uploads source to gs://<PROJECT_ID>_cloudbuild before
# it can build anything. cloudbuild.builds.editor (above) lets the SA queue
# and watch builds, but grants nothing on that bucket -- confirmed by a real
# first-deploy failure: "The user is forbidden from accessing the bucket
# [gen-lang-client-0153967509_cloudbuild]". Two earlier attempts at this grant
# (storage.objectAdmin on the bucket, then serviceusage.serviceUsageConsumer
# on the project -- both genuinely required, both still applied above/below)
# left the exact same error, because 'gcloud builds submit' also calls
# storage.buckets.get/storage.buckets.list on the staging bucket itself
# before it uploads anything, and objectAdmin does not include those --
# only a bucket-*admin* role does. Scoped to this ONE auto-created staging
# bucket, not project-wide storage, so this stays deploy-only and never
# touches the app's own data bucket ($BUCKET above).
CLOUDBUILD_BUCKET="${PROJECT_ID}_cloudbuild"
gcloud storage buckets add-iam-policy-binding "gs://${CLOUDBUILD_BUCKET}" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.admin" \
  --quiet \
  || echo "(gs://${CLOUDBUILD_BUCKET} doesn't exist yet -- Cloud Build auto-creates it on someone's first 'gcloud builds submit'. Re-run this script after that first build, or run the binding above manually once the bucket exists.)"

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

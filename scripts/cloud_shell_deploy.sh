#!/bin/bash
set -e

# Resolve project ID string even if user set project number
RAW_PROJECT=$(gcloud config get-value project 2>/dev/null)

if [ -z "$RAW_PROJECT" ] || [ "$RAW_PROJECT" = "(unset)" ]; then
    echo "No default GCP project set in Cloud Shell."
    echo "Your available GCP Projects:"
    gcloud projects list --format="table(projectId, name)" || true
    echo ""
    read -p "Please enter your GCP Project ID string from above: " RAW_PROJECT
fi

# Convert project number to canonical string Project ID if needed
PROJECT_ID=$(gcloud projects describe "$RAW_PROJECT" --format="value(projectId)" 2>/dev/null || echo "$RAW_PROJECT")
gcloud config set project "$PROJECT_ID"

REGION="me-central1"
SERVICE_NAME="amlkit"
BUCKET_NAME="${PROJECT_ID}-aml-data"

echo "Deploying amlkit to Cloud Run in Project ID: ${PROJECT_ID} (${REGION}) utilizing $300 GCP Trial Credits..."

# Ensure APIs enabled
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# Create GCS Bucket if missing
if ! gcloud storage buckets describe "gs://${BUCKET_NAME}" > /dev/null 2>&1; then
    gcloud storage buckets create "gs://${BUCKET_NAME}" --location="${REGION}"
fi

# Optimized for $300 Trial Credits:
# - 1Gi RAM & 1 vCPU for high-speed screening performance
# - max-instances 10 allows fast concurrent testing between UAE and India
# - min-instances 0 ensures 0 credit burn when idle
gcloud builds submit . --tag "gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest" --project "${PROJECT_ID}"

gcloud run deploy "${SERVICE_NAME}" \
    --image "gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest" \
    --platform managed \
    --region "${REGION}" \
    --allow-unauthenticated \
    --set-env-vars "GCS_BUCKET=${BUCKET_NAME},AMLKIT_BIND_HOST=0.0.0.0,AMLKIT_PORT=8000,AMLKIT_BEHIND_PROXY=1" \
    --port 8000 \
    --memory 1Gi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 10

URL=$(gcloud run services describe "${SERVICE_NAME}" --platform managed --region "${REGION}" --format "value(status.url)")

echo "========================================================"
echo "DEPLOYMENT COMPLETE (OPTIMIZED FOR $300 FREE CREDITS)!"
echo "Memory: 1GB | CPU: 1 vCPU | Max Instances: 10"
echo "Idle Cost: $0.00 (min-instances 0)"
echo "Live Web URL: ${URL}"
echo "========================================================"

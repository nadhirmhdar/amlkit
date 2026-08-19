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
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com cloudscheduler.googleapis.com

# Create GCS Bucket if missing
if ! gcloud storage buckets describe "gs://${BUCKET_NAME}" > /dev/null 2>&1; then
    gcloud storage buckets create "gs://${BUCKET_NAME}" --location="${REGION}"
fi

# Optimized for $300 Trial Credits:
# - 1Gi RAM & 1 vCPU for high-speed screening performance
# - max-instances 10 allows fast concurrent testing between UAE and India
# - min-instances 0 ensures 0 credit burn when idle
gcloud builds submit . --tag "gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest" --project "${PROJECT_ID}"

# SCHEDULER_SECRET / ADMIN_API_SECRET gate the /system/* endpoints (see
# app.py). Reuse whatever is already deployed rather than regenerating on
# every deploy -- `gcloud run deploy --set-env-vars` REPLACES the entire env
# var set, so a naive redeploy would otherwise silently rotate these out
# from under Cloud Scheduler's existing job.
EXISTING_VARS=$(gcloud run services describe "${SERVICE_NAME}" --platform managed --region "${REGION}" --format "value(spec.template.spec.containers[0].env)" 2>/dev/null || echo "")
extract_existing() {
    echo "$EXISTING_VARS" | grep -oE "$1=[^,}]+" | head -1 | cut -d= -f2-
}
SCHEDULER_SECRET=$(extract_existing SCHEDULER_SECRET)
[ -z "$SCHEDULER_SECRET" ] && SCHEDULER_SECRET=$(openssl rand -hex 24)
ADMIN_API_SECRET=$(extract_existing ADMIN_API_SECRET)
[ -z "$ADMIN_API_SECRET" ] && ADMIN_API_SECRET=$(openssl rand -hex 24)

# --timeout 900: /system/refresh now runs the sanctions refresh
# SYNCHRONOUSLY (see app.py) so Cloud Run's autoscaler sees it as an
# in-flight request and won't freeze/kill the instance mid-refresh -- the
# request just needs to be allowed to run long enough. 900s is generous
# headroom over its measured real-world duration.
gcloud run deploy "${SERVICE_NAME}" \
    --image "gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest" \
    --platform managed \
    --region "${REGION}" \
    --allow-unauthenticated \
    --set-env-vars "GCS_BUCKET=${BUCKET_NAME},AMLKIT_BIND_HOST=0.0.0.0,AMLKIT_PORT=8000,AMLKIT_BEHIND_PROXY=1,SCHEDULER_SECRET=${SCHEDULER_SECRET},ADMIN_API_SECRET=${ADMIN_API_SECRET}" \
    --port 8000 \
    --memory 1Gi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 10 \
    --timeout 900

URL=$(gcloud run services describe "${SERVICE_NAME}" --platform managed --region "${REGION}" --format "value(status.url)")

# Every 20 hours: safely inside the 24-hour EOCN rule with margin for a
# slow/retried run, same reasoning as the in-process scheduler's 23-hour
# interval (see app.py) but reliable across Cloud Run scaling to zero,
# which the in-process one is not.
JOB_NAME="${SERVICE_NAME}-sanctions-refresh"
if gcloud scheduler jobs describe "$JOB_NAME" --location "${REGION}" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "$JOB_NAME" \
        --location "${REGION}" \
        --schedule "0 */20 * * *" \
        --uri "${URL}/system/refresh" \
        --http-method POST \
        --message-body "{}" \
        --headers "Authorization=Bearer ${SCHEDULER_SECRET}" \
        --attempt-deadline 900s
else
    gcloud scheduler jobs create http "$JOB_NAME" \
        --location "${REGION}" \
        --schedule "0 */20 * * *" \
        --uri "${URL}/system/refresh" \
        --http-method POST \
        --message-body "{}" \
        --headers "Authorization=Bearer ${SCHEDULER_SECRET}" \
        --attempt-deadline 900s
fi

echo "========================================================"
echo "DEPLOYMENT COMPLETE (OPTIMIZED FOR $300 FREE CREDITS)!"
echo "Memory: 1GB | CPU: 1 vCPU | Max Instances: 10"
echo "Idle Cost: $0.00 (min-instances 0)"
echo "Automatic sanctions refresh: every 20h via Cloud Scheduler job ${JOB_NAME}"
echo "Live Web URL: ${URL}"
echo "========================================================"

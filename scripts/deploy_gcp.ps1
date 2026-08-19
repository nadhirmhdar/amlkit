<#
.SYNOPSIS
    Automates building and deploying amlkit to Google Cloud Run using $300 GCP Trial Credits.
.EXAMPLE
    .\scripts\deploy_gcp.ps1 -ProjectId "my-gcp-project-id" -Region "me-central1"
#>

param (
    [Parameter(Mandatory=$true)]
    [string]$ProjectId,
    [string]$Region = "me-central1",
    [string]$ServiceName = "amlkit"
)

$ErrorActionPreference = "Stop"
$BucketName = "${ProjectId}-aml-data"

Write-Host "Setting GCP Project: $ProjectId" -ForegroundColor Cyan
gcloud config set project $ProjectId

Write-Host "Ensuring Cloud Storage Bucket exists (gs://$BucketName)..." -ForegroundColor Cyan
gcloud storage buckets describe "gs://$BucketName" 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud storage buckets create "gs://$BucketName" --location=$Region
}

Write-Host "Enabling Cloud Run, Cloud Build and Cloud Scheduler APIs..." -ForegroundColor Cyan
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com cloudscheduler.googleapis.com

Write-Host "Building Docker image with Google Cloud Build..." -ForegroundColor Cyan
gcloud builds submit "c:\Users\nadhi\Cluade connect\AML" --tag "gcr.io/$ProjectId/$ServiceName:latest"

# SCHEDULER_SECRET / ADMIN_API_SECRET gate the /system/* endpoints (see app.py).
# Reuse whatever is already deployed rather than regenerating on every deploy --
# `gcloud run deploy --set-env-vars` REPLACES the entire env var set (unlike
# `services update --update-env-vars`), so a naive redeploy would otherwise
# silently rotate these out from under Cloud Scheduler's existing job and
# invalidate anyone who'd saved the admin secret to provision operators.
$existingVars = gcloud run services describe $ServiceName --platform managed --region $Region --format "value(spec.template.spec.containers[0].env)" 2>$null
function Get-ExistingEnvValue([string]$Name) {
    if ($existingVars -match "$Name=([^,}]+)") { return $Matches[1] }
    return $null
}
$SchedulerSecret = Get-ExistingEnvValue "SCHEDULER_SECRET"
if (-not $SchedulerSecret) { $SchedulerSecret = -join ((1..48) | ForEach-Object { "{0:x}" -f (Get-Random -Max 16) }) }
$AdminApiSecret = Get-ExistingEnvValue "ADMIN_API_SECRET"
if (-not $AdminApiSecret) { $AdminApiSecret = -join ((1..48) | ForEach-Object { "{0:x}" -f (Get-Random -Max 16) }) }

Write-Host "Deploying to Google Cloud Run (Optimized for $300 Free Credits)..." -ForegroundColor Cyan
# --timeout 900: /system/refresh now runs the sanctions refresh SYNCHRONOUSLY
# (see app.py) so Cloud Run's autoscaler sees it as an in-flight request and
# won't freeze/kill the instance mid-refresh -- the request just needs to be
# allowed to run long enough. 900s is generous headroom over its measured
# real-world duration (well under a minute for the current source set).
gcloud run deploy $ServiceName `
    --image "gcr.io/$ProjectId/$ServiceName:latest" `
    --platform managed `
    --region $Region `
    --allow-unauthenticated `
    --set-env-vars "GCS_BUCKET=$BucketName,AMLKIT_BIND_HOST=0.0.0.0,AMLKIT_PORT=8000,AMLKIT_BEHIND_PROXY=1,SCHEDULER_SECRET=$SchedulerSecret,ADMIN_API_SECRET=$AdminApiSecret" `
    --port 8000 `
    --memory 1Gi `
    --cpu 1 `
    --min-instances 0 `
    --max-instances 10 `
    --timeout 900

$ServiceUrl = (gcloud run services describe $ServiceName --platform managed --region $Region --format "value(status.url)")

Write-Host "Wiring up the automatic sanctions-list refresh (Cloud Scheduler)..." -ForegroundColor Cyan
# Every 20 hours: safely inside the 24-hour EOCN rule with margin for a
# slow/retried run, same reasoning as the in-process scheduler's 23-hour
# interval (see app.py) but reliable across Cloud Run scaling to zero,
# which the in-process one is not.
$JobName = "$ServiceName-sanctions-refresh"
$jobExists = gcloud scheduler jobs describe $JobName --location $Region 2>$null
if ($LASTEXITCODE -eq 0) {
    gcloud scheduler jobs update http $JobName `
        --location $Region `
        --schedule "0 */20 * * *" `
        --uri "$ServiceUrl/system/refresh" `
        --http-method POST `
        --message-body "{}" `
        --headers "Authorization=Bearer $SchedulerSecret" `
        --attempt-deadline 900s
} else {
    gcloud scheduler jobs create http $JobName `
        --location $Region `
        --schedule "0 */20 * * *" `
        --uri "$ServiceUrl/system/refresh" `
        --http-method POST `
        --message-body "{}" `
        --headers "Authorization=Bearer $SchedulerSecret" `
        --attempt-deadline 900s
}

Write-Host "`n========================================================" -ForegroundColor Green
Write-Host "SUCCESS! amlkit is deployed to Cloud Run." -ForegroundColor Green
Write-Host "Optimized for $300 Free Trial Credits (1GB RAM, 1 vCPU)" -ForegroundColor Green
Write-Host "Web URL: $ServiceUrl" -ForegroundColor Yellow
Write-Host "Share this URL with your IT colleague in India!" -ForegroundColor Yellow
Write-Host "========================================================`n" -ForegroundColor Green

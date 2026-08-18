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

Write-Host "Enabling Cloud Run and Cloud Build APIs..." -ForegroundColor Cyan
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

Write-Host "Building Docker image with Google Cloud Build..." -ForegroundColor Cyan
gcloud builds submit "c:\Users\nadhi\Cluade connect\AML" --tag "gcr.io/$ProjectId/$ServiceName:latest"

Write-Host "Deploying to Google Cloud Run (Optimized for $300 Free Credits)..." -ForegroundColor Cyan
gcloud run deploy $ServiceName `
    --image "gcr.io/$ProjectId/$ServiceName:latest" `
    --platform managed `
    --region $Region `
    --allow-unauthenticated `
    --set-env-vars "GCS_BUCKET=$BucketName,AMLKIT_BIND_HOST=0.0.0.0,AMLKIT_PORT=8000,AMLKIT_BEHIND_PROXY=1" `
    --port 8000 `
    --memory 1Gi `
    --cpu 1 `
    --min-instances 0 `
    --max-instances 10

$ServiceUrl = (gcloud run services describe $ServiceName --platform managed --region $Region --format "value(status.url)")

Write-Host "`n========================================================" -ForegroundColor Green
Write-Host "SUCCESS! amlkit is deployed to Cloud Run." -ForegroundColor Green
Write-Host "Optimized for $300 Free Trial Credits (1GB RAM, 1 vCPU)" -ForegroundColor Green
Write-Host "Web URL: $ServiceUrl" -ForegroundColor Yellow
Write-Host "Share this URL with your IT colleague in India!" -ForegroundColor Yellow
Write-Host "========================================================`n" -ForegroundColor Green

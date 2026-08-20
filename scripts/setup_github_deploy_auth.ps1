<#
.SYNOPSIS
    One-time setup: lets GitHub Actions deploy amlkit to Cloud Run without any
    long-lived key file, via Workload Identity Federation (WIF).
.DESCRIPTION
    Run this once, from a terminal where `gcloud` is authenticated as an
    Owner/IAM Admin on the project (gcloud auth list should show
    nadhirmhd.ar@gmail.com as ACTIVE).

    After it finishes, it prints two values (WIF provider + service account
    email) and the exact `gh variable set` commands to run next.
.EXAMPLE
    .\scripts\setup_github_deploy_auth.ps1
#>

$ErrorActionPreference = "Stop"

$ProjectId = "gen-lang-client-0153967509"
$ProjectNumber = "720622408077"
$Repo = "nadhirmhdar/amlkit"
$Region = "me-central1"
$Bucket = "gen-lang-client-0153967509-aml-data"
$SaName = "github-deployer"
$SaEmail = "$SaName@$ProjectId.iam.gserviceaccount.com"
$PoolId = "github-pool"
$ProviderId = "github-provider"

Write-Host "== Enabling required APIs ==" -ForegroundColor Cyan
gcloud services enable sts.googleapis.com iamcredentials.googleapis.com --project $ProjectId

Write-Host "== Creating deployer service account (skips if it already exists) ==" -ForegroundColor Cyan
gcloud iam service-accounts create $SaName `
    --project $ProjectId `
    --display-name "GitHub Actions Deployer (amlkit CI/CD)"
if ($LASTEXITCODE -ne 0) { Write-Host "(already exists, continuing)" -ForegroundColor Yellow }

Write-Host "== Granting deploy-only roles (no access to the app's data bucket) ==" -ForegroundColor Cyan
$Roles = @(
    "roles/run.admin",
    "roles/iam.serviceAccountUser",
    "roles/cloudbuild.builds.editor",
    "roles/artifactregistry.writer"
)
foreach ($Role in $Roles) {
    gcloud projects add-iam-policy-binding $ProjectId `
        --member="serviceAccount:$SaEmail" `
        --role="$Role" `
        --condition=None `
        --quiet
}

Write-Host "== Granting access to the Cloud Build staging bucket ==" -ForegroundColor Cyan
# 'gcloud builds submit' uploads source to gs://<ProjectId>_cloudbuild before
# it can build anything. cloudbuild.builds.editor (above) lets the SA queue
# and watch builds, but grants nothing on that bucket -- confirmed by a real
# first-deploy failure: "The user is forbidden from accessing the bucket
# [gen-lang-client-0153967509_cloudbuild]". Scoped to this ONE auto-created
# staging bucket, not project-wide storage, so this stays deploy-only and
# never touches the app's own data bucket ($Bucket above).
$CloudBuildBucket = "${ProjectId}_cloudbuild"
gcloud storage buckets add-iam-policy-binding "gs://$CloudBuildBucket" `
    --project=$ProjectId `
    --member="serviceAccount:$SaEmail" `
    --role="roles/storage.objectAdmin" `
    --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "(gs://$CloudBuildBucket doesn't exist yet -- Cloud Build auto-creates it on someone's first 'gcloud builds submit'. Re-run this script after that first build, or run the binding above manually once the bucket exists.)" -ForegroundColor Yellow }

Write-Host "== Creating Workload Identity Pool ==" -ForegroundColor Cyan
gcloud iam workload-identity-pools create $PoolId `
    --project=$ProjectId `
    --location="global" `
    --display-name="GitHub Actions Pool"
if ($LASTEXITCODE -ne 0) { Write-Host "(already exists, continuing)" -ForegroundColor Yellow }

Write-Host "== Creating OIDC provider, restricted to this repo only ==" -ForegroundColor Cyan
gcloud iam workload-identity-pools providers create-oidc $ProviderId `
    --project=$ProjectId `
    --location="global" `
    --workload-identity-pool=$PoolId `
    --display-name="GitHub provider" `
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" `
    --attribute-condition="assertion.repository=='$Repo'" `
    --issuer-uri="https://token.actions.githubusercontent.com"
if ($LASTEXITCODE -ne 0) { Write-Host "(already exists, continuing)" -ForegroundColor Yellow }

Write-Host "== Allowing only this repo's workflows to impersonate the service account ==" -ForegroundColor Cyan
gcloud iam service-accounts add-iam-policy-binding $SaEmail `
    --project=$ProjectId `
    --role="roles/iam.workloadIdentityUser" `
    --member="principalSet://iam.googleapis.com/projects/$ProjectNumber/locations/global/workloadIdentityPools/$PoolId/attribute.repository/$Repo" `
    --quiet

$WifProvider = "projects/$ProjectNumber/locations/global/workloadIdentityPools/$PoolId/providers/$ProviderId"

Write-Host ""
Write-Host "========================================================================" -ForegroundColor Green
Write-Host "DONE. Two values the GitHub Actions workflow needs:" -ForegroundColor Green
Write-Host ""
Write-Host "  GCP_WIF_PROVIDER    = $WifProvider"
Write-Host "  GCP_SERVICE_ACCOUNT = $SaEmail"
Write-Host ""
Write-Host "Run these to finish wiring GitHub Actions:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  gh variable set GCP_WIF_PROVIDER    -b `"$WifProvider`" -R $Repo"
Write-Host "  gh variable set GCP_SERVICE_ACCOUNT -b `"$SaEmail`" -R $Repo"
Write-Host "  gh variable set GCP_PROJECT_ID       -b `"$ProjectId`" -R $Repo"
Write-Host "  gh variable set GCP_REGION           -b `"$Region`" -R $Repo"
Write-Host "  gh variable set GCS_BUCKET           -b `"$Bucket`" -R $Repo"
Write-Host "========================================================================" -ForegroundColor Green

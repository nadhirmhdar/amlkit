<#
.SYNOPSIS
    Backs up the amlkit workspace and database snapshot to Google Cloud Storage (GCS).
.EXAMPLE
    .\scripts\backup_to_gcs.ps1 -GcsBucket "my-aml-project-backups"
#>

param (
    [Parameter(Mandatory=$true)]
    [string]$GcsBucket,
    [string]$Note = "amlkit-snapshot"
)

$ErrorActionPreference = "Stop"

$Timestamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$ArchiveName = "${Timestamp}_${Note}.zip"
$TempZip = Join-Path $env:TEMP $ArchiveName

Write-Host "Creating local zip snapshot..." -ForegroundColor Cyan
Compress-Archive -Path "c:\Users\nadhi\Cluade connect\AML\*" -DestinationPath $TempZip -Force

Write-Host "Uploading snapshot to gs://$GcsBucket/backups/$ArchiveName ..." -ForegroundColor Cyan
gcloud storage cp $TempZip "gs://$GcsBucket/backups/$ArchiveName"

Remove-Item -Path $TempZip -Force -ErrorAction SilentlyContinue

Write-Host "Backup complete! Saved to gs://$GcsBucket/backups/$ArchiveName" -ForegroundColor Green

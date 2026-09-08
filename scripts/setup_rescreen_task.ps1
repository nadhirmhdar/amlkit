<#
.SYNOPSIS
    Register the 23-hour auto-rescreen task with Windows Task Scheduler.

.DESCRIPTION
    Creates (or replaces) a scheduled task that runs auto_rescreen.py every
    23 hours, starting 30 minutes after the daily sanctions-list refresh.
    The 23-hour interval ensures the task drifts through the clock rather than
    always firing at the same wall-clock time, which reduces the risk of a
    systematic gap if the refresh itself is delayed.

    The task writes its stdout/stderr to logs\auto_rescreen.log beside the
    script. A new log file is created each day (date suffix). Logs older than
    30 days are pruned automatically at the start of each run.

.PARAMETER PythonExe
    Full path to the Python interpreter in the project's virtual environment.
    Defaults to .venv\Scripts\python.exe relative to the amlkit repo root.

.PARAMETER StartTime
    Wall-clock time for the first run today (HH:MM, 24-hour). Defaults to
    06:30 (i.e. 30 min after the 06:00 refresh task defined in refresh.py).

.EXAMPLE
    .\scripts\setup_rescreen_task.ps1
    .\scripts\setup_rescreen_task.ps1 -PythonExe "C:\Python311\python.exe" -StartTime "07:00"
#>
[CmdletBinding()]
param(
    [string]$PythonExe = "",
    [string]$StartTime = "06:30"
)

$ErrorActionPreference = "Stop"

# ── resolve paths ────────────────────────────────────────────────────────────
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot    = Split-Path -Parent $ScriptDir
$ScriptPath  = Join-Path $ScriptDir "auto_rescreen.py"
$LogDir      = Join-Path $RepoRoot  "logs"

if (-not $PythonExe) {
    $PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
}

foreach ($p in @($PythonExe, $ScriptPath)) {
    if (-not (Test-Path $p)) {
        Write-Error "Not found: $p`nUpdate -PythonExe or activate the venv first."
        exit 1
    }
}

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# ── task definition ──────────────────────────────────────────────────────────
$TaskName   = "AML auto-rescreen (23h)"
$TaskDesc   = "Re-screen all customers 23 h after the daily sanctions refresh."

# Wrap in cmd /c so stdout+stderr land in the log file.
$LogFile    = Join-Path $LogDir "auto_rescreen_%DATE:~-4,4%%DATE:~-7,2%%DATE:~0,2%.log"
$Action     = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$PythonExe`" `"$ScriptPath`" >> `"$LogFile`" 2>&1"

# Repeat every 23 hours. Task Scheduler does not accept MaxValue as duration;
# use a Once trigger with a 10-year repetition window instead.
$Trigger    = New-ScheduledTaskTrigger -Once -At $StartTime `
    -RepetitionInterval  (New-TimeSpan -Hours 23) `
    -RepetitionDuration  (New-TimeSpan -Days 3650)

$Settings   = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit  (New-TimeSpan -Hours 2) `
    -MultipleInstances   IgnoreNew `
    -StartWhenAvailable  `
    -RunOnlyIfNetworkAvailable:$false

$Principal  = New-ScheduledTaskPrincipal `
    -UserId    "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel  Limited

# ── register (replace if exists) ─────────────────────────────────────────────
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Replacing existing task: $TaskName"
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName   $TaskName `
    -Description $TaskDesc `
    -Action     $Action `
    -Trigger    $Trigger `
    -Settings   $Settings `
    -Principal  $Principal | Out-Null

Write-Host ""
Write-Host "Task registered successfully." -ForegroundColor Green
Write-Host "  Name     : $TaskName"
Write-Host "  Python   : $PythonExe"
Write-Host "  Script   : $ScriptPath"
Write-Host "  Schedule : every 23 hours, first run at $StartTime"
Write-Host "  Logs     : $LogDir\auto_rescreen_YYYYMMDD.log"
Write-Host ""
Write-Host "To run immediately:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "To view last run status:"
Write-Host "  Get-ScheduledTaskInfo -TaskName '$TaskName'"

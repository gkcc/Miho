param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$TaskName = "MiHoYoEndgameDailyUpdate",
    [string]$At = "09:30"
)

$ErrorActionPreference = "Stop"
$scriptPath = Join-Path $Root "scripts\update_endgame_data.ps1"
if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Update script not found: $scriptPath"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Root `"$Root`""
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Refresh HSR/ZZZ endgame exports and rebuild ZZZ coverage/pull-value reports." `
    -Force | Out-Null

Write-Host "Registered task '$TaskName' at $At."

param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$HsrOut = "out",
    [string]$ZzzOut = "out_zzz",
    [string]$ZzzBox = ".miho\zzz_box_state.json",
    [string]$ZzzPlan = "configs\zzz_banner_plan.json",
    [string]$ZzzPlanStatus = "next",
    [string]$ZzzPullPlanStatus = "current,next",
    [int]$Days = 183,
    [switch]$SkipHsr,
    [switch]$SkipZzz
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $Root

$toDate = (Get-Date).ToString("yyyy-MM-dd")
$fromDate = (Get-Date).AddDays(-1 * $Days).ToString("yyyy-MM-dd")

function Invoke-Step {
    param(
        [string]$Name,
        [string[]]$Command
    )
    Write-Host "==> $Name"
    & $Command[0] @($Command[1..($Command.Length - 1)])
}

if (-not $SkipHsr) {
    Invoke-Step "Refresh HSR endgame export" @(
        "python", "-m", "hsr_endgame_exporter", "export",
        "--from-date", $fromDate,
        "--to-date", $toDate,
        "--out", $HsrOut
    )
}

if (-not $SkipZzz) {
    Invoke-Step "Refresh ZZZ endgame export" @(
        "python", "-m", "zzz_endgame_exporter", "export",
        "--from-date", $fromDate,
        "--to-date", $toDate,
        "--out", $ZzzOut
    )
    Invoke-Step "Build ZZZ current/target coverage" @(
        "python", "-m", "zzz_endgame_exporter", "coverage",
        "--box", $ZzzBox,
        "--out", $ZzzOut,
        "--plan", $ZzzPlan,
        "--plan-status", $ZzzPullPlanStatus
    )
    Invoke-Step "Build ZZZ pull value report" @(
        "python", "-m", "zzz_endgame_exporter", "pull-value",
        "--box", $ZzzBox,
        "--out", $ZzzOut,
        "--plan", $ZzzPlan,
        "--plan-status", $ZzzPullPlanStatus
    )
    Invoke-Step "Build ZZZ GPT reviewer packet" @(
        "python", "-m", "zzz_endgame_exporter", "review-packet",
        "--box", $ZzzBox,
        "--out", $ZzzOut,
        "--plan", $ZzzPlan,
        "--plan-status", $ZzzPullPlanStatus
    )
}

Write-Host "Update complete: $fromDate -> $toDate"

param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$Config = "configs\update_v1.json",
    [switch]$SkipHsr,
    [switch]$SkipZzz,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "native_command.ps1")

function Resolve-MihoCli {
    param([string]$Workspace)

    $candidates = @()
    if ($env:MIHO_CLI_PATH) {
        $candidates += $env:MIHO_CLI_PATH
    }
    $candidates += @(
        (Join-Path $Workspace "miho.exe"),
        (Join-Path $Workspace "target\release\miho.exe")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Get-Item -LiteralPath $candidate).FullName
        }
    }

    $command = Get-Command "miho.exe" -CommandType Application -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    throw "Native miho CLI not found. Install the release CLI or set MIHO_CLI_PATH."
}

$workspace = (Get-Item -LiteralPath $Root -ErrorAction Stop).FullName
$cli = Resolve-MihoCli -Workspace $workspace
$arguments = @("update", "run", "--workspace", $workspace, "--config", $Config)
if ($SkipHsr) {
    $arguments += "--skip-hsr"
}
if ($SkipZzz) {
    $arguments += "--skip-zzz"
}
if ($Force) {
    $arguments += "--force"
}

try {
    Invoke-NativeCommand -FilePath $cli -ArgumentList $arguments -FailureMessage "Native endgame update failed"
    $healthArguments = @("update", "health", "--workspace", $workspace, "--config", $Config)
    if ($SkipHsr) {
        $healthArguments += "--skip-hsr"
    }
    if ($SkipZzz) {
        $healthArguments += "--skip-zzz"
    }
    Invoke-NativeCommand -FilePath $cli -ArgumentList $healthArguments -FailureMessage "Native update health check failed"
    Write-Host "Native update and health verification complete."
}
catch {
    if ($_.Exception.Data.Contains("NativeExitCode")) {
        exit [int]$_.Exception.Data["NativeExitCode"]
    }
    throw
}

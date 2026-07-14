[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("installed", "portable", "manual")]
    [string]$ExpectedOwnerKind,

    [Parameter(Mandatory = $true)]
    [string]$ExpectedOwnerInstanceId,

    [int]$QuiesceTimeoutSeconds = 30,
    [string]$AutomationRoot
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "task_scheduler_v1.ps1")

$parameters = @{
    ExpectedOwnerKind = $ExpectedOwnerKind
    ExpectedOwnerInstanceId = $ExpectedOwnerInstanceId
    QuiesceTimeoutSeconds = $QuiesceTimeoutSeconds
}
if (-not [string]::IsNullOrWhiteSpace($AutomationRoot)) { $parameters.AutomationRoot = $AutomationRoot }

UninstallAndRelease-MihoDailyUpdateTaskV1 @parameters | ConvertTo-Json -Depth 8

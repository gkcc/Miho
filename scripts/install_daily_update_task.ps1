[CmdletBinding()]
param(
    [string]$SourceCli,

    [ValidateSet("Claim", "ReleaseClaim", "Install", "Prepare", "Commit", "Rollback")]
    [string]$Mode = "Install",

    [Parameter(Mandatory = $true)]
    [ValidateSet("installed", "portable", "manual")]
    [string]$ExpectedOwnerKind,

    [Parameter(Mandatory = $true)]
    [string]$ExpectedOwnerInstanceId,

    [string]$TransactionToken,

    [string]$ResultPath,
    [string]$CallerNonce,

    [string]$Workspace,

    [string]$DefaultWorkspace,
    [string]$DesktopSettingsPath,
    [string]$Config,
    [string]$At = "09:30",
    [int]$CandidateTimeoutSeconds = 7200,
    [int]$ProcessTimeoutSeconds = 7200,
    [int]$PrepareValiditySeconds = 1800,
    [int64]$CoordinatorPid = 0,
    [string]$AutomationRoot,
    [string]$ExpectedLegacyXmlSha256,
    [string]$ExpectedLegacySddlSha256
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "task_scheduler_v1.ps1")

$parameters = @{
    ExpectedOwnerKind = $ExpectedOwnerKind
    ExpectedOwnerInstanceId = $ExpectedOwnerInstanceId
    ProcessTimeoutSeconds = $ProcessTimeoutSeconds
}
if (-not [string]::IsNullOrWhiteSpace($AutomationRoot)) { $parameters.AutomationRoot = $AutomationRoot }
if ($Mode -eq "Claim") {
    $claimParameters = @{
        ExpectedOwnerKind = $ExpectedOwnerKind
        ExpectedOwnerInstanceId = $ExpectedOwnerInstanceId
    }
    if (-not [string]::IsNullOrWhiteSpace($AutomationRoot)) { $claimParameters.AutomationRoot = $AutomationRoot }
    $result = Claim-MihoAutomationOwnerV1 @claimParameters
    $result | ConvertTo-Json -Depth 8
    return
}
if ($Mode -eq "ReleaseClaim") {
    $releaseParameters = @{
        ExpectedOwnerKind = $ExpectedOwnerKind
        ExpectedOwnerInstanceId = $ExpectedOwnerInstanceId
    }
    if (-not [string]::IsNullOrWhiteSpace($AutomationRoot)) { $releaseParameters.AutomationRoot = $AutomationRoot }
    $result = Release-MihoAutomationOwnerClaimV1 @releaseParameters
    $result | ConvertTo-Json -Depth 8
    return
}
if ($Mode -eq "Commit" -or $Mode -eq "Rollback") {
    $handoffRequested = -not [string]::IsNullOrWhiteSpace($ResultPath) -or -not [string]::IsNullOrWhiteSpace($CallerNonce) -or $CoordinatorPid -gt 0
    if ($handoffRequested) {
        if ([string]::IsNullOrWhiteSpace($ResultPath) -or [string]::IsNullOrWhiteSpace($CallerNonce) -or $CoordinatorPid -le 0) {
            throw "ResultPath, CallerNonce, and CoordinatorPid are required together for $Mode handoff."
        }
        $expectedOwner = New-MihoExpectedOwnerV1 -OwnerKind $ExpectedOwnerKind -OwnerInstanceId $ExpectedOwnerInstanceId
        $handoff = Read-MihoPrepareHandoffReceiptV1 -Path $ResultPath -CallerNonce $CallerNonce -ExpectedOwner $expectedOwner -CoordinatorPid $CoordinatorPid
        $receiptToken = [string]$handoff.Object.transaction_token
        if (-not [string]::IsNullOrWhiteSpace($TransactionToken) -and $TransactionToken -cne $receiptToken) {
            throw "Explicit TransactionToken disagrees with the prepare handoff receipt."
        }
        $TransactionToken = $receiptToken
        $parameters.ResultPath = $ResultPath
        $parameters.CallerNonce = $CallerNonce
        $parameters.CoordinatorPid = $CoordinatorPid
    }
    elseif ([string]::IsNullOrWhiteSpace($TransactionToken)) {
        throw "TransactionToken or a strict prepare handoff receipt is required for $Mode."
    }
    $parameters.TransactionToken = $TransactionToken
    if ($Mode -eq "Commit") {
        if (-not [string]::IsNullOrWhiteSpace($ExpectedLegacyXmlSha256)) { $parameters.ExpectedLegacyXmlSha256 = $ExpectedLegacyXmlSha256 }
        if (-not [string]::IsNullOrWhiteSpace($ExpectedLegacySddlSha256)) { $parameters.ExpectedLegacySddlSha256 = $ExpectedLegacySddlSha256 }
        $result = Commit-MihoDailyUpdateTaskInstallV1 @parameters
    }
    else {
        $result = Rollback-MihoDailyUpdateTaskInstallV1 @parameters
    }
    $result | ConvertTo-Json -Depth 8
    return
}
if ([string]::IsNullOrWhiteSpace($SourceCli)) {
    throw "SourceCli is required for $Mode."
}
$parameters.SourceCli = $SourceCli
$parameters.At = $At
$parameters.CandidateTimeoutSeconds = $CandidateTimeoutSeconds
$parameters.PrepareValiditySeconds = $PrepareValiditySeconds
$parameters.CoordinatorPid = $CoordinatorPid
$workspaceOverride = Select-MihoInstallWorkspaceOverrideV1 `
    -ExplicitWorkspace $Workspace `
    -EnvironmentWorkspace $env:MIHO_DATA_ROOT
if (-not [string]::IsNullOrWhiteSpace($workspaceOverride)) {
    $parameters.Workspace = $workspaceOverride
}
if (-not [string]::IsNullOrWhiteSpace($DefaultWorkspace)) {
    $parameters.DefaultWorkspace = $DefaultWorkspace
}
if (-not [string]::IsNullOrWhiteSpace($DesktopSettingsPath)) {
    $parameters.DesktopSettingsPath = $DesktopSettingsPath
}
if (-not [string]::IsNullOrWhiteSpace($Config)) {
    $parameters.Config = $Config
}
if ($Mode -eq "Prepare") {
    $handoffRequested = -not [string]::IsNullOrWhiteSpace($ResultPath) -or -not [string]::IsNullOrWhiteSpace($CallerNonce) -or $CoordinatorPid -gt 0
    if ($handoffRequested) {
        if ([string]::IsNullOrWhiteSpace($ResultPath) -or [string]::IsNullOrWhiteSpace($CallerNonce) -or $CoordinatorPid -le 0) {
            throw "ResultPath, CallerNonce, and CoordinatorPid are required together for Prepare handoff."
        }
        $parameters.ResultPath = $ResultPath
        $parameters.CallerNonce = $CallerNonce
    }
    $result = Prepare-MihoDailyUpdateTaskInstallV1 @parameters
}
else {
    if (-not [string]::IsNullOrWhiteSpace($ExpectedLegacyXmlSha256)) { $parameters.ExpectedLegacyXmlSha256 = $ExpectedLegacyXmlSha256 }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedLegacySddlSha256)) { $parameters.ExpectedLegacySddlSha256 = $ExpectedLegacySddlSha256 }
    $result = Install-MihoDailyUpdateTaskV1 @parameters
}
$result | ConvertTo-Json -Depth 8

[CmdletBinding()]
param(
    [ValidateSet("Claim", "Install", "Prepare", "Commit", "Rollback", "Uninstall")]
    [string]$Mode = "Install",

    [string]$TransactionToken,
    [string]$ResultPath,
    [string]$CallerNonce,
    [int64]$CoordinatorPid = 0,
    [string]$Config,
    [string]$At = "09:30",
    [int]$CandidateTimeoutSeconds = 7200,
    [int]$ProcessTimeoutSeconds = 7200,
    [int]$PrepareValiditySeconds = 1800,
    [int]$QuiesceTimeoutSeconds = 30,
    [string]$AutomationRoot,
    [string]$ExpectedLegacyXmlSha256,
    [string]$ExpectedLegacySddlSha256
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "task_scheduler_v1.ps1")

$portableRoot = Resolve-MihoExistingDirectoryV1 `
    -Path (Split-Path -Parent $PSScriptRoot) `
    -Label "Portable release root"
$markerPath = Resolve-MihoExistingFileV1 `
    -Path (Join-Path $portableRoot "miho-portable-v1.json") `
    -Label "Portable release marker"
$markerRecord = Read-MihoJsonFileV1 `
    -Path $markerPath `
    -MaximumBytes 4096 `
    -ExpectedKeys @("schema_version", "workspace")
if (-not ($markerRecord.Object.schema_version -is [string]) -or
    -not ($markerRecord.Object.workspace -is [string]) -or
    [string]$markerRecord.Object.schema_version -cne "miho-portable-v1" -or
    [string]$markerRecord.Object.workspace -cne "data") {
    throw "Portable release marker is invalid."
}

$workspace = Resolve-MihoExistingDirectoryV1 `
    -Path (Join-Path $portableRoot "data") `
    -Label "Portable workspace"
$identityPath = Resolve-MihoExistingFileV1 `
    -Path (Join-Path $workspace ".miho\portable-identity-v1.json") `
    -Label "Portable automation identity"
$identityRecord = Read-MihoJsonFileV1 `
    -Path $identityPath `
    -MaximumBytes 4096 `
    -ExpectedKeys @("schema_version", "owner_kind", "owner_instance_id")
$identity = $identityRecord.Object
if (-not ($identity.schema_version -is [string]) -or
    -not ($identity.owner_kind -is [string]) -or
    -not ($identity.owner_instance_id -is [string]) -or
    [string]$identity.schema_version -cne "miho-portable-identity-v1" -or
    [string]$identity.owner_kind -cne "portable" -or
    -not (Test-MihoCanonicalUuidV1 -Value ([string]$identity.owner_instance_id))) {
    throw "Portable automation identity is invalid. Launch the portable desktop once to create it safely."
}

$ownerInstanceId = [string]$identity.owner_instance_id
$common = @{
    ExpectedOwnerKind = "portable"
    ExpectedOwnerInstanceId = $ownerInstanceId
}
if (-not [string]::IsNullOrWhiteSpace($AutomationRoot)) {
    $common.AutomationRoot = $AutomationRoot
}

if ($Mode -eq "Claim") {
    $result = Claim-MihoAutomationOwnerV1 @common
    $result | ConvertTo-Json -Depth 8
    return
}

if ($Mode -eq "Uninstall") {
    $uninstallParameters = @{} + $common
    $uninstallParameters.QuiesceTimeoutSeconds = $QuiesceTimeoutSeconds
    $uninstalled = Uninstall-MihoDailyUpdateTaskV1 @uninstallParameters
    $released = Release-MihoAutomationOwnerClaimV1 @common
    [pscustomobject][ordered]@{
        schema = "miho-portable-automation-uninstall-result-v1"
        owner_instance_id = $ownerInstanceId
        automation = $uninstalled
        claim = $released
    } | ConvertTo-Json -Depth 8
    return
}

if ($Mode -in @("Commit", "Rollback")) {
    if ([string]::IsNullOrWhiteSpace($ResultPath) -or
        [string]::IsNullOrWhiteSpace($CallerNonce) -or
        $CoordinatorPid -le 0) {
        throw "$Mode requires ResultPath, CallerNonce, and the original positive CoordinatorPid."
    }
    $terminal = @{} + $common
    $terminal.ResultPath = $ResultPath
    $terminal.CallerNonce = $CallerNonce
    $terminal.CoordinatorPid = $CoordinatorPid
    $terminal.ProcessTimeoutSeconds = $ProcessTimeoutSeconds
    if (-not [string]::IsNullOrWhiteSpace($TransactionToken)) {
        $terminal.TransactionToken = $TransactionToken
    }
    if ($Mode -eq "Commit") {
        if (-not [string]::IsNullOrWhiteSpace($ExpectedLegacyXmlSha256)) {
            $terminal.ExpectedLegacyXmlSha256 = $ExpectedLegacyXmlSha256
        }
        if (-not [string]::IsNullOrWhiteSpace($ExpectedLegacySddlSha256)) {
            $terminal.ExpectedLegacySddlSha256 = $ExpectedLegacySddlSha256
        }
        $result = Commit-MihoDailyUpdateTaskInstallV1 @terminal
    }
    else {
        $result = Rollback-MihoDailyUpdateTaskInstallV1 @terminal
    }
    $result | ConvertTo-Json -Depth 8
    return
}

$sourceCli = Resolve-MihoExistingFileV1 `
    -Path (Join-Path $portableRoot "miho.exe") `
    -Label "Portable native CLI"
$null = Claim-MihoAutomationOwnerV1 @common
$install = @{} + $common
$install.SourceCli = $sourceCli
$install.Workspace = $workspace
$install.At = $At
$install.CandidateTimeoutSeconds = $CandidateTimeoutSeconds
$install.ProcessTimeoutSeconds = $ProcessTimeoutSeconds
$install.PrepareValiditySeconds = $PrepareValiditySeconds
if (-not [string]::IsNullOrWhiteSpace($Config)) { $install.Config = $Config }
if (-not [string]::IsNullOrWhiteSpace($ExpectedLegacyXmlSha256)) {
    $install.ExpectedLegacyXmlSha256 = $ExpectedLegacyXmlSha256
}
if (-not [string]::IsNullOrWhiteSpace($ExpectedLegacySddlSha256)) {
    $install.ExpectedLegacySddlSha256 = $ExpectedLegacySddlSha256
}

if ($Mode -eq "Prepare") {
    if ([string]::IsNullOrWhiteSpace($ResultPath) -or
        [string]::IsNullOrWhiteSpace($CallerNonce) -or
        $CoordinatorPid -le 0) {
        throw "Prepare requires ResultPath, CallerNonce, and a positive CoordinatorPid."
    }
    $install.ResultPath = $ResultPath
    $install.CallerNonce = $CallerNonce
    $install.CoordinatorPid = $CoordinatorPid
    $result = Prepare-MihoDailyUpdateTaskInstallV1 @install
}
else {
    $result = Install-MihoDailyUpdateTaskV1 @install
}
$result | ConvertTo-Json -Depth 8

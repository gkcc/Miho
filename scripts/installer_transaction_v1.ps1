[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Begin", "Claim", "ApplyStatic", "Prepare", "VerifyDynamic", "Commit", "Rollback", "Recover", "Finalize", "Inspect", "VerifyUninstallStatic", "RemoveUninstallStatic", "FinalizeUninstallStatic")]
    [string]$Mode,

    [string]$TransactionRoot,
    [string]$FailureReceiptPath,

    [string]$InstallRoot,
    [string]$StagingRoot,
    [int64]$CoordinatorPid = 0,
    [string]$ProductName = "Miho Endgame",
    [string]$Manufacturer = "Miho Endgame",
    [string]$ProductVersion = "0.0.0",
    [string]$MainBinaryName = "miho-desktop",
    [string]$StartMenuFolder = "Miho Endgame",
    [switch]$CreateDesktopShortcut,
    [switch]$NoShortcuts,

    [string]$SourceCli,
    [string]$Workspace,
    [string]$DefaultWorkspace,
    [string]$DesktopSettingsPath,
    [string]$Config,
    [string]$At = "09:30",
    [int]$CandidateTimeoutSeconds = 7200,
    [int]$ProcessTimeoutSeconds = 7200,
    [int]$PrepareValiditySeconds = 1800,
    [string]$AutomationRoot,
    [string]$ExpectedLegacyXmlSha256,
    [string]$ExpectedLegacySddlSha256,
    [string]$ExpectedOwnerInstanceId,
    [string]$TestOwnerRegistrySubKey
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$schedulerPath = Join-Path $PSScriptRoot "task_scheduler_v1.ps1"
if (-not (Test-Path -LiteralPath $schedulerPath -PathType Leaf)) {
    throw "The installer transaction helper cannot locate its scheduler contract."
}
. $schedulerPath

$script:MihoInstallerTransactionSchemaV1 = "miho-installer-transaction-v1"
$script:MihoStaticOwnershipSchemaV1 = "miho-static-ownership-v1"
$script:MihoStaticOwnershipFileV1 = "miho-static-ownership-v1.json"
$script:MihoInstallerJournalFileV1 = "installer-transaction-v1.json"
$script:MihoInstallerHandoffFileV1 = "automation-handoff-v1.json"
$script:MihoInstallerUninstallStaticSchemaV1 = "miho-installer-uninstall-static-transaction-v1"
$script:MihoInstallerUninstallStaticFileV1 = "uninstall-static-v1.json"
$script:MihoInstalledOwnerRegistrySubKeyV1 = "Software\com.miho.endgame"
$script:MihoInstalledOwnerRegistryValueV1 = "AutomationOwnerInstanceIdV1"
$script:MihoInstallerMaximumJournalBytesV1 = 16MB
$script:MihoInstallerMaximumManifestBytesV1 = 4MB

if ([string]::IsNullOrWhiteSpace($TransactionRoot)) { $TransactionRoot = $env:MIHO_INSTALLER_TRANSACTION_ROOT_V1 }
if ([string]::IsNullOrWhiteSpace($FailureReceiptPath)) { $FailureReceiptPath = $env:MIHO_INSTALLER_FAILURE_RECEIPT_V1 }
if ([string]::IsNullOrWhiteSpace($InstallRoot)) { $InstallRoot = $env:MIHO_INSTALLER_INSTALL_ROOT_V1 }
if ([string]::IsNullOrWhiteSpace($StagingRoot)) { $StagingRoot = $env:MIHO_INSTALLER_STAGING_ROOT_V1 }
if ($CoordinatorPid -le 0 -and $env:MIHO_INSTALLER_COORDINATOR_PID_V1 -match '^[1-9][0-9]{0,18}$') {
    $CoordinatorPid = [int64]::Parse($env:MIHO_INSTALLER_COORDINATOR_PID_V1, [System.Globalization.CultureInfo]::InvariantCulture)
}
if (-not [string]::IsNullOrWhiteSpace($env:MIHO_INSTALLER_PRODUCT_NAME_V1)) { $ProductName = $env:MIHO_INSTALLER_PRODUCT_NAME_V1 }
if (-not [string]::IsNullOrWhiteSpace($env:MIHO_INSTALLER_MANUFACTURER_V1)) { $Manufacturer = $env:MIHO_INSTALLER_MANUFACTURER_V1 }
if (-not [string]::IsNullOrWhiteSpace($env:MIHO_INSTALLER_PRODUCT_VERSION_V1)) { $ProductVersion = $env:MIHO_INSTALLER_PRODUCT_VERSION_V1 }
if (-not [string]::IsNullOrWhiteSpace($env:MIHO_INSTALLER_MAIN_BINARY_V1)) { $MainBinaryName = $env:MIHO_INSTALLER_MAIN_BINARY_V1 }
$startMenuRootMarker = $env:MIHO_INSTALLER_START_MENU_ROOT_V1
if ($null -ne $startMenuRootMarker -and $startMenuRootMarker -cnotin @("0", "1")) {
    throw "Installer start-menu root marker is invalid."
}
if ($startMenuRootMarker -ceq "1") {
    if (-not [string]::IsNullOrEmpty($env:MIHO_INSTALLER_START_MENU_V1)) {
        throw "Installer start-menu policy is ambiguous."
    }
    $StartMenuFolder = ""
}
elseif ($null -ne $env:MIHO_INSTALLER_START_MENU_V1) { $StartMenuFolder = $env:MIHO_INSTALLER_START_MENU_V1 }
if ($env:MIHO_INSTALLER_DESKTOP_SHORTCUT_V1 -ceq "1") { $CreateDesktopShortcut = $true }
if ($env:MIHO_INSTALLER_NO_SHORTCUTS_V1 -ceq "1") { $NoShortcuts = $true }
if ([string]::IsNullOrWhiteSpace($Workspace)) { $Workspace = $env:MIHO_INSTALLER_WORKSPACE_V1 }
if ([string]::IsNullOrWhiteSpace($DefaultWorkspace)) { $DefaultWorkspace = $env:MIHO_INSTALLER_DEFAULT_WORKSPACE_V1 }
if ([string]::IsNullOrWhiteSpace($DesktopSettingsPath)) { $DesktopSettingsPath = $env:MIHO_INSTALLER_DESKTOP_SETTINGS_V1 }
if ([string]::IsNullOrWhiteSpace($Config)) { $Config = $env:MIHO_INSTALLER_CONFIG_V1 }
if ([string]::IsNullOrWhiteSpace($AutomationRoot)) { $AutomationRoot = $env:MIHO_INSTALLER_AUTOMATION_ROOT_V1 }
if ([string]::IsNullOrWhiteSpace($ExpectedLegacyXmlSha256)) { $ExpectedLegacyXmlSha256 = $env:MIHO_INSTALLER_LEGACY_XML_SHA256_V1 }
if ([string]::IsNullOrWhiteSpace($ExpectedLegacySddlSha256)) { $ExpectedLegacySddlSha256 = $env:MIHO_INSTALLER_LEGACY_SDDL_SHA256_V1 }
if ([string]::IsNullOrWhiteSpace($ExpectedOwnerInstanceId)) { $ExpectedOwnerInstanceId = $env:MIHO_INSTALLER_EXPECTED_OWNER_V1 }
if ([string]::IsNullOrWhiteSpace($TransactionRoot)) { throw "Installer transaction root is required." }

if (-not [string]::IsNullOrWhiteSpace($TestOwnerRegistrySubKey)) {
    if ($env:MIHO_INSTALLER_TRANSACTION_TEST_V1 -cne "1" -or
        $TestOwnerRegistrySubKey -cnotmatch '^Software\\com\.miho\.endgame\\tests\\[0-9a-f]{32}$') {
        throw "Installer owner registry test override is unauthorized."
    }
    $script:MihoInstalledOwnerRegistrySubKeyV1 = $TestOwnerRegistrySubKey
}

function Test-MihoInstallerIntegerV1 {
    param($Value)
    return ($Value -is [byte] -or $Value -is [int16] -or $Value -is [int32] -or $Value -is [int64] -or
        $Value -is [uint16] -or $Value -is [uint32])
}

function Assert-MihoInstallerAbsolutePathV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label,
        [switch]$MustExist,
        [switch]$Directory
    )

    if (-not [System.IO.Path]::IsPathRooted($Path)) { throw "$Label must be absolute." }
    $full = Get-MihoNormalizedFullPathV1 -Path $Path
    Assert-MihoNoReparseChainV1 -Path $full
    if ($MustExist) {
        $item = Get-Item -LiteralPath $full -Force -ErrorAction Stop
        if ([bool]$item.PSIsContainer -ne [bool]$Directory) { throw "$Label has the wrong filesystem type." }
        return $item.FullName
    }
    return $full
}

function Test-MihoInstallerPathWithinV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Parent
    )
    $child = (Get-MihoNormalizedFullPathV1 -Path $Path).TrimEnd("\", "/")
    $root = (Get-MihoNormalizedFullPathV1 -Path $Parent).TrimEnd("\", "/")
    return $child.StartsWith($root + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)
}

function Assert-MihoInstallerRelativePathV1 {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path) -or $Path.Contains("\") -or $Path.StartsWith("/") -or
        $Path.EndsWith("/") -or $Path.Contains(":") -or $Path.IndexOf([char]0) -ge 0) {
        throw "Static ownership contains an unsafe install path."
    }
    foreach ($component in $Path.Split('/')) {
        if ([string]::IsNullOrEmpty($component) -or $component -in @(".", "..") -or
            $component.TrimEnd(' ', '.') -cne $component -or
            $component -cnotmatch '^[A-Za-z0-9._-]+$') {
            throw "Static ownership contains an unsafe install path component."
        }
        $device = ($component.Split('.')[0]).ToLowerInvariant()
        if ($device -in @("con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9", "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9")) {
            throw "Static ownership contains a reserved Windows path component."
        }
    }
}

function Join-MihoInstallerOwnedPathV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Relative
    )
    Assert-MihoInstallerRelativePathV1 -Path $Relative
    $candidate = Get-MihoNormalizedFullPathV1 -Path (Join-Path $Root ($Relative.Replace('/', '\')))
    if (-not (Test-MihoInstallerPathWithinV1 -Path $candidate -Parent $Root)) {
        throw "Static ownership path escapes the install root."
    }
    return $candidate
}

function Get-MihoInstallerSafeFilesV1 {
    param([Parameter(Mandatory = $true)][string]$Root)
    $directory = Assert-MihoInstallerAbsolutePathV1 -Path $Root -Label "Installer payload directory" -MustExist -Directory
    $files = New-Object System.Collections.ArrayList
    foreach ($entry in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
        if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Installer payload contains a reparse point."
        }
        if ($entry.PSIsContainer) {
            foreach ($file in @(Get-MihoInstallerSafeFilesV1 -Root $entry.FullName)) { $null = $files.Add($file) }
        }
        else { $null = $files.Add($entry) }
    }
    return @($files)
}

function Assert-MihoInstallerTreeNoReparseV1 {
    param([Parameter(Mandatory = $true)][string]$Root)
    $directory = Assert-MihoInstallerAbsolutePathV1 -Path $Root -Label "Installer transaction directory" -MustExist -Directory
    foreach ($entry in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
        if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Installer transaction tree contains a reparse point."
        }
        if ($entry.PSIsContainer) { Assert-MihoInstallerTreeNoReparseV1 -Root $entry.FullName }
    }
}

function Read-MihoStaticOwnershipManifestV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$PayloadRoot,
        [switch]$RequireExactPayloadTree
    )

    $record = Read-MihoJsonFileV1 -Path $Path -MaximumBytes $script:MihoInstallerMaximumManifestBytesV1 -ExpectedKeys @(
        "schema_version", "product_version", "target_triple", "files", "ownership"
    )
    $manifest = $record.Object
    Assert-MihoObjectExactPropertyNamesV1 -Object $manifest -ExpectedNames @(
        "schema_version", "product_version", "target_triple", "files", "ownership"
    ) -Label "Static ownership manifest"
    if ($manifest.schema_version -isnot [string] -or [string]$manifest.schema_version -cne $script:MihoStaticOwnershipSchemaV1 -or
        $manifest.product_version -isnot [string] -or [string]::IsNullOrWhiteSpace([string]$manifest.product_version) -or
        $manifest.target_triple -isnot [string] -or [string]::IsNullOrWhiteSpace([string]$manifest.target_triple) -or
        $null -eq $manifest.files -or $manifest.files -is [string] -or
        $manifest.ownership -isnot [pscustomobject]) {
        throw "Static ownership manifest identity or types are invalid."
    }
    Assert-MihoObjectExactPropertyNamesV1 -Object $manifest.ownership -ExpectedNames @(
        "manifest_install_path", "manifest_self_in_files", "files_are_complete", "retired_file_policy", "mutable_data_excluded"
    ) -Label "Static ownership policy"
    if ($manifest.ownership.manifest_install_path -isnot [string] -or
        [string]$manifest.ownership.manifest_install_path -cne $script:MihoStaticOwnershipFileV1 -or
        $manifest.ownership.manifest_self_in_files -isnot [bool] -or $manifest.ownership.manifest_self_in_files -ne $false -or
        $manifest.ownership.files_are_complete -isnot [bool] -or $manifest.ownership.files_are_complete -ne $true -or
        $manifest.ownership.retired_file_policy -isnot [string] -or
        [string]$manifest.ownership.retired_file_policy -cne "delete-only-if-old-size-and-sha256-match" -or
        $manifest.ownership.mutable_data_excluded -isnot [bool] -or $manifest.ownership.mutable_data_excluded -ne $true) {
        throw "Static ownership policy is invalid."
    }

    $files = @($manifest.files)
    $byPath = @{}
    $orderedPaths = New-Object 'System.Collections.Generic.List[string]'
    $previous = $null
    foreach ($file in $files) {
        Assert-MihoObjectExactPropertyNamesV1 -Object $file -ExpectedNames @("install_path", "size", "sha256") -Label "Static ownership file"
        if ($file.install_path -isnot [string] -or -not (Test-MihoInstallerIntegerV1 -Value $file.size) -or
            [int64]$file.size -lt 0 -or $file.sha256 -isnot [string] -or [string]$file.sha256 -cnotmatch '^[0-9a-f]{64}$') {
            throw "Static ownership file record is invalid."
        }
        $relative = [string]$file.install_path
        Assert-MihoInstallerRelativePathV1 -Path $relative
        if ($relative -ceq $script:MihoStaticOwnershipFileV1 -or $byPath.ContainsKey($relative)) {
            throw "Static ownership file set is duplicated or self-referential."
        }
        if ($null -ne $previous -and [string]::CompareOrdinal([string]$previous, $relative) -ge 0) {
            throw "Static ownership file records are not strictly sorted."
        }
        $previous = $relative
        $byPath[$relative] = $file
        $orderedPaths.Add($relative)
    }

    $root = Assert-MihoInstallerAbsolutePathV1 -Path $PayloadRoot -Label "Static payload root" -MustExist -Directory
    if ($RequireExactPayloadTree) {
        $actual = @{}
        $prefix = $root.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
        foreach ($entry in @(Get-MihoInstallerSafeFilesV1 -Root $root)) {
            $relative = $entry.FullName.Substring($prefix.Length).Replace("\", "/")
            Assert-MihoInstallerRelativePathV1 -Path $relative
            if ($actual.ContainsKey($relative)) { throw "Static payload contains duplicate Windows paths." }
            $actual[$relative] = $entry
        }
        if ($actual.Count -ne ($byPath.Count + 1) -or -not $actual.ContainsKey($script:MihoStaticOwnershipFileV1)) {
            throw "Static payload tree is not the exact ownership set plus its manifest."
        }
        foreach ($relative in $orderedPaths) {
            if (-not $actual.ContainsKey($relative)) { throw "Static payload is missing an owned file." }
            $entry = $actual[$relative]
            $expected = $byPath[$relative]
            if ([int64]$entry.Length -ne [int64]$expected.size -or
                (Get-MihoFileSha256V1 -Path $entry.FullName) -cne [string]$expected.sha256) {
                throw "Static payload bytes do not match their ownership record."
            }
        }
        $manifestEntry = $actual[$script:MihoStaticOwnershipFileV1]
        if ((Get-MihoFileSha256V1 -Path $manifestEntry.FullName) -cne (Get-MihoSha256BytesV1 -Bytes $record.Bytes)) {
            throw "Static ownership manifest changed during validation."
        }
    }
    return [pscustomobject][ordered]@{
        Record = $record
        Object = $manifest
        Files = $byPath
        OrderedPaths = @($orderedPaths)
        Root = $root
    }
}

function Write-MihoInstallerJournalV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)][string]$Root
    )
    $path = Join-Path $Root $script:MihoInstallerJournalFileV1
    $bytes = ConvertTo-MihoJsonBytesV1 -Object $Journal -Depth 20
    if ($bytes.Length -gt $script:MihoInstallerMaximumJournalBytesV1) { throw "Installer transaction journal is too large." }
    Write-MihoAtomicBytesV1 -Path $path -Bytes $bytes -Purpose "installer-transaction-journal"
}

function Read-MihoInstallerJournalV1 {
    param([Parameter(Mandatory = $true)][string]$Root)
    $path = Join-Path $Root $script:MihoInstallerJournalFileV1
    $record = Read-MihoJsonFileV1 -Path $path -MaximumBytes $script:MihoInstallerMaximumJournalBytesV1
    $currentNames = @(
        "schema_version", "transaction_id", "phase", "owner_kind", "owner_instance_id",
        "owner_registry_was_present", "claim_created_new_owner", "install_root", "install_root_was_present", "staging_root",
        "caller_nonce", "coordinator_pid", "handoff_path", "new_manifest_sha256",
        "old_manifest_present", "static_files", "dynamic_files", "registry_trees", "failure"
    )
    $journal = $record.Object
    if (Test-MihoObjectPropertyV1 -Object $journal -Name "install_root_was_present") {
        Assert-MihoObjectExactPropertyNamesV1 -Object $journal -ExpectedNames $currentNames -Label "Installer transaction journal"
    }
    else {
        # Pre-field v1 journals cannot prove that the installer created the
        # install root. Migrate them conservatively so recovery never removes it.
        $legacyNames = @(
            "schema_version", "transaction_id", "phase", "owner_kind", "owner_instance_id",
            "owner_registry_was_present", "claim_created_new_owner", "install_root", "staging_root",
            "caller_nonce", "coordinator_pid", "handoff_path", "new_manifest_sha256",
            "old_manifest_present", "static_files", "dynamic_files", "registry_trees", "failure"
        )
        Assert-MihoObjectExactPropertyNamesV1 -Object $journal -ExpectedNames $legacyNames -Label "Installer transaction journal"
        $journal | Add-Member -MemberType NoteProperty -Name "install_root_was_present" -Value $true
    }
    Assert-MihoObjectExactPropertyNamesV1 -Object $journal -ExpectedNames @(
        "schema_version", "transaction_id", "phase", "owner_kind", "owner_instance_id",
        "owner_registry_was_present", "claim_created_new_owner", "install_root", "install_root_was_present", "staging_root",
        "caller_nonce", "coordinator_pid", "handoff_path", "new_manifest_sha256",
        "old_manifest_present", "static_files", "dynamic_files", "registry_trees", "failure"
    ) -Label "Installer transaction journal"
    if ($journal.schema_version -isnot [string] -or [string]$journal.schema_version -cne $script:MihoInstallerTransactionSchemaV1 -or
        $journal.transaction_id -isnot [string] -or [string]$journal.transaction_id -cnotmatch '^[0-9a-f]{32}$' -or
        $journal.phase -isnot [string] -or [string]$journal.phase -cnotin @(
            "before-image-ready", "owner-registered", "claimed", "applying-static", "static-applied",
            "prepared", "dynamic-verified", "committed", "rolling-back", "rolled-back"
        ) -or $journal.owner_kind -isnot [string] -or [string]$journal.owner_kind -cne "installed" -or
        $journal.owner_instance_id -isnot [string] -or -not (Test-MihoCanonicalUuidV1 -Value ([string]$journal.owner_instance_id)) -or
        $journal.owner_registry_was_present -isnot [bool] -or $journal.claim_created_new_owner -isnot [bool] -or
        $journal.install_root_was_present -isnot [bool] -or
        $journal.install_root -isnot [string] -or $journal.staging_root -isnot [string] -or
        $journal.caller_nonce -isnot [string] -or [string]$journal.caller_nonce -cnotmatch '^[0-9a-f]{32}$' -or
        -not (Test-MihoInstallerIntegerV1 -Value $journal.coordinator_pid) -or [int64]$journal.coordinator_pid -le 0 -or
        $journal.handoff_path -isnot [string] -or $journal.new_manifest_sha256 -isnot [string] -or
        [string]$journal.new_manifest_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        $journal.old_manifest_present -isnot [bool] -or $journal.failure -isnot [string]) {
        throw "Installer transaction journal identity or types are invalid."
    }
    $root = Assert-MihoInstallerAbsolutePathV1 -Path $Root -Label "Installer transaction root" -MustExist -Directory
    $install = Assert-MihoInstallerAbsolutePathV1 -Path ([string]$journal.install_root) -Label "Journal install root"
    $staging = Assert-MihoInstallerAbsolutePathV1 -Path ([string]$journal.staging_root) -Label "Journal staging root"
    $handoff = Assert-MihoInstallerAbsolutePathV1 -Path ([string]$journal.handoff_path) -Label "Journal handoff path"
    if (-not (Test-MihoInstallerPathWithinV1 -Path $handoff -Parent $root)) { throw "Installer handoff escapes its transaction root." }
    return [pscustomobject][ordered]@{ Record = $record; Object = $journal; Root = $root; InstallRoot = $install; StagingRoot = $staging; HandoffPath = $handoff }
}

function Get-MihoInstalledOwnerRegistryV1 {
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($script:MihoInstalledOwnerRegistrySubKeyV1, $false)
    if ($null -eq $key) { return $null }
    try {
        if (-not ($key.GetValueNames() -contains $script:MihoInstalledOwnerRegistryValueV1)) { return $null }
        if ($key.GetValueKind($script:MihoInstalledOwnerRegistryValueV1) -ne [Microsoft.Win32.RegistryValueKind]::String) {
            throw "Installed automation owner registry value has the wrong type."
        }
        $value = $key.GetValue($script:MihoInstalledOwnerRegistryValueV1, $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        if ($value -isnot [string] -or -not (Test-MihoCanonicalUuidV1 -Value ([string]$value))) {
            throw "Installed automation owner registry value is invalid."
        }
        return [string]$value
    }
    finally { $key.Dispose() }
}

function Set-MihoInstalledOwnerRegistryV1 {
    param([Parameter(Mandatory = $true)][string]$OwnerInstanceId)
    if (-not (Test-MihoCanonicalUuidV1 -Value $OwnerInstanceId)) { throw "Installed automation owner identity is invalid." }
    $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($script:MihoInstalledOwnerRegistrySubKeyV1, $true)
    if ($null -eq $key) { throw "Installed automation owner registry key is unavailable." }
    try {
        $key.SetValue($script:MihoInstalledOwnerRegistryValueV1, $OwnerInstanceId, [Microsoft.Win32.RegistryValueKind]::String)
        $key.Flush()
    }
    finally { $key.Dispose() }
    $actual = Get-MihoInstalledOwnerRegistryV1
    if ($actual -cne $OwnerInstanceId) { throw "Installed automation owner registry write was not durable." }
}

function Remove-MihoInstalledOwnerRegistryV1 {
    param([Parameter(Mandatory = $true)][string]$ExpectedOwnerInstanceId)
    $actual = Get-MihoInstalledOwnerRegistryV1
    if ($null -eq $actual) { return }
    if ($actual -cne $ExpectedOwnerInstanceId) { throw "Installed automation owner registry value drifted." }
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($script:MihoInstalledOwnerRegistrySubKeyV1, $true)
    if ($null -eq $key) { throw "Installed automation owner registry key is unavailable." }
    try { $key.DeleteValue($script:MihoInstalledOwnerRegistryValueV1, $true); $key.Flush() }
    finally { $key.Dispose() }
    if ($null -ne (Get-MihoInstalledOwnerRegistryV1)) { throw "Installed automation owner registry value could not be removed." }
}

function Write-MihoInstallerBackupV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    Assert-MihoNoReparseChainV1 -Path $Source
    $sourceItem = Get-Item -LiteralPath $Source -Force -ErrorAction Stop
    if ($sourceItem.PSIsContainer) { throw "Installer before-image source is not a normal file." }
    $parent = Split-Path -Parent $Destination
    [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    Assert-MihoNoReparseChainV1 -Path $parent
    $input = New-Object System.IO.FileStream($Source, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
    try {
        $output = New-Object System.IO.FileStream($Destination, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None, 1048576, [System.IO.FileOptions]::WriteThrough)
        try { $input.CopyTo($output); $output.Flush($true) }
        finally { $output.Dispose() }
    }
    finally { $input.Dispose() }
    if ((Get-MihoFileSha256V1 -Path $Destination) -cne (Get-MihoFileSha256V1 -Path $Source) -or
        [int64](Get-Item -LiteralPath $Destination -Force).Length -ne [int64]$sourceItem.Length) {
        throw "Installer before-image backup verification failed."
    }
}

function Export-MihoInstallerRegistryKeyCoreV1 {
    param(
        [Parameter(Mandatory = $true)][Microsoft.Win32.RegistryKey]$Key,
        [Parameter(Mandatory = $true)][int]$Depth,
        [Parameter(Mandatory = $true)][ref]$EntryCount
    )
    if ($Depth -gt 32) { throw "Installer registry before-image is too deep." }
    $values = New-Object System.Collections.ArrayList
    foreach ($name in @($Key.GetValueNames() | Sort-Object)) {
        $EntryCount.Value++
        if ($EntryCount.Value -gt 4096) { throw "Installer registry before-image has too many entries." }
        $kind = $Key.GetValueKind($name)
        $value = $Key.GetValue($name, $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        $encoded = $null
        switch ($kind) {
            ([Microsoft.Win32.RegistryValueKind]::Binary) { $encoded = [System.Convert]::ToBase64String([byte[]]$value) }
            ([Microsoft.Win32.RegistryValueKind]::None) { $encoded = [System.Convert]::ToBase64String([byte[]]$value) }
            ([Microsoft.Win32.RegistryValueKind]::MultiString) { $encoded = @([string[]]$value) }
            ([Microsoft.Win32.RegistryValueKind]::DWord) { $encoded = ([int64]$value).ToString([System.Globalization.CultureInfo]::InvariantCulture) }
            ([Microsoft.Win32.RegistryValueKind]::QWord) { $encoded = ([int64]$value).ToString([System.Globalization.CultureInfo]::InvariantCulture) }
            default { $encoded = [string]$value }
        }
        $null = $values.Add([pscustomobject][ordered]@{
            name = [string]$name
            kind = $kind.ToString()
            data = $encoded
        })
    }
    $subkeys = New-Object System.Collections.ArrayList
    foreach ($name in @($Key.GetSubKeyNames() | Sort-Object)) {
        $EntryCount.Value++
        if ($EntryCount.Value -gt 4096) { throw "Installer registry before-image has too many entries." }
        $child = $Key.OpenSubKey($name, $false)
        if ($null -eq $child) { throw "Installer registry before-image changed during enumeration." }
        try {
            $tree = Export-MihoInstallerRegistryKeyCoreV1 -Key $child -Depth ($Depth + 1) -EntryCount $EntryCount
        }
        finally { $child.Dispose() }
        $null = $subkeys.Add([pscustomobject][ordered]@{ name = [string]$name; tree = $tree })
    }
    try {
        # A current-user installer can restore the DACL exactly, but setting
        # owner/group/SACL from an All-sections descriptor requires privileges
        # that a currentUser NSIS process deliberately does not hold.
        $sddl = $Key.GetAccessControl().GetSecurityDescriptorSddlForm([System.Security.AccessControl.AccessControlSections]::Access)
    }
    catch { throw "Installer registry before-image security descriptor is unavailable." }
    return [pscustomobject][ordered]@{ sddl = $sddl; values = @($values); subkeys = @($subkeys) }
}

function Export-MihoInstallerRegistryTreeV1 {
    param([Parameter(Mandatory = $true)][string]$SubKey)
    if ([string]::IsNullOrWhiteSpace($SubKey) -or $SubKey.StartsWith("\") -or $SubKey.EndsWith("\") -or
        $SubKey.Contains("..") -or $SubKey.IndexOf([char]0) -ge 0) {
        throw "Installer registry subkey is invalid."
    }
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($SubKey, $false)
    if ($null -eq $key) {
        return [pscustomobject][ordered]@{ subkey = $SubKey; present = $false; tree = $null }
    }
    try {
        $count = 0
        $tree = Export-MihoInstallerRegistryKeyCoreV1 -Key $key -Depth 0 -EntryCount ([ref]$count)
    }
    finally { $key.Dispose() }
    return [pscustomobject][ordered]@{ subkey = $SubKey; present = $true; tree = $tree }
}

function ConvertTo-MihoInstallerComparableDaclSddlV1 {
    param([Parameter(Mandatory = $true)][string]$Sddl)
    if ($Sddl -cnotmatch '^D:([A-Z]*)(.*)$') { throw "Installer registry DACL descriptor is invalid." }
    return "D:" + $matches[1].Replace("AI", "") + $matches[2]
}

function Import-MihoInstallerRegistryKeyCoreV1 {
    param(
        [Parameter(Mandatory = $true)][Microsoft.Win32.RegistryKey]$Key,
        [Parameter(Mandatory = $true)]$Tree,
        [Parameter(Mandatory = $true)][int]$Depth,
        [Parameter(Mandatory = $true)][string]$SubKey
    )
    if ($Depth -gt 32) { throw "Installer registry restore is too deep." }
    Assert-MihoObjectExactPropertyNamesV1 -Object $Tree -ExpectedNames @("sddl", "values", "subkeys") -Label "Installer registry tree"
    foreach ($record in @($Tree.values)) {
        Assert-MihoObjectExactPropertyNamesV1 -Object $record -ExpectedNames @("name", "kind", "data") -Label "Installer registry value"
        if ($record.name -isnot [string] -or $record.kind -isnot [string]) { throw "Installer registry value record is invalid." }
        try { $kind = [Microsoft.Win32.RegistryValueKind]([System.Enum]::Parse([Microsoft.Win32.RegistryValueKind], [string]$record.kind, $false)) }
        catch { throw "Installer registry value kind is invalid." }
        switch ($kind) {
            ([Microsoft.Win32.RegistryValueKind]::Binary) { $value = [System.Convert]::FromBase64String([string]$record.data) }
            ([Microsoft.Win32.RegistryValueKind]::None) { $value = [System.Convert]::FromBase64String([string]$record.data) }
            ([Microsoft.Win32.RegistryValueKind]::MultiString) { $value = [string[]]@($record.data) }
            ([Microsoft.Win32.RegistryValueKind]::DWord) { $value = [int32]::Parse([string]$record.data, [System.Globalization.CultureInfo]::InvariantCulture) }
            ([Microsoft.Win32.RegistryValueKind]::QWord) { $value = [int64]::Parse([string]$record.data, [System.Globalization.CultureInfo]::InvariantCulture) }
            default { $value = [string]$record.data }
        }
        $Key.SetValue([string]$record.name, $value, $kind)
    }
    foreach ($record in @($Tree.subkeys)) {
        Assert-MihoObjectExactPropertyNamesV1 -Object $record -ExpectedNames @("name", "tree") -Label "Installer registry subkey"
        if ($record.name -isnot [string] -or [string]::IsNullOrEmpty([string]$record.name) -or [string]$record.name -match '[\\/]' -or [string]$record.name -in @(".", "..")) {
            throw "Installer registry subkey record is invalid."
        }
        $child = $Key.CreateSubKey([string]$record.name, $true)
        if ($null -eq $child) { throw "Installer registry subkey could not be restored." }
        $childSubKey = $SubKey + "\" + [string]$record.name
        try { Import-MihoInstallerRegistryKeyCoreV1 -Key $child -Tree $record.tree -Depth ($Depth + 1) -SubKey $childSubKey }
        finally { $child.Dispose() }
    }
    if ($Tree.sddl -isnot [string] -or [string]::IsNullOrWhiteSpace([string]$Tree.sddl)) { throw "Installer registry security descriptor is invalid." }
    $Key.Flush()
    $security = New-Object System.Security.AccessControl.RegistrySecurity
    $accessSections = [System.Security.AccessControl.AccessControlSections]::Access
    $security.SetSecurityDescriptorSddlForm([string]$Tree.sddl, $accessSections)
    $rights = [System.Security.AccessControl.RegistryRights](
        [int][System.Security.AccessControl.RegistryRights]::ReadKey -bor
        [int][System.Security.AccessControl.RegistryRights]::WriteKey -bor
        [int][System.Security.AccessControl.RegistryRights]::ChangePermissions
    )
    $securityKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey(
        $SubKey,
        [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree,
        $rights
    )
    if ($null -eq $securityKey) { throw "Installer registry security handle is unavailable." }
    try {
        $securityKey.SetAccessControl($security)
        $securityKey.Flush()
        $expectedSddl = $security.GetSecurityDescriptorSddlForm($accessSections)
        $actualSddl = $securityKey.GetAccessControl().GetSecurityDescriptorSddlForm($accessSections)
        # Windows can add the DACL_AUTO_INHERITED (AI) control bit when a key
        # is recreated below the same parent even though every ACE, protection
        # flag and effective permission is identical. Ignore only that OS
        # bookkeeping bit; P/AR and every ACE remain exact comparison inputs.
        $expectedComparable = ConvertTo-MihoInstallerComparableDaclSddlV1 -Sddl $expectedSddl
        $actualComparable = ConvertTo-MihoInstallerComparableDaclSddlV1 -Sddl $actualSddl
        if ($actualComparable -cne $expectedComparable) {
            throw "Installer registry access control did not restore exactly: $SubKey"
        }
    }
    finally { $securityKey.Dispose() }
}

function Restore-MihoInstallerRegistryTreeV1 {
    param([Parameter(Mandatory = $true)]$Snapshot)
    Assert-MihoObjectExactPropertyNamesV1 -Object $Snapshot -ExpectedNames @("subkey", "present", "tree") -Label "Installer registry snapshot"
    if ($Snapshot.subkey -isnot [string] -or $Snapshot.present -isnot [bool]) { throw "Installer registry snapshot is invalid." }
    try { [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree([string]$Snapshot.subkey, $false) }
    catch [System.ArgumentException] { }
    if ($Snapshot.present) {
        if ($Snapshot.tree -isnot [pscustomobject]) { throw "Installer registry snapshot tree is invalid." }
        $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey([string]$Snapshot.subkey, $true)
        if ($null -eq $key) { throw "Installer registry root could not be restored." }
        try { Import-MihoInstallerRegistryKeyCoreV1 -Key $key -Tree $Snapshot.tree -Depth 0 -SubKey ([string]$Snapshot.subkey) }
        finally { $key.Dispose() }
    }
}

function Get-MihoInstallerDynamicFilePlanV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Install,
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Product,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$MenuFolder,
        [Parameter(Mandatory = $true)][bool]$StartMenuShortcut,
        [Parameter(Mandatory = $true)][bool]$DesktopShortcut
    )
    $programs = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::StartMenu)) "Programs"
    $desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
    if ([string]::IsNullOrWhiteSpace($programs) -or [string]::IsNullOrWhiteSpace($desktop)) {
        throw "Installer shell folders are unavailable."
    }
    $startMenuPath = if ([string]::IsNullOrEmpty($MenuFolder)) {
        Join-Path $programs ($Product + ".lnk")
    }
    else { Join-Path (Join-Path $programs $MenuFolder) ($Product + ".lnk") }
    $paths = @(
        [pscustomobject]@{ Label = "uninstaller"; Path = Join-Path $Install "uninstall.exe"; ExpectedAfter = $true },
        [pscustomobject]@{ Label = "start-menu-shortcut"; Path = $startMenuPath; ExpectedAfter = $StartMenuShortcut },
        [pscustomobject]@{ Label = "desktop-shortcut"; Path = Join-Path $desktop ($Product + ".lnk"); ExpectedAfter = $DesktopShortcut }
    )
    $records = New-Object System.Collections.ArrayList
    $index = 0
    foreach ($entry in $paths) {
        $path = Assert-MihoInstallerAbsolutePathV1 -Path ([string]$entry.Path) -Label ("Dynamic file " + [string]$entry.Label)
        $present = Test-Path -LiteralPath $path
        $size = [int64]0
        $hash = ""
        $backup = ""
        if ($present) {
            Assert-MihoNoReparseChainV1 -Path $path
            $item = Get-Item -LiteralPath $path -Force -ErrorAction Stop
            if ($item.PSIsContainer) { throw "Installer dynamic path is not a normal file." }
            $size = [int64]$item.Length
            $hash = Get-MihoFileSha256V1 -Path $path
            $backup = "backups/dynamic/{0:D3}.bin" -f $index
            Write-MihoInstallerBackupV1 -Source $path -Destination (Join-Path $Root ($backup.Replace('/', '\')))
        }
        $null = $records.Add([pscustomobject][ordered]@{
            label = [string]$entry.Label
            path = $path
            before_present = [bool]$present
            before_size = $size
            before_sha256 = $hash
            backup_relative = $backup
            expected_after_present = [bool]$entry.ExpectedAfter
            after_captured = $false
            after_size = [int64]0
            after_sha256 = ""
        })
        $index++
    }
    return @($records)
}

function Get-MihoInstallerStaticPlanV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Install,
        [Parameter(Mandatory = $true)][string]$Staging,
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)]$NewManifest
    )
    $oldManifestPath = Join-Path $Install $script:MihoStaticOwnershipFileV1
    $oldManifest = $null
    if (Test-Path -LiteralPath $oldManifestPath) {
        $oldManifest = Read-MihoStaticOwnershipManifestV1 -Path $oldManifestPath -PayloadRoot $Install
    }
    $union = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    foreach ($relative in @($NewManifest.OrderedPaths)) { $null = $union.Add([string]$relative) }
    if ($null -ne $oldManifest) {
        foreach ($relative in @($oldManifest.OrderedPaths)) { $null = $union.Add([string]$relative) }
    }
    $null = $union.Add($script:MihoStaticOwnershipFileV1)
    $paths = @($union) | Sort-Object
    $records = New-Object System.Collections.ArrayList
    $backupIndex = 0
    foreach ($relative in $paths) {
        $target = Join-MihoInstallerOwnedPathV1 -Root $Install -Relative $relative
        $beforePresent = Test-Path -LiteralPath $target
        $beforeSize = [int64]0
        $beforeHash = ""
        $backupRelative = ""
        if ($beforePresent) {
            Assert-MihoNoReparseChainV1 -Path $target
            $item = Get-Item -LiteralPath $target -Force -ErrorAction Stop
            if ($item.PSIsContainer) { throw "Installer-owned static target is not a normal file." }
            $beforeSize = [int64]$item.Length
            $beforeHash = Get-MihoFileSha256V1 -Path $target
            $oldRecord = if ($null -eq $oldManifest -or $relative -ceq $script:MihoStaticOwnershipFileV1) { $null } else { $oldManifest.Files[$relative] }
            if ($relative -cne $script:MihoStaticOwnershipFileV1 -and $null -eq $oldRecord) {
                throw "A new installer-owned path collides with an unmanaged existing file."
            }
            if ($null -ne $oldRecord -and ([int64]$oldRecord.size -ne $beforeSize -or [string]$oldRecord.sha256 -cne $beforeHash)) {
                throw "An old installer-owned static file drifted; retired or replaced bytes were preserved."
            }
            $backupRelative = "backups/files/{0:D6}.bin" -f $backupIndex
            $backupPath = Join-Path $Root ($backupRelative.Replace('/', '\'))
            Write-MihoInstallerBackupV1 -Source $target -Destination $backupPath
            $backupIndex++
        }
        elseif ($null -ne $oldManifest -and $relative -cne $script:MihoStaticOwnershipFileV1 -and $null -ne $oldManifest.Files[$relative]) {
            throw "An old installer-owned static file is missing."
        }

        $newRecord = if ($relative -ceq $script:MihoStaticOwnershipFileV1) {
            [pscustomobject]@{
                size = [int64]$NewManifest.Record.Bytes.Length
                sha256 = Get-MihoSha256BytesV1 -Bytes $NewManifest.Record.Bytes
            }
        }
        else { $NewManifest.Files[$relative] }
        $afterPresent = $null -ne $newRecord
        $null = $records.Add([pscustomobject][ordered]@{
            install_path = $relative
            before_present = [bool]$beforePresent
            before_size = $beforeSize
            before_sha256 = $beforeHash
            backup_relative = $backupRelative
            after_present = [bool]$afterPresent
            after_size = [int64]$(if ($afterPresent) { $newRecord.size } else { 0 })
            after_sha256 = [string]$(if ($afterPresent) { $newRecord.sha256 } else { "" })
        })
    }
    return [pscustomobject][ordered]@{
        OldManifestPresent = $null -ne $oldManifest
        Records = @($records)
    }
}

function New-MihoInstallerTransactionV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Install,
        [Parameter(Mandatory = $true)][string]$Staging,
        [Parameter(Mandatory = $true)][int64]$ParentPid
    )
    if ($ParentPid -le 0) { throw "Installer coordinator PID is required." }
    try { $process = Get-Process -Id $ParentPid -ErrorAction Stop }
    catch { throw "Installer coordinator process is unavailable." }
    if ($process.HasExited) { throw "Installer coordinator process is unavailable." }

    $installPath = Assert-MihoInstallerAbsolutePathV1 -Path $Install -Label "Install root"
    $installRootWasPresent = Test-Path -LiteralPath $installPath
    if ($installRootWasPresent) {
        $installPath = Assert-MihoInstallerAbsolutePathV1 -Path $installPath -Label "Install root" -MustExist -Directory
    }
    $stagingPath = Assert-MihoInstallerAbsolutePathV1 -Path $Staging -Label "Staging root" -MustExist -Directory
    $rootPath = Assert-MihoInstallerAbsolutePathV1 -Path $Root -Label "Installer transaction root"
    foreach ($pair in @(@($rootPath, $installPath), @($rootPath, $stagingPath), @($installPath, $stagingPath), @($stagingPath, $installPath))) {
        if ([string]::Equals($pair[0], $pair[1], [System.StringComparison]::OrdinalIgnoreCase) -or
            (Test-MihoInstallerPathWithinV1 -Path $pair[0] -Parent $pair[1])) {
            throw "Installer transaction, staging, and install roots must not overlap."
        }
    }
    if (Test-Path -LiteralPath $rootPath) { throw "An installer transaction already exists; recover it before beginning another." }
    $parent = Split-Path -Parent $rootPath
    $null = Assert-MihoInstallerAbsolutePathV1 -Path $parent -Label "Installer transaction parent" -MustExist -Directory
    [System.IO.Directory]::CreateDirectory($rootPath) | Out-Null
    $rootPath = Assert-MihoInstallerAbsolutePathV1 -Path $rootPath -Label "Installer transaction root" -MustExist -Directory

    $newManifestPath = Join-Path $stagingPath $script:MihoStaticOwnershipFileV1
    $newManifest = Read-MihoStaticOwnershipManifestV1 -Path $newManifestPath -PayloadRoot $stagingPath -RequireExactPayloadTree
    $plan = Get-MihoInstallerStaticPlanV1 -Install $installPath -Staging $stagingPath -Root $rootPath -NewManifest $newManifest
    foreach ($identity in @($ProductName, $Manufacturer, $StartMenuFolder)) {
        if ($null -eq $identity -or [string]$identity -match '[\\/\x00]') {
            throw "Installer product identity contains an unsafe registry or shell component."
        }
    }
    if ([string]::IsNullOrWhiteSpace($ProductName) -or [string]::IsNullOrWhiteSpace($Manufacturer)) {
        throw "Installer product identity is incomplete."
    }
    $dynamicFiles = Get-MihoInstallerDynamicFilePlanV1 `
        -Install $installPath `
        -Root $rootPath `
        -Product $ProductName `
        -MenuFolder $StartMenuFolder `
        -StartMenuShortcut (-not [bool]$NoShortcuts) `
        -DesktopShortcut ((-not [bool]$NoShortcuts) -and [bool]$CreateDesktopShortcut)
    $registryTrees = @(
        [pscustomobject][ordered]@{
            label = "install-location"
            before = Export-MihoInstallerRegistryTreeV1 -SubKey ("Software\{0}\{1}" -f $Manufacturer, $ProductName)
            after_sha256 = ""
        },
        [pscustomobject][ordered]@{
            label = "uninstall"
            before = Export-MihoInstallerRegistryTreeV1 -SubKey ("Software\Microsoft\Windows\CurrentVersion\Uninstall\{0}" -f $ProductName)
            after_sha256 = ""
        }
    )
    $existingOwner = Get-MihoInstalledOwnerRegistryV1
    $owner = if ($null -eq $existingOwner) { [guid]::NewGuid().ToString("D").ToLowerInvariant() } else { $existingOwner }
    $journal = [pscustomobject][ordered]@{
        schema_version = $script:MihoInstallerTransactionSchemaV1
        transaction_id = [guid]::NewGuid().ToString("N").ToLowerInvariant()
        phase = "before-image-ready"
        owner_kind = "installed"
        owner_instance_id = $owner
        owner_registry_was_present = ($null -ne $existingOwner)
        claim_created_new_owner = $false
        install_root = $installPath
        install_root_was_present = [bool]$installRootWasPresent
        staging_root = $stagingPath
        caller_nonce = [guid]::NewGuid().ToString("N").ToLowerInvariant()
        coordinator_pid = $ParentPid
        handoff_path = Join-Path $rootPath $script:MihoInstallerHandoffFileV1
        new_manifest_sha256 = Get-MihoSha256BytesV1 -Bytes $newManifest.Record.Bytes
        old_manifest_present = [bool]$plan.OldManifestPresent
        static_files = @($plan.Records)
        dynamic_files = @($dynamicFiles)
        registry_trees = @($registryTrees)
        failure = ""
    }
    Write-MihoInstallerJournalV1 -Journal $journal -Root $rootPath
    try {
        Set-MihoInstalledOwnerRegistryV1 -OwnerInstanceId $owner
        $journal.phase = "owner-registered"
        Write-MihoInstallerJournalV1 -Journal $journal -Root $rootPath
    }
    catch {
        $journal.failure = "owner-register-failed"
        try { Write-MihoInstallerJournalV1 -Journal $journal -Root $rootPath } catch { }
        throw
    }
    return [pscustomobject][ordered]@{
        schema = "miho-installer-begin-result-v1"
        owner_kind = "installed"
        owner_instance_id = $owner
        owner_registry_was_present = ($null -ne $existingOwner)
        transaction_id = $journal.transaction_id
        phase = $journal.phase
    }
}

function Assert-MihoInstallerStaticRecordV1 {
    param([Parameter(Mandatory = $true)]$Record)
    Assert-MihoObjectExactPropertyNamesV1 -Object $Record -ExpectedNames @(
        "install_path", "before_present", "before_size", "before_sha256", "backup_relative",
        "after_present", "after_size", "after_sha256"
    ) -Label "Installer static before-image"
    if ($Record.install_path -isnot [string] -or $Record.before_present -isnot [bool] -or
        -not (Test-MihoInstallerIntegerV1 -Value $Record.before_size) -or [int64]$Record.before_size -lt 0 -or
        $Record.before_sha256 -isnot [string] -or $Record.backup_relative -isnot [string] -or
        $Record.after_present -isnot [bool] -or -not (Test-MihoInstallerIntegerV1 -Value $Record.after_size) -or
        [int64]$Record.after_size -lt 0 -or $Record.after_sha256 -isnot [string]) {
        throw "Installer static before-image types are invalid."
    }
    Assert-MihoInstallerRelativePathV1 -Path ([string]$Record.install_path)
    if (($Record.before_present -and ([string]$Record.before_sha256 -cnotmatch '^[0-9a-f]{64}$' -or [string]::IsNullOrEmpty([string]$Record.backup_relative))) -or
        (-not $Record.before_present -and ([int64]$Record.before_size -ne 0 -or -not [string]::IsNullOrEmpty([string]$Record.before_sha256) -or -not [string]::IsNullOrEmpty([string]$Record.backup_relative))) -or
        ($Record.after_present -and [string]$Record.after_sha256 -cnotmatch '^[0-9a-f]{64}$') -or
        (-not $Record.after_present -and ([int64]$Record.after_size -ne 0 -or -not [string]::IsNullOrEmpty([string]$Record.after_sha256)))) {
        throw "Installer static before-image invariants are invalid."
    }
    if ($Record.before_present) { Assert-MihoInstallerRelativePathV1 -Path ([string]$Record.backup_relative) }
}

function Assert-MihoInstallerDynamicRecordV1 {
    param([Parameter(Mandatory = $true)]$Record)
    Assert-MihoObjectExactPropertyNamesV1 -Object $Record -ExpectedNames @(
        "label", "path", "before_present", "before_size", "before_sha256", "backup_relative",
        "expected_after_present", "after_captured", "after_size", "after_sha256"
    ) -Label "Installer dynamic before-image"
    if ($Record.label -isnot [string] -or $Record.path -isnot [string] -or
        $Record.before_present -isnot [bool] -or -not (Test-MihoInstallerIntegerV1 -Value $Record.before_size) -or
        $Record.before_sha256 -isnot [string] -or $Record.backup_relative -isnot [string] -or
        $Record.expected_after_present -isnot [bool] -or $Record.after_captured -isnot [bool] -or
        -not (Test-MihoInstallerIntegerV1 -Value $Record.after_size) -or $Record.after_sha256 -isnot [string]) {
        throw "Installer dynamic before-image types are invalid."
    }
    $null = Assert-MihoInstallerAbsolutePathV1 -Path ([string]$Record.path) -Label "Installer dynamic path"
    if (($Record.before_present -and ([string]$Record.before_sha256 -cnotmatch '^[0-9a-f]{64}$' -or [string]::IsNullOrEmpty([string]$Record.backup_relative))) -or
        (-not $Record.before_present -and ([int64]$Record.before_size -ne 0 -or -not [string]::IsNullOrEmpty([string]$Record.before_sha256) -or -not [string]::IsNullOrEmpty([string]$Record.backup_relative))) -or
        ($Record.after_captured -and [string]$Record.after_sha256 -cnotmatch '^[0-9a-f]{64}$')) {
        throw "Installer dynamic before-image invariants are invalid."
    }
    if ($Record.before_present) { Assert-MihoInstallerRelativePathV1 -Path ([string]$Record.backup_relative) }
}

function Assert-MihoInstallerJournalRecordsV1 {
    param([Parameter(Mandatory = $true)]$Journal)
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    foreach ($record in @($Journal.static_files)) {
        Assert-MihoInstallerStaticRecordV1 -Record $record
        if (-not $seen.Add([string]$record.install_path)) { throw "Installer static before-image contains duplicate paths." }
    }
    if (-not $seen.Contains($script:MihoStaticOwnershipFileV1)) { throw "Installer static before-image omits its ownership manifest." }
    $dynamicLabels = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    foreach ($record in @($Journal.dynamic_files)) {
        Assert-MihoInstallerDynamicRecordV1 -Record $record
        if (-not $dynamicLabels.Add([string]$record.label)) { throw "Installer dynamic before-image contains duplicate labels." }
    }
    foreach ($record in @($Journal.registry_trees)) {
        Assert-MihoObjectExactPropertyNamesV1 -Object $record -ExpectedNames @("label", "before", "after_sha256") -Label "Installer registry before-image"
        if ($record.label -isnot [string] -or $record.before -isnot [pscustomobject] -or $record.after_sha256 -isnot [string] -or
            (-not [string]::IsNullOrEmpty([string]$record.after_sha256) -and [string]$record.after_sha256 -cnotmatch '^[0-9a-f]{64}$')) {
            throw "Installer registry before-image record is invalid."
        }
        Assert-MihoObjectExactPropertyNamesV1 -Object $record.before -ExpectedNames @("subkey", "present", "tree") -Label "Installer registry snapshot"
        if ($record.before.subkey -isnot [string] -or $record.before.present -isnot [bool]) { throw "Installer registry snapshot is invalid." }
    }
}

function Test-MihoInstallerFileStateV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][bool]$Present,
        [Parameter(Mandatory = $true)][int64]$Size,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Sha256
    )
    if (-not (Test-Path -LiteralPath $Path)) { return -not $Present }
    if (-not $Present) { return $false }
    try {
        Assert-MihoNoReparseChainV1 -Path $Path
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        return (-not $item.PSIsContainer -and [int64]$item.Length -eq $Size -and (Get-MihoFileSha256V1 -Path $Path) -ceq $Sha256)
    }
    catch { return $false }
}

function Write-MihoInstallerFileFromPathV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][int64]$ExpectedSize,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256
    )
    Assert-MihoNoReparseChainV1 -Path $Source
    $sourceItem = Get-Item -LiteralPath $Source -Force -ErrorAction Stop
    if ($sourceItem.PSIsContainer -or [int64]$sourceItem.Length -ne $ExpectedSize -or
        (Get-MihoFileSha256V1 -Path $Source) -cne $ExpectedSha256) {
        throw "Installer transaction source bytes drifted."
    }
    $parent = Split-Path -Parent $Target
    if (-not (Test-Path -LiteralPath $parent)) { [System.IO.Directory]::CreateDirectory($parent) | Out-Null }
    Assert-MihoNoReparseChainV1 -Path $parent
    $bytes = [System.IO.File]::ReadAllBytes($Source)
    if ([int64]$bytes.Length -ne $ExpectedSize -or (Get-MihoSha256BytesV1 -Bytes $bytes) -cne $ExpectedSha256) {
        throw "Installer transaction source changed while reading."
    }
    Write-MihoAtomicBytesCoreV1 -Path $Target -Bytes $bytes
    if (-not (Test-MihoInstallerFileStateV1 -Path $Target -Present $true -Size $ExpectedSize -Sha256 $ExpectedSha256)) {
        throw "Installer transaction target verification failed."
    }
}

function Install-MihoStaticPayloadV1 {
    param([Parameter(Mandatory = $true)]$Evidence)
    $journal = $Evidence.Object
    Assert-MihoInstallerJournalRecordsV1 -Journal $journal
    if ([string]$journal.phase -eq "static-applied") {
        foreach ($record in @($journal.static_files)) {
            $target = Join-MihoInstallerOwnedPathV1 -Root $Evidence.InstallRoot -Relative ([string]$record.install_path)
            if (-not (Test-MihoInstallerFileStateV1 -Path $target -Present ([bool]$record.after_present) -Size ([int64]$record.after_size) -Sha256 ([string]$record.after_sha256))) {
                throw "Previously applied installer static payload drifted."
            }
        }
        return [pscustomobject][ordered]@{ schema = "miho-installer-static-result-v1"; applied = $true; recovered = $true }
    }
    if ([string]$journal.phase -cne "claimed") { throw "Installer static apply requires a completed owner claim." }
    $manifestPath = Join-Path $Evidence.StagingRoot $script:MihoStaticOwnershipFileV1
    $manifest = Read-MihoStaticOwnershipManifestV1 -Path $manifestPath -PayloadRoot $Evidence.StagingRoot -RequireExactPayloadTree
    if ((Get-MihoSha256BytesV1 -Bytes $manifest.Record.Bytes) -cne [string]$journal.new_manifest_sha256) {
        throw "Installer staging manifest no longer matches the transaction."
    }
    foreach ($record in @($journal.static_files)) {
        $target = Join-MihoInstallerOwnedPathV1 -Root $Evidence.InstallRoot -Relative ([string]$record.install_path)
        if (-not (Test-MihoInstallerFileStateV1 -Path $target -Present ([bool]$record.before_present) -Size ([int64]$record.before_size) -Sha256 ([string]$record.before_sha256))) {
            throw "Installer-owned static state changed after its before-image was captured."
        }
    }
    $journal.phase = "applying-static"
    Write-MihoInstallerJournalV1 -Journal $journal -Root $Evidence.Root
    try {
        $records = @($journal.static_files | Where-Object { [string]$_.install_path -cne $script:MihoStaticOwnershipFileV1 }) +
            @($journal.static_files | Where-Object { [string]$_.install_path -ceq $script:MihoStaticOwnershipFileV1 })
        foreach ($record in $records) {
            $target = Join-MihoInstallerOwnedPathV1 -Root $Evidence.InstallRoot -Relative ([string]$record.install_path)
            if ($record.after_present) {
                $source = Join-MihoInstallerOwnedPathV1 -Root $Evidence.StagingRoot -Relative ([string]$record.install_path)
                Write-MihoInstallerFileFromPathV1 -Source $source -Target $target -ExpectedSize ([int64]$record.after_size) -ExpectedSha256 ([string]$record.after_sha256)
            }
            elseif (Test-Path -LiteralPath $target) {
                if (-not (Test-MihoInstallerFileStateV1 -Path $target -Present $true -Size ([int64]$record.before_size) -Sha256 ([string]$record.before_sha256))) {
                    throw "A retired installer-owned static file drifted and was preserved."
                }
                Remove-Item -LiteralPath $target -Force -ErrorAction Stop
            }
        }
        foreach ($record in @($journal.static_files)) {
            $target = Join-MihoInstallerOwnedPathV1 -Root $Evidence.InstallRoot -Relative ([string]$record.install_path)
            if (-not (Test-MihoInstallerFileStateV1 -Path $target -Present ([bool]$record.after_present) -Size ([int64]$record.after_size) -Sha256 ([string]$record.after_sha256))) {
                throw "Installer static payload final verification failed."
            }
        }
        $journal.phase = "static-applied"
        $journal.failure = ""
        Write-MihoInstallerJournalV1 -Journal $journal -Root $Evidence.Root
    }
    catch {
        $journal.failure = "static-apply-failed"
        try { Write-MihoInstallerJournalV1 -Journal $journal -Root $Evidence.Root } catch { }
        throw
    }
    return [pscustomobject][ordered]@{ schema = "miho-installer-static-result-v1"; applied = $true; recovered = $false }
}

function Claim-MihoInstallerAutomationV1 {
    param([Parameter(Mandatory = $true)]$Evidence)
    $journal = $Evidence.Object
    if ([string]$journal.phase -in @("claimed", "applying-static", "static-applied", "prepared", "dynamic-verified", "committed")) {
        return [pscustomobject][ordered]@{ schema = "miho-installer-claim-result-v1"; claimed = $true; recovered = $true; claim_created_new_owner = [bool]$journal.claim_created_new_owner }
    }
    if ([string]$journal.phase -cne "owner-registered") { throw "Installer owner claim is unavailable in the current phase." }
    if ((Get-MihoInstalledOwnerRegistryV1) -cne [string]$journal.owner_instance_id) { throw "Installed automation owner registry value drifted before claim." }
    $parameters = @{
        ExpectedOwnerKind = "installed"
        ExpectedOwnerInstanceId = [string]$journal.owner_instance_id
    }
    if (-not [string]::IsNullOrWhiteSpace($AutomationRoot)) { $parameters.AutomationRoot = $AutomationRoot }
    $result = Claim-MihoAutomationOwnerV1 @parameters
    Assert-MihoObjectExactPropertyNamesV1 -Object $result -ExpectedNames @(
        "schema", "owner_kind", "owner_instance_id", "owner_epoch", "claimed", "recovered", "root_was_absent", "claim_created_new_owner"
    ) -Label "Automation owner claim result"
    if ($result.schema -isnot [string] -or [string]$result.schema -cne "miho-automation-owner-claim-result-v1" -or
        [string]$result.owner_kind -cne "installed" -or [string]$result.owner_instance_id -cne [string]$journal.owner_instance_id -or
        -not (Test-MihoCanonicalUuidV1 -Value ([string]$result.owner_epoch)) -or $result.claimed -ne $true -or
        $result.recovered -isnot [bool] -or $result.root_was_absent -isnot [bool] -or $result.claim_created_new_owner -isnot [bool] -or
        [bool]$result.root_was_absent -ne [bool]$result.claim_created_new_owner) {
        throw "Automation owner claim result is invalid."
    }
    $journal.claim_created_new_owner = [bool]$result.claim_created_new_owner
    $journal.phase = "claimed"
    Write-MihoInstallerJournalV1 -Journal $journal -Root $Evidence.Root
    return [pscustomobject][ordered]@{ schema = "miho-installer-claim-result-v1"; claimed = $true; recovered = [bool]$result.recovered; claim_created_new_owner = [bool]$result.claim_created_new_owner }
}

function Prepare-MihoInstallerAutomationV1 {
    param([Parameter(Mandatory = $true)]$Evidence)
    $journal = $Evidence.Object
    if ([string]$journal.phase -in @("prepared", "dynamic-verified", "committed")) {
        $owner = New-MihoExpectedOwnerV1 -OwnerKind "installed" -OwnerInstanceId ([string]$journal.owner_instance_id)
        $handoff = Read-MihoPrepareHandoffReceiptV1 -Path $Evidence.HandoffPath -CallerNonce ([string]$journal.caller_nonce) -ExpectedOwner $owner -CoordinatorPid ([int64]$journal.coordinator_pid)
        return [pscustomobject][ordered]@{ schema = "miho-installer-prepare-result-v1"; prepared = $true; recovered = $true; handoff_phase = [string]$handoff.Object.phase }
    }
    if ([string]$journal.phase -cne "static-applied") { throw "Automation prepare requires the exact static payload." }
    $source = Join-MihoInstallerOwnedPathV1 -Root $Evidence.InstallRoot -Relative "miho.exe"
    $parameters = @{
        SourceCli = $source
        ExpectedOwnerKind = "installed"
        ExpectedOwnerInstanceId = [string]$journal.owner_instance_id
        ResultPath = $Evidence.HandoffPath
        CallerNonce = [string]$journal.caller_nonce
        CoordinatorPid = [int64]$journal.coordinator_pid
        At = $At
        CandidateTimeoutSeconds = $CandidateTimeoutSeconds
        ProcessTimeoutSeconds = $ProcessTimeoutSeconds
        PrepareValiditySeconds = $PrepareValiditySeconds
    }
    if (-not [string]::IsNullOrWhiteSpace($Workspace)) { $parameters.Workspace = $Workspace }
    if (-not [string]::IsNullOrWhiteSpace($DefaultWorkspace)) { $parameters.DefaultWorkspace = $DefaultWorkspace }
    if (-not [string]::IsNullOrWhiteSpace($DesktopSettingsPath)) { $parameters.DesktopSettingsPath = $DesktopSettingsPath }
    if (-not [string]::IsNullOrWhiteSpace($Config)) { $parameters.Config = $Config }
    if (-not [string]::IsNullOrWhiteSpace($AutomationRoot)) { $parameters.AutomationRoot = $AutomationRoot }
    $null = Prepare-MihoDailyUpdateTaskInstallV1 @parameters
    $owner = New-MihoExpectedOwnerV1 -OwnerKind "installed" -OwnerInstanceId ([string]$journal.owner_instance_id)
    $handoff = Read-MihoPrepareHandoffReceiptV1 -Path $Evidence.HandoffPath -CallerNonce ([string]$journal.caller_nonce) -ExpectedOwner $owner -CoordinatorPid ([int64]$journal.coordinator_pid)
    if ([string]$handoff.Object.phase -cne "candidate-removed") { throw "Automation prepare handoff is not at its durable prepared phase." }
    $journal.phase = "prepared"
    $journal.failure = ""
    Write-MihoInstallerJournalV1 -Journal $journal -Root $Evidence.Root
    return [pscustomobject][ordered]@{ schema = "miho-installer-prepare-result-v1"; prepared = $true; recovered = $false; handoff_phase = [string]$handoff.Object.phase }
}

function Get-MihoInstallerRegistrySnapshotHashV1 {
    param([Parameter(Mandatory = $true)]$Snapshot)
    return Get-MihoSha256BytesV1 -Bytes (ConvertTo-MihoJsonBytesV1 -Object $Snapshot -Depth 20)
}

function Test-MihoShortcutTargetV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Shortcut,
        [Parameter(Mandatory = $true)][string]$ExpectedTarget,
        [Parameter(Mandatory = $true)][string]$ExpectedWorkingDirectory
    )
    try {
        $shell = New-Object -ComObject WScript.Shell
        $link = $shell.CreateShortcut($Shortcut)
        return (
            [string]::Equals((Get-MihoNormalizedFullPathV1 -Path ([string]$link.TargetPath)), (Get-MihoNormalizedFullPathV1 -Path $ExpectedTarget), [System.StringComparison]::OrdinalIgnoreCase) -and
            [string]::Equals((Get-MihoNormalizedFullPathV1 -Path ([string]$link.WorkingDirectory)), (Get-MihoNormalizedFullPathV1 -Path $ExpectedWorkingDirectory), [System.StringComparison]::OrdinalIgnoreCase)
        )
    }
    catch { return $false }
}

function Assert-MihoInstallerRegistryReadyV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Install,
        [Parameter(Mandatory = $true)][string]$Product,
        [Parameter(Mandatory = $true)][string]$Publisher,
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string]$BinaryName
    )
    $productKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey(("Software\{0}\{1}" -f $Publisher, $Product), $false)
    if ($null -eq $productKey) { throw "Installer location registry key is missing." }
    try {
        if ([string]$productKey.GetValue("", "") -cne $Install) { throw "Installer location registry value is invalid." }
    }
    finally { $productKey.Dispose() }
    $uninstallKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey(("Software\Microsoft\Windows\CurrentVersion\Uninstall\{0}" -f $Product), $false)
    if ($null -eq $uninstallKey) { throw "Installer uninstall registry key is missing." }
    try {
        $expected = [ordered]@{
            "DisplayName" = $Product
            "DisplayVersion" = $Version
            "Publisher" = $Publisher
            "MainBinaryName" = ($BinaryName + ".exe")
            "DisplayIcon" = ('"' + (Join-Path $Install ($BinaryName + ".exe")) + '"')
            "InstallLocation" = ('"' + $Install + '"')
            "UninstallString" = ('"' + (Join-Path $Install "uninstall.exe") + '"')
        }
        foreach ($name in $expected.Keys) {
            if ($uninstallKey.GetValueKind($name) -ne [Microsoft.Win32.RegistryValueKind]::String -or
                [string]$uninstallKey.GetValue($name, "", [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames) -cne [string]$expected[$name]) {
                throw "Installer uninstall registry value '$name' is invalid."
            }
        }
        foreach ($name in @("NoModify", "NoRepair", "EstimatedSize")) {
            if ($uninstallKey.GetValueKind($name) -ne [Microsoft.Win32.RegistryValueKind]::DWord) { throw "Installer uninstall registry value '$name' has the wrong type." }
        }
        if ([int32]$uninstallKey.GetValue("NoModify", 0) -ne 1 -or [int32]$uninstallKey.GetValue("NoRepair", 0) -ne 1 -or
            [int32]$uninstallKey.GetValue("EstimatedSize", 0) -lt 0) {
            throw "Installer uninstall registry numeric values are invalid."
        }
    }
    finally { $uninstallKey.Dispose() }
}

function Confirm-MihoInstallerDynamicStateV1 {
    param([Parameter(Mandatory = $true)]$Evidence)
    $journal = $Evidence.Object
    if ([string]$journal.phase -eq "dynamic-verified") {
        return [pscustomobject][ordered]@{ schema = "miho-installer-dynamic-result-v1"; verified = $true; recovered = $true }
    }
    if ([string]$journal.phase -cne "prepared") { throw "Dynamic verification requires a prepared automation transaction." }
    if ((Get-MihoInstalledOwnerRegistryV1) -cne [string]$journal.owner_instance_id) { throw "Installed automation owner registry value drifted before commit." }
    foreach ($record in @($journal.static_files)) {
        $target = Join-MihoInstallerOwnedPathV1 -Root $Evidence.InstallRoot -Relative ([string]$record.install_path)
        if (-not (Test-MihoInstallerFileStateV1 -Path $target -Present ([bool]$record.after_present) -Size ([int64]$record.after_size) -Sha256 ([string]$record.after_sha256))) {
            throw "Installer static payload drifted before automation commit."
        }
    }
    Assert-MihoInstallerRegistryReadyV1 -Install $Evidence.InstallRoot -Product $ProductName -Publisher $Manufacturer -Version $ProductVersion -BinaryName $MainBinaryName
    $expectedExecutable = Join-Path $Evidence.InstallRoot ($MainBinaryName + ".exe")
    foreach ($record in @($journal.dynamic_files)) {
        Assert-MihoInstallerDynamicRecordV1 -Record $record
        $present = Test-Path -LiteralPath ([string]$record.path)
        if ($record.expected_after_present -and -not $present) {
            throw "Required installer dynamic file '$([string]$record.label)' is missing."
        }
        if (-not $record.expected_after_present -and [string]$record.label -like "*-shortcut") {
            if ([bool]$record.before_present -ne [bool]$present) { throw "Optional desktop shortcut changed outside its selected policy." }
            if ($present -and -not (Test-MihoInstallerFileStateV1 -Path ([string]$record.path) -Present $true -Size ([int64]$record.before_size) -Sha256 ([string]$record.before_sha256))) {
                throw "Existing desktop shortcut drifted during install."
            }
        }
        if ($present) {
            Assert-MihoNoReparseChainV1 -Path ([string]$record.path)
            $item = Get-Item -LiteralPath ([string]$record.path) -Force -ErrorAction Stop
            if ($item.PSIsContainer) { throw "Installer dynamic file has the wrong type." }
            if ([string]$record.label -like "*-shortcut" -and -not (Test-MihoShortcutTargetV1 -Shortcut ([string]$record.path) -ExpectedTarget $expectedExecutable -ExpectedWorkingDirectory $Evidence.InstallRoot)) {
                throw "Installer shortcut target or working directory is invalid."
            }
            $record.after_size = [int64]$item.Length
            $record.after_sha256 = Get-MihoFileSha256V1 -Path ([string]$record.path)
            $record.after_captured = $true
        }
    }
    foreach ($record in @($journal.registry_trees)) {
        $after = Export-MihoInstallerRegistryTreeV1 -SubKey ([string]$record.before.subkey)
        if (-not $after.present) { throw "Required installer registry state is missing." }
        $record.after_sha256 = Get-MihoInstallerRegistrySnapshotHashV1 -Snapshot $after
    }
    $journal.phase = "dynamic-verified"
    $journal.failure = ""
    Write-MihoInstallerJournalV1 -Journal $journal -Root $Evidence.Root
    return [pscustomobject][ordered]@{ schema = "miho-installer-dynamic-result-v1"; verified = $true; recovered = $false }
}

function Commit-MihoInstallerAutomationV1 {
    param([Parameter(Mandatory = $true)]$Evidence)
    $journal = $Evidence.Object
    $owner = New-MihoExpectedOwnerV1 -OwnerKind "installed" -OwnerInstanceId ([string]$journal.owner_instance_id)
    $handoff = Read-MihoPrepareHandoffReceiptV1 -Path $Evidence.HandoffPath -CallerNonce ([string]$journal.caller_nonce) -ExpectedOwner $owner -CoordinatorPid ([int64]$journal.coordinator_pid)
    if ([string]$handoff.Object.phase -eq "committed") {
        if ([string]$journal.phase -ne "committed") {
            $journal.phase = "committed"
            $journal.failure = ""
            try { Write-MihoInstallerJournalV1 -Journal $journal -Root $Evidence.Root } catch { }
        }
        return [pscustomobject][ordered]@{ schema = "miho-installer-commit-result-v1"; committed = $true; recovered = $true }
    }
    if ([string]$journal.phase -cne "dynamic-verified" -or [string]$handoff.Object.phase -cne "candidate-removed") {
        throw "Automation commit requires verified dynamic state and a durable prepare handoff."
    }
    $parameters = @{
        TransactionToken = [string]$handoff.Object.transaction_token
        ExpectedOwnerKind = "installed"
        ExpectedOwnerInstanceId = [string]$journal.owner_instance_id
        ProcessTimeoutSeconds = $ProcessTimeoutSeconds
        ResultPath = $Evidence.HandoffPath
        CallerNonce = [string]$journal.caller_nonce
        CoordinatorPid = [int64]$journal.coordinator_pid
    }
    if (-not [string]::IsNullOrWhiteSpace($AutomationRoot)) { $parameters.AutomationRoot = $AutomationRoot }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedLegacyXmlSha256)) { $parameters.ExpectedLegacyXmlSha256 = $ExpectedLegacyXmlSha256 }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedLegacySddlSha256)) { $parameters.ExpectedLegacySddlSha256 = $ExpectedLegacySddlSha256 }
    $null = Commit-MihoDailyUpdateTaskInstallV1 @parameters
    $terminal = Read-MihoPrepareHandoffReceiptV1 -Path $Evidence.HandoffPath -CallerNonce ([string]$journal.caller_nonce) -ExpectedOwner $owner -CoordinatorPid ([int64]$journal.coordinator_pid)
    if ([string]$terminal.Object.phase -cne "committed") { throw "Automation commit did not publish its terminal handoff before returning." }
    $journal.phase = "committed"
    $journal.failure = ""
    try { Write-MihoInstallerJournalV1 -Journal $journal -Root $Evidence.Root } catch { }
    return [pscustomobject][ordered]@{ schema = "miho-installer-commit-result-v1"; committed = $true; recovered = $false }
}

function Restore-MihoInstallerFilesV1 {
    param([Parameter(Mandatory = $true)]$Evidence)
    $journal = $Evidence.Object
    foreach ($record in @($journal.dynamic_files)) {
        Assert-MihoInstallerDynamicRecordV1 -Record $record
        $target = [string]$record.path
        if ($record.before_present) {
            $backup = Join-Path $Evidence.Root ([string]$record.backup_relative).Replace('/', '\')
            Write-MihoInstallerFileFromPathV1 -Source $backup -Target $target -ExpectedSize ([int64]$record.before_size) -ExpectedSha256 ([string]$record.before_sha256)
        }
        elseif (Test-Path -LiteralPath $target) {
            Assert-MihoNoReparseChainV1 -Path $target
            $item = Get-Item -LiteralPath $target -Force -ErrorAction Stop
            if ($item.PSIsContainer) { throw "Installer rollback encountered a dynamic directory." }
            Remove-Item -LiteralPath $target -Force -ErrorAction Stop
        }
    }
    $static = @($journal.static_files)
    [array]::Reverse($static)
    foreach ($record in $static) {
        Assert-MihoInstallerStaticRecordV1 -Record $record
        $target = Join-MihoInstallerOwnedPathV1 -Root $Evidence.InstallRoot -Relative ([string]$record.install_path)
        if ($record.before_present) {
            $backup = Join-Path $Evidence.Root ([string]$record.backup_relative).Replace('/', '\')
            Write-MihoInstallerFileFromPathV1 -Source $backup -Target $target -ExpectedSize ([int64]$record.before_size) -ExpectedSha256 ([string]$record.before_sha256)
        }
        elseif (Test-Path -LiteralPath $target) {
            Assert-MihoNoReparseChainV1 -Path $target
            $item = Get-Item -LiteralPath $target -Force -ErrorAction Stop
            if ($item.PSIsContainer) { throw "Installer rollback encountered a static directory." }
            Remove-Item -LiteralPath $target -Force -ErrorAction Stop
        }
    }
    $directories = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($record in @($journal.static_files | Where-Object { -not $_.before_present })) {
        $path = Split-Path -Parent (Join-MihoInstallerOwnedPathV1 -Root $Evidence.InstallRoot -Relative ([string]$record.install_path))
        while ((Test-MihoInstallerPathWithinV1 -Path $path -Parent $Evidence.InstallRoot)) {
            $null = $directories.Add($path)
            $path = Split-Path -Parent $path
        }
    }
    foreach ($directory in @($directories | Sort-Object { $_.Length } -Descending)) {
        if (Test-Path -LiteralPath $directory) {
            Assert-MihoNoReparseChainV1 -Path $directory
            if (@(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop).Count -eq 0) { [System.IO.Directory]::Delete($directory, $false) }
        }
    }
    if (-not [bool]$journal.install_root_was_present -and (Test-Path -LiteralPath $Evidence.InstallRoot)) {
        Assert-MihoNoReparseChainV1 -Path $Evidence.InstallRoot
        $rootItem = Get-Item -LiteralPath $Evidence.InstallRoot -Force -ErrorAction Stop
        if (-not $rootItem.PSIsContainer) { throw "Installer rollback encountered a non-directory install root." }
        if (@(Get-ChildItem -LiteralPath $Evidence.InstallRoot -Force -ErrorAction Stop).Count -eq 0) {
            [System.IO.Directory]::Delete($Evidence.InstallRoot, $false)
        }
    }
}

function Rollback-MihoInstallerTransactionV1 {
    param([Parameter(Mandatory = $true)]$Evidence)
    $journal = $Evidence.Object
    if ([string]$journal.phase -eq "committed") {
        return [pscustomobject][ordered]@{ schema = "miho-installer-rollback-result-v1"; rolled_back = $false; committed = $true; recovered = $true }
    }
    if (Test-Path -LiteralPath $Evidence.HandoffPath) {
        $owner = New-MihoExpectedOwnerV1 -OwnerKind "installed" -OwnerInstanceId ([string]$journal.owner_instance_id)
        $handoff = Read-MihoPrepareHandoffReceiptV1 -Path $Evidence.HandoffPath -CallerNonce ([string]$journal.caller_nonce) -ExpectedOwner $owner -CoordinatorPid ([int64]$journal.coordinator_pid)
        if ([string]$handoff.Object.phase -eq "committed") {
            $journal.phase = "committed"
            $journal.failure = ""
            try { Write-MihoInstallerJournalV1 -Journal $journal -Root $Evidence.Root } catch { }
            return [pscustomobject][ordered]@{ schema = "miho-installer-rollback-result-v1"; rolled_back = $false; committed = $true; recovered = $true }
        }
        if ([string]$handoff.Object.phase -eq "candidate-removed") {
            $parameters = @{
                TransactionToken = [string]$handoff.Object.transaction_token
                ExpectedOwnerKind = "installed"
                ExpectedOwnerInstanceId = [string]$journal.owner_instance_id
                ProcessTimeoutSeconds = $ProcessTimeoutSeconds
                ResultPath = $Evidence.HandoffPath
                CallerNonce = [string]$journal.caller_nonce
                CoordinatorPid = [int64]$journal.coordinator_pid
            }
            if (-not [string]::IsNullOrWhiteSpace($AutomationRoot)) { $parameters.AutomationRoot = $AutomationRoot }
            $null = Rollback-MihoDailyUpdateTaskInstallV1 @parameters
            $handoff = Read-MihoPrepareHandoffReceiptV1 -Path $Evidence.HandoffPath -CallerNonce ([string]$journal.caller_nonce) -ExpectedOwner $owner -CoordinatorPid ([int64]$journal.coordinator_pid)
            if ([string]$handoff.Object.phase -cne "rolled-back") { throw "Automation rollback did not publish its terminal handoff." }
        }
        elseif ([string]$handoff.Object.phase -cne "rolled-back") { throw "Automation handoff phase cannot be rolled back safely." }
    }
    $journal.phase = "rolling-back"
    $journal.failure = ""
    Write-MihoInstallerJournalV1 -Journal $journal -Root $Evidence.Root
    foreach ($record in @($journal.registry_trees)) { Restore-MihoInstallerRegistryTreeV1 -Snapshot $record.before }
    Restore-MihoInstallerFilesV1 -Evidence $Evidence
    if ($journal.claim_created_new_owner) {
        $parameters = @{
            ExpectedOwnerKind = "installed"
            ExpectedOwnerInstanceId = [string]$journal.owner_instance_id
        }
        if (-not [string]::IsNullOrWhiteSpace($AutomationRoot)) { $parameters.AutomationRoot = $AutomationRoot }
        $null = Release-MihoAutomationOwnerClaimV1 @parameters
    }
    if (-not $journal.owner_registry_was_present) { Remove-MihoInstalledOwnerRegistryV1 -ExpectedOwnerInstanceId ([string]$journal.owner_instance_id) }
    elseif ((Get-MihoInstalledOwnerRegistryV1) -cne [string]$journal.owner_instance_id) { throw "Original installed automation owner registry value was not preserved." }
    $journal.phase = "rolled-back"
    $journal.failure = ""
    Write-MihoInstallerJournalV1 -Journal $journal -Root $Evidence.Root
    return [pscustomobject][ordered]@{ schema = "miho-installer-rollback-result-v1"; rolled_back = $true; committed = $false; recovered = $false }
}

function Remove-MihoInstallerTransactionTreeV1 {
    param([Parameter(Mandatory = $true)][string]$Root)
    $rootPath = Assert-MihoInstallerAbsolutePathV1 -Path $Root -Label "Installer transaction cleanup root" -MustExist -Directory
    Assert-MihoInstallerTreeNoReparseV1 -Root $rootPath
    [System.IO.Directory]::Delete($rootPath, $true)
}

function Finalize-MihoInstallerTransactionV1 {
    param([Parameter(Mandatory = $true)]$Evidence)
    if ([string]$Evidence.Object.phase -notin @("committed", "rolled-back")) { throw "Only a terminal installer transaction can be finalized." }
    $terminal = [string]$Evidence.Object.phase
    try {
        Remove-MihoInstallerTransactionTreeV1 -Root $Evidence.Root
        $pending = $false
    }
    catch { $pending = $true }
    return [pscustomobject][ordered]@{ schema = "miho-installer-finalize-result-v1"; terminal_phase = $terminal; cleanup_pending = $pending }
}

function Recover-MihoInstallerTransactionV1 {
    param([Parameter(Mandatory = $true)][string]$Root)
    $rootPath = Assert-MihoInstallerAbsolutePathV1 -Path $Root -Label "Installer transaction root"
    if (-not (Test-Path -LiteralPath $rootPath)) {
        return [pscustomobject][ordered]@{ schema = "miho-installer-recover-result-v1"; found = $false; terminal_phase = "absent"; cleanup_pending = $false }
    }
    $uninstallStaticPath = Join-Path $rootPath $script:MihoInstallerUninstallStaticFileV1
    if (Test-Path -LiteralPath $uninstallStaticPath) {
        $uninstallEvidence = Read-MihoInstallerUninstallStaticJournalV1 -Root $rootPath
        if ([string]$uninstallEvidence.Object.phase -cne "removed") {
            throw "An interrupted static uninstall must be resumed by uninstall.exe before a new install can begin."
        }
        $uninstallResult = Finalize-MihoInstallerUninstallStaticV1 -Root $rootPath
        return [pscustomobject][ordered]@{ schema = "miho-installer-recover-result-v1"; found = $true; terminal_phase = "uninstalled"; cleanup_pending = [bool]$uninstallResult.cleanup_pending }
    }
    $evidence = Read-MihoInstallerJournalV1 -Root $rootPath
    Assert-MihoInstallerJournalRecordsV1 -Journal $evidence.Object
    if ([string]$evidence.Object.phase -eq "committed") {
        $result = Finalize-MihoInstallerTransactionV1 -Evidence $evidence
        return [pscustomobject][ordered]@{ schema = "miho-installer-recover-result-v1"; found = $true; terminal_phase = "committed"; cleanup_pending = [bool]$result.cleanup_pending }
    }
    if ([string]$evidence.Object.phase -eq "rolled-back") {
        $result = Finalize-MihoInstallerTransactionV1 -Evidence $evidence
        return [pscustomobject][ordered]@{ schema = "miho-installer-recover-result-v1"; found = $true; terminal_phase = "rolled-back"; cleanup_pending = [bool]$result.cleanup_pending }
    }
    $result = Rollback-MihoInstallerTransactionV1 -Evidence $evidence
    if ($result.committed) {
        $fresh = Read-MihoInstallerJournalV1 -Root $rootPath
        $final = Finalize-MihoInstallerTransactionV1 -Evidence $fresh
        return [pscustomobject][ordered]@{ schema = "miho-installer-recover-result-v1"; found = $true; terminal_phase = "committed"; cleanup_pending = [bool]$final.cleanup_pending }
    }
    $fresh = Read-MihoInstallerJournalV1 -Root $rootPath
    $final = Finalize-MihoInstallerTransactionV1 -Evidence $fresh
    return [pscustomobject][ordered]@{ schema = "miho-installer-recover-result-v1"; found = $true; terminal_phase = "rolled-back"; cleanup_pending = [bool]$final.cleanup_pending }
}

function Write-MihoInstallerUninstallStaticJournalV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)][string]$Root
    )
    $bytes = ConvertTo-MihoJsonBytesV1 -Object $Journal -Depth 12
    if ($bytes.Length -gt $script:MihoInstallerMaximumJournalBytesV1) { throw "Static uninstall journal is too large." }
    Write-MihoAtomicBytesV1 -Path (Join-Path $Root $script:MihoInstallerUninstallStaticFileV1) -Bytes $bytes -Purpose "installer-uninstall-static-journal"
}

function Read-MihoInstallerUninstallStaticJournalV1 {
    param([Parameter(Mandatory = $true)][string]$Root)
    $rootPath = Assert-MihoInstallerAbsolutePathV1 -Path $Root -Label "Static uninstall transaction root" -MustExist -Directory
    $entries = @(Get-ChildItem -LiteralPath $rootPath -Force -ErrorAction Stop)
    if ($entries.Count -ne 1 -or $entries[0].PSIsContainer -or
        ($entries[0].Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or
        [string]$entries[0].Name -cne $script:MihoInstallerUninstallStaticFileV1) {
        throw "Static uninstall transaction root contains unexpected state."
    }
    $record = Read-MihoJsonFileV1 -Path $entries[0].FullName -MaximumBytes $script:MihoInstallerMaximumJournalBytesV1 -ExpectedKeys @(
        "schema_version", "owner_instance_id", "install_root", "manifest_size", "manifest_sha256", "files", "phase"
    )
    $journal = $record.Object
    Assert-MihoObjectExactPropertyNamesV1 -Object $journal -ExpectedNames @(
        "schema_version", "owner_instance_id", "install_root", "manifest_size", "manifest_sha256", "files", "phase"
    ) -Label "Static uninstall journal"
    if ($journal.schema_version -isnot [string] -or [string]$journal.schema_version -cne $script:MihoInstallerUninstallStaticSchemaV1 -or
        $journal.owner_instance_id -isnot [string] -or -not (Test-MihoCanonicalUuidV1 -Value ([string]$journal.owner_instance_id)) -or
        $journal.install_root -isnot [string] -or -not (Test-MihoInstallerIntegerV1 -Value $journal.manifest_size) -or
        [int64]$journal.manifest_size -lt 0 -or $journal.manifest_sha256 -isnot [string] -or
        [string]$journal.manifest_sha256 -cnotmatch '^[0-9a-f]{64}$' -or $journal.phase -isnot [string] -or
        [string]$journal.phase -cnotin @("removing", "removed") -or $null -eq $journal.files -or $journal.files -is [string]) {
        throw "Static uninstall journal identity or types are invalid."
    }
    $installPath = Assert-MihoInstallerAbsolutePathV1 -Path ([string]$journal.install_root) -Label "Static uninstall journal install root"
    $files = @{}
    $previous = $null
    foreach ($file in @($journal.files)) {
        Assert-MihoObjectExactPropertyNamesV1 -Object $file -ExpectedNames @("install_path", "size", "sha256") -Label "Static uninstall journal file"
        if ($file.install_path -isnot [string] -or -not (Test-MihoInstallerIntegerV1 -Value $file.size) -or
            [int64]$file.size -lt 0 -or $file.sha256 -isnot [string] -or [string]$file.sha256 -cnotmatch '^[0-9a-f]{64}$') {
            throw "Static uninstall journal file is invalid."
        }
        $relative = [string]$file.install_path
        Assert-MihoInstallerRelativePathV1 -Path $relative
        if ($relative -ceq $script:MihoStaticOwnershipFileV1 -or $files.ContainsKey($relative) -or
            ($null -ne $previous -and [string]::CompareOrdinal([string]$previous, $relative) -ge 0)) {
            throw "Static uninstall journal file set is duplicated, self-referential, or unsorted."
        }
        $previous = $relative
        $files[$relative] = $file
    }
    return [pscustomobject][ordered]@{
        Record = $record
        Object = $journal
        Root = $rootPath
        InstallRoot = $installPath
        ManifestPath = Join-Path $installPath $script:MihoStaticOwnershipFileV1
        Files = $files
        OrderedPaths = @($journal.files | ForEach-Object { [string]$_.install_path })
    }
}

function New-MihoInstallerUninstallStaticJournalV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Install,
        [Parameter(Mandatory = $true)][string]$OwnerInstanceId,
        [Parameter(Mandatory = $true)]$Manifest
    )
    $rootPath = Assert-MihoInstallerAbsolutePathV1 -Path $Root -Label "Static uninstall transaction root"
    $parent = Assert-MihoInstallerAbsolutePathV1 -Path (Split-Path -Parent $rootPath) -Label "Static uninstall transaction parent" -MustExist -Directory
    if ([string]::Equals($rootPath, $Install, [System.StringComparison]::OrdinalIgnoreCase) -or
        (Test-MihoInstallerPathWithinV1 -Path $rootPath -Parent $Install) -or
        (Test-MihoInstallerPathWithinV1 -Path $Install -Parent $rootPath)) {
        throw "Static uninstall transaction and install roots must not overlap."
    }
    if (Test-Path -LiteralPath $rootPath) { throw "A product transaction already exists." }
    [System.IO.Directory]::CreateDirectory($rootPath) | Out-Null
    try {
        $records = @($Manifest.OrderedPaths | ForEach-Object {
            $item = $Manifest.Files[[string]$_]
            [pscustomobject][ordered]@{ install_path = [string]$_; size = [int64]$item.size; sha256 = [string]$item.sha256 }
        })
        $journal = [pscustomobject][ordered]@{
            schema_version = $script:MihoInstallerUninstallStaticSchemaV1
            owner_instance_id = $OwnerInstanceId
            install_root = $Install
            manifest_size = [int64]$Manifest.Record.Bytes.Length
            manifest_sha256 = Get-MihoSha256BytesV1 -Bytes $Manifest.Record.Bytes
            files = $records
            phase = "removing"
        }
        Write-MihoInstallerUninstallStaticJournalV1 -Journal $journal -Root $rootPath
    }
    catch {
        if ((Test-Path -LiteralPath $rootPath) -and @(Get-ChildItem -LiteralPath $rootPath -Force -ErrorAction SilentlyContinue).Count -eq 0) {
            [System.IO.Directory]::Delete($rootPath, $false)
        }
        throw
    }
    return Read-MihoInstallerUninstallStaticJournalV1 -Root $rootPath
}

function Get-MihoInstallerUninstallStaticEvidenceV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Install,
        [Parameter(Mandatory = $true)][string]$OwnerInstanceId
    )
    if (-not (Test-MihoCanonicalUuidV1 -Value $OwnerInstanceId)) { throw "Static uninstall owner identity is invalid." }
    if ((Get-MihoInstalledOwnerRegistryV1) -cne $OwnerInstanceId) { throw "Static uninstall owner registry identity is missing or drifted." }
    $installPath = Assert-MihoInstallerAbsolutePathV1 -Path $Install -Label "Static uninstall root" -MustExist -Directory
    $rootPath = Assert-MihoInstallerAbsolutePathV1 -Path $Root -Label "Static uninstall transaction root"
    if (-not (Test-Path -LiteralPath $rootPath)) {
        $manifestPath = Join-Path $installPath $script:MihoStaticOwnershipFileV1
        $manifest = Read-MihoStaticOwnershipManifestV1 -Path $manifestPath -PayloadRoot $installPath
        foreach ($relative in @($manifest.OrderedPaths)) {
            $item = $manifest.Files[$relative]
            $target = Join-MihoInstallerOwnedPathV1 -Root $installPath -Relative $relative
            if (-not (Test-MihoInstallerFileStateV1 -Path $target -Present $true -Size ([int64]$item.size) -Sha256 ([string]$item.sha256))) {
                throw "An installer-owned static file is missing, drifted, or unsafe; uninstall preserved all static files."
            }
        }
        $evidence = New-MihoInstallerUninstallStaticJournalV1 -Root $rootPath -Install $installPath -OwnerInstanceId $OwnerInstanceId -Manifest $manifest
    }
    else { $evidence = Read-MihoInstallerUninstallStaticJournalV1 -Root $rootPath }
    if ([string]$evidence.Object.owner_instance_id -cne $OwnerInstanceId -or
        -not ([string]::Equals($evidence.InstallRoot, $installPath, [System.StringComparison]::OrdinalIgnoreCase))) {
        throw "Static uninstall journal belongs to another owner or install root."
    }
    foreach ($relative in @($evidence.OrderedPaths)) {
        $item = $evidence.Files[$relative]
        $target = Join-MihoInstallerOwnedPathV1 -Root $installPath -Relative $relative
        if ((Test-Path -LiteralPath $target) -and
            -not (Test-MihoInstallerFileStateV1 -Path $target -Present $true -Size ([int64]$item.size) -Sha256 ([string]$item.sha256))) {
            throw "An installer-owned static file changed after uninstall began; the drifted file was preserved."
        }
    }
    if (Test-Path -LiteralPath $evidence.ManifestPath) {
        if (-not (Test-MihoInstallerFileStateV1 -Path $evidence.ManifestPath -Present $true -Size ([int64]$evidence.Object.manifest_size) -Sha256 ([string]$evidence.Object.manifest_sha256))) {
            throw "The static ownership manifest changed after uninstall began and was preserved."
        }
        $manifest = Read-MihoStaticOwnershipManifestV1 -Path $evidence.ManifestPath -PayloadRoot $installPath
        if ((Get-MihoSha256BytesV1 -Bytes $manifest.Record.Bytes) -cne [string]$evidence.Object.manifest_sha256 -or
            @($manifest.OrderedPaths).Count -ne @($evidence.OrderedPaths).Count) {
            throw "The static ownership manifest no longer matches its uninstall journal."
        }
        foreach ($relative in @($evidence.OrderedPaths)) {
            $left = $manifest.Files[$relative]
            $right = $evidence.Files[$relative]
            if ($null -eq $left -or [int64]$left.size -ne [int64]$right.size -or [string]$left.sha256 -cne [string]$right.sha256) {
                throw "The static ownership manifest no longer matches its uninstall journal."
            }
        }
    }
    return $evidence
}

function Verify-MihoInstallerUninstallStaticV1 {
    param([Parameter(Mandatory = $true)][string]$Root, [Parameter(Mandatory = $true)][string]$Install, [Parameter(Mandatory = $true)][string]$OwnerInstanceId)
    $evidence = Get-MihoInstallerUninstallStaticEvidenceV1 -Root $Root -Install $Install -OwnerInstanceId $OwnerInstanceId
    return [pscustomobject][ordered]@{
        schema = "miho-installer-uninstall-static-verify-result-v1"
        owner_instance_id = $evidence.Object.owner_instance_id
        file_count = [int64]@($evidence.OrderedPaths).Count
        verified = $true
        recovered = [string]$evidence.Object.phase -eq "removed"
    }
}

function Remove-MihoInstallerUninstallStaticV1 {
    param([Parameter(Mandatory = $true)][string]$Root, [Parameter(Mandatory = $true)][string]$Install, [Parameter(Mandatory = $true)][string]$OwnerInstanceId)
    $evidence = Get-MihoInstallerUninstallStaticEvidenceV1 -Root $Root -Install $Install -OwnerInstanceId $OwnerInstanceId
    if ([string]$evidence.Object.phase -eq "removed") {
        foreach ($relative in @($evidence.OrderedPaths)) {
            if (Test-Path -LiteralPath (Join-MihoInstallerOwnedPathV1 -Root $evidence.InstallRoot -Relative $relative)) {
                throw "A terminal static uninstall journal has a present owned file."
            }
        }
        if (Test-Path -LiteralPath $evidence.ManifestPath) { throw "A terminal static uninstall journal has a present ownership manifest." }
        return [pscustomobject][ordered]@{ schema = "miho-installer-uninstall-static-remove-result-v1"; owner_instance_id = $OwnerInstanceId; file_count = [int64]@($evidence.OrderedPaths).Count; removed = $true; recovered = $true }
    }
    $directories = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($relative in @($evidence.OrderedPaths)) {
        $item = $evidence.Files[$relative]
        $target = Join-MihoInstallerOwnedPathV1 -Root $evidence.InstallRoot -Relative $relative
        $parent = Split-Path -Parent $target
        while (Test-MihoInstallerPathWithinV1 -Path $parent -Parent $evidence.InstallRoot) { $null = $directories.Add($parent); $parent = Split-Path -Parent $parent }
        if (Test-Path -LiteralPath $target) {
            if (-not (Test-MihoInstallerFileStateV1 -Path $target -Present $true -Size ([int64]$item.size) -Sha256 ([string]$item.sha256))) { throw "An installer-owned static file changed during uninstall; the drifted file was preserved." }
            Remove-Item -LiteralPath $target -Force -ErrorAction Stop
            if (Test-Path -LiteralPath $target) { throw "An installer-owned static file could not be removed." }
        }
    }
    if (Test-Path -LiteralPath $evidence.ManifestPath) {
        if (-not (Test-MihoInstallerFileStateV1 -Path $evidence.ManifestPath -Present $true -Size ([int64]$evidence.Object.manifest_size) -Sha256 ([string]$evidence.Object.manifest_sha256))) { throw "The static ownership manifest changed during uninstall and was preserved." }
        Remove-Item -LiteralPath $evidence.ManifestPath -Force -ErrorAction Stop
    }
    foreach ($directory in @($directories | Sort-Object { $_.Length } -Descending)) {
        if (Test-Path -LiteralPath $directory) {
            Assert-MihoNoReparseChainV1 -Path $directory
            if (@(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop).Count -eq 0) { [System.IO.Directory]::Delete($directory, $false) }
        }
    }
    $evidence.Object.phase = "removed"
    Write-MihoInstallerUninstallStaticJournalV1 -Journal $evidence.Object -Root $evidence.Root
    return [pscustomobject][ordered]@{ schema = "miho-installer-uninstall-static-remove-result-v1"; owner_instance_id = $OwnerInstanceId; file_count = [int64]@($evidence.OrderedPaths).Count; removed = $true; recovered = $false }
}

function Finalize-MihoInstallerUninstallStaticV1 {
    param([Parameter(Mandatory = $true)][string]$Root)
    $evidence = Read-MihoInstallerUninstallStaticJournalV1 -Root $Root
    if ([string]$evidence.Object.phase -cne "removed") { throw "Static uninstall cannot finalize before owned files are removed." }
    foreach ($relative in @($evidence.OrderedPaths)) {
        if (Test-Path -LiteralPath (Join-MihoInstallerOwnedPathV1 -Root $evidence.InstallRoot -Relative $relative)) { throw "Static uninstall finalization found an owned file." }
    }
    if (Test-Path -LiteralPath $evidence.ManifestPath) { throw "Static uninstall finalization found its ownership manifest." }
    Remove-MihoInstallerTransactionTreeV1 -Root $evidence.Root
    return [pscustomobject][ordered]@{ schema = "miho-installer-uninstall-static-finalize-result-v1"; terminal_phase = "removed"; cleanup_pending = (Test-Path -LiteralPath $evidence.Root) }
}

function Write-MihoInstallerPublicResultV1 {
    param([Parameter(Mandatory = $true)]$Result)
    $Result | ConvertTo-Json -Depth 8 -Compress
}

function Write-MihoInstallerFailureReceiptV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$FailedMode,
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$ErrorMessage
    )

    $destination = Assert-MihoInstallerAbsolutePathV1 -Path $Path -Label "Installer failure receipt"
    $transactionId = ""
    $phase = ""
    try {
        $journalPath = Join-Path $Root $script:MihoInstallerJournalFileV1
        if (Test-Path -LiteralPath $journalPath -PathType Leaf) {
            $failureEvidence = Read-MihoInstallerJournalV1 -Root $Root
            $transactionId = [string]$failureEvidence.Object.transaction_id
            $phase = [string]$failureEvidence.Object.phase
        }
    }
    catch { }
    $receipt = [pscustomobject][ordered]@{
        schema_version = "miho-installer-failure-v1"
        mode = $FailedMode
        transaction_id = $transactionId
        phase = $phase
        error_message = $ErrorMessage
        occurred_at_utc = [DateTime]::UtcNow.ToString("o", [System.Globalization.CultureInfo]::InvariantCulture)
    }
    Write-MihoAtomicBytesV1 -Path $destination -Bytes (ConvertTo-MihoJsonBytesV1 -Object $receipt -Depth 4) -Purpose "installer-failure-receipt"
}

try {
    $resolvedTransactionRoot = Assert-MihoInstallerAbsolutePathV1 -Path $TransactionRoot -Label "Installer transaction root"
    switch ($Mode) {
    "Begin" {
        if ([string]::IsNullOrWhiteSpace($InstallRoot) -or [string]::IsNullOrWhiteSpace($StagingRoot)) { throw "Begin requires install and staging roots." }
        try {
            $result = New-MihoInstallerTransactionV1 -Root $resolvedTransactionRoot -Install $InstallRoot -Staging $StagingRoot -ParentPid $CoordinatorPid
        }
        catch {
            $journalPath = Join-Path $resolvedTransactionRoot $script:MihoInstallerJournalFileV1
            if ((Test-Path -LiteralPath $resolvedTransactionRoot -PathType Container) -and -not (Test-Path -LiteralPath $journalPath)) {
                try { Remove-MihoInstallerTransactionTreeV1 -Root $resolvedTransactionRoot } catch { }
            }
            throw
        }
        Write-MihoInstallerPublicResultV1 -Result $result
    }
    "Recover" { Write-MihoInstallerPublicResultV1 -Result (Recover-MihoInstallerTransactionV1 -Root $resolvedTransactionRoot) }
    "VerifyUninstallStatic" {
        if ([string]::IsNullOrWhiteSpace($InstallRoot) -or [string]::IsNullOrWhiteSpace($ExpectedOwnerInstanceId)) {
            throw "Static uninstall verification requires install root and expected owner identity."
        }
        Write-MihoInstallerPublicResultV1 -Result (Verify-MihoInstallerUninstallStaticV1 -Root $resolvedTransactionRoot -Install $InstallRoot -OwnerInstanceId $ExpectedOwnerInstanceId)
    }
    "RemoveUninstallStatic" {
        if ([string]::IsNullOrWhiteSpace($InstallRoot) -or [string]::IsNullOrWhiteSpace($ExpectedOwnerInstanceId)) {
            throw "Static uninstall removal requires install root and expected owner identity."
        }
        Write-MihoInstallerPublicResultV1 -Result (Remove-MihoInstallerUninstallStaticV1 -Root $resolvedTransactionRoot -Install $InstallRoot -OwnerInstanceId $ExpectedOwnerInstanceId)
    }
    "FinalizeUninstallStatic" {
        Write-MihoInstallerPublicResultV1 -Result (Finalize-MihoInstallerUninstallStaticV1 -Root $resolvedTransactionRoot)
    }
    default {
        $evidence = Read-MihoInstallerJournalV1 -Root $resolvedTransactionRoot
        Assert-MihoInstallerJournalRecordsV1 -Journal $evidence.Object
        switch ($Mode) {
            "Claim" { $result = Claim-MihoInstallerAutomationV1 -Evidence $evidence }
            "ApplyStatic" { $result = Install-MihoStaticPayloadV1 -Evidence $evidence }
            "Prepare" { $result = Prepare-MihoInstallerAutomationV1 -Evidence $evidence }
            "VerifyDynamic" { $result = Confirm-MihoInstallerDynamicStateV1 -Evidence $evidence }
            "Commit" { $result = Commit-MihoInstallerAutomationV1 -Evidence $evidence }
            "Rollback" { $result = Rollback-MihoInstallerTransactionV1 -Evidence $evidence }
            "Finalize" { $result = Finalize-MihoInstallerTransactionV1 -Evidence $evidence }
            "Inspect" {
                $result = [pscustomobject][ordered]@{
                    schema = "miho-installer-inspect-result-v1"
                    transaction_id = [string]$evidence.Object.transaction_id
                    phase = [string]$evidence.Object.phase
                    owner_kind = [string]$evidence.Object.owner_kind
                    owner_instance_id = [string]$evidence.Object.owner_instance_id
                }
            }
        }
        Write-MihoInstallerPublicResultV1 -Result $result
        if ($Mode -ceq "Rollback" -and $result.PSObject.Properties["committed"] -and [bool]$result.committed) {
            # Exit 10 is a narrow NSIS recovery signal: the automation handoff
            # proves that Commit crossed its terminal boundary even though the
            # original PowerShell invocation did not report success.  A normal
            # rollback remains exit 0; every unresolved failure remains nonzero.
            exit 10
        }
    }
    }
}
catch {
    $installerErrorMessage = [string]$_.Exception.Message
    if (-not [string]::IsNullOrWhiteSpace($FailureReceiptPath)) {
        try {
            Write-MihoInstallerFailureReceiptV1 -Path $FailureReceiptPath -FailedMode $Mode -Root $TransactionRoot -ErrorMessage $installerErrorMessage
        }
        catch { }
    }
    throw
}

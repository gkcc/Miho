[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

function Get-Sha256HexV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    return (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
}

function Write-Utf8NoBomV1 {
    param(
        [Parameter(Mandatory = $true)][string]$LiteralPath,
        [Parameter(Mandatory = $true)][string]$Text
    )
    [System.IO.File]::WriteAllText($LiteralPath, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

function Invoke-InstallerHelperV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Shell,
        [Parameter(Mandatory = $true)][string]$Helper,
        [Parameter(Mandatory = $true)][hashtable]$Arguments
    )
    $tokens = New-Object System.Collections.ArrayList
    foreach ($name in $Arguments.Keys) {
        $null = $tokens.Add("-$name")
        if ($Arguments[$name] -is [bool]) {
            if ($Arguments[$name]) { continue }
            $tokens.RemoveAt($tokens.Count - 1)
            continue
        }
        $null = $tokens.Add([string]$Arguments[$name])
    }
    $output = & $Shell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Helper @tokens 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Installer helper failed ($LASTEXITCODE): $($output -join [Environment]::NewLine)" }
    try { return (($output -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop) }
    catch { throw "Installer helper returned invalid JSON: $($output -join [Environment]::NewLine)" }
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$helper = Join-Path $root "scripts\installer_transaction_v1.ps1"
$shells = @()
foreach ($name in @("powershell.exe", "pwsh.exe")) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if ($null -ne $command) { $shells += $command.Source }
}
if ($shells.Count -eq 0) { throw "No PowerShell host is available." }

foreach ($shell in $shells) {
    $nonce = [guid]::NewGuid().ToString("N").ToLowerInvariant()
    $temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("miho-installer-transaction-test-" + $nonce)
    $staging = Join-Path $temporary "staging"
    $install = Join-Path $temporary "install"
    $transaction = Join-Path $temporary "transaction"
    $automation = Join-Path $temporary "automation"
    $product = "MihoTxnTest-" + $nonce
    $manufacturer = "MihoTxnTests-" + $nonce
    $testOwnerSubKey = "Software\com.miho.endgame\tests\$nonce"
    [System.IO.Directory]::CreateDirectory($staging) | Out-Null
    try {
        $payload = Join-Path $staging "miho.exe"
        [System.IO.File]::WriteAllBytes($payload, (New-Object byte[] 4096))
        $stagedInstallerDirectory = Join-Path $staging "installer"
        [System.IO.Directory]::CreateDirectory($stagedInstallerDirectory) | Out-Null
        $stagedHelper = Join-Path $stagedInstallerDirectory "installer_transaction_v1.ps1"
        $stagedScheduler = Join-Path $stagedInstallerDirectory "task_scheduler_v1.ps1"
        Copy-Item -LiteralPath $helper -Destination $stagedHelper -Force -ErrorAction Stop
        Copy-Item -LiteralPath (Join-Path $root "scripts\task_scheduler_v1.ps1") -Destination $stagedScheduler -Force -ErrorAction Stop
        $manifest = [pscustomobject][ordered]@{
            schema_version = "miho-static-ownership-v1"
            product_version = "1.2.3"
            target_triple = "x86_64-pc-windows-msvc"
            files = @(
                [pscustomobject][ordered]@{
                    install_path = "installer/installer_transaction_v1.ps1"
                    size = [int64](Get-Item -LiteralPath $stagedHelper -Force).Length
                    sha256 = Get-Sha256HexV1 -LiteralPath $stagedHelper
                },
                [pscustomobject][ordered]@{
                    install_path = "installer/task_scheduler_v1.ps1"
                    size = [int64](Get-Item -LiteralPath $stagedScheduler -Force).Length
                    sha256 = Get-Sha256HexV1 -LiteralPath $stagedScheduler
                },
                [pscustomobject][ordered]@{
                    install_path = "miho.exe"
                    size = [int64](Get-Item -LiteralPath $payload -Force).Length
                    sha256 = Get-Sha256HexV1 -LiteralPath $payload
                }
            )
            ownership = [pscustomobject][ordered]@{
                manifest_install_path = "miho-static-ownership-v1.json"
                manifest_self_in_files = $false
                files_are_complete = $true
                retired_file_policy = "delete-only-if-old-size-and-sha256-match"
                mutable_data_excluded = $true
            }
        }
        Write-Utf8NoBomV1 -LiteralPath (Join-Path $staging "miho-static-ownership-v1.json") -Text (($manifest | ConvertTo-Json -Depth 8) + "`n")
        $env:MIHO_INSTALLER_TRANSACTION_TEST_V1 = "1"
        $common = [ordered]@{
            TransactionRoot = $transaction
            ProductName = $product
            Manufacturer = $manufacturer
            StartMenuFolder = $product
            ProductVersion = "1.2.3"
            MainBinaryName = "miho-desktop"
            TestOwnerRegistrySubKey = $testOwnerSubKey
        }

        $begin = @{} + $common
        $begin.Mode = "Begin"
        $begin.InstallRoot = $install
        $begin.StagingRoot = $staging
        $begin.CoordinatorPid = $PID
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $begin
        if ($receipt.schema -cne "miho-installer-begin-result-v1" -or $receipt.phase -cne "owner-registered") { throw "Begin receipt is invalid." }
        $journal = Get-Content -Raw -LiteralPath (Join-Path $transaction "installer-transaction-v1.json") | ConvertFrom-Json -ErrorAction Stop
        $startMenuRecord = @($journal.dynamic_files | Where-Object { $_.label -ceq "start-menu-shortcut" })
        $desktopRecord = @($journal.dynamic_files | Where-Object { $_.label -ceq "desktop-shortcut" })
        if ($startMenuRecord.Count -ne 1 -or $startMenuRecord[0].expected_after_present -ne $true -or
            $desktopRecord.Count -ne 1 -or $desktopRecord[0].expected_after_present -ne $false) {
            throw "Interactive shortcut policy was not captured exactly."
        }
        $recover = @{} + $common
        $recover.Mode = "Recover"
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $recover
        if ($receipt.terminal_phase -cne "rolled-back" -or (Test-Path -LiteralPath $transaction)) { throw "Begin recovery did not restore and finalize." }

        $beginNoShortcuts = @{} + $begin
        $beginNoShortcuts.NoShortcuts = $true
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $beginNoShortcuts
        $journal = Get-Content -Raw -LiteralPath (Join-Path $transaction "installer-transaction-v1.json") | ConvertFrom-Json -ErrorAction Stop
        if (@($journal.dynamic_files | Where-Object { $_.label -like "*-shortcut" -and $_.expected_after_present }).Count -ne 0) {
            throw "No-shortcuts policy still requires a shortcut."
        }
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $recover
        if ($receipt.terminal_phase -cne "rolled-back" -or (Test-Path -LiteralPath $transaction)) { throw "No-shortcuts recovery failed." }

        $beginDesktop = @{} + $begin
        $beginDesktop.CreateDesktopShortcut = $true
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $beginDesktop
        $journal = Get-Content -Raw -LiteralPath (Join-Path $transaction "installer-transaction-v1.json") | ConvertFrom-Json -ErrorAction Stop
        if (@($journal.dynamic_files | Where-Object { $_.label -like "*-shortcut" -and $_.expected_after_present }).Count -ne 2) {
            throw "Explicit desktop shortcut policy was not captured."
        }
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $recover
        if ($receipt.terminal_phase -cne "rolled-back" -or (Test-Path -LiteralPath $transaction)) { throw "Desktop-shortcut recovery failed." }

        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $begin
        $claim = @{} + $common
        $claim.Mode = "Claim"
        $claim.AutomationRoot = $automation
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $claim
        if (-not $receipt.claimed -or -not $receipt.claim_created_new_owner) { throw "Fresh installer claim receipt is invalid." }
        $apply = @{} + $common
        $apply.Mode = "ApplyStatic"
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $apply
        if (-not $receipt.applied -or -not (Test-Path -LiteralPath (Join-Path $install "miho.exe"))) { throw "Static apply failed." }
        $rollback = @{} + $common
        $rollback.Mode = "Rollback"
        $rollback.AutomationRoot = $automation
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $rollback
        if (-not $receipt.rolled_back -or (Test-Path -LiteralPath (Join-Path $install "miho.exe"))) { throw "Static rollback failed." }
        $finalize = @{} + $common
        $finalize.Mode = "Finalize"
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $finalize
        if ($receipt.cleanup_pending -or (Test-Path -LiteralPath $transaction)) { throw "Rollback finalization failed." }
        $ownerKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($testOwnerSubKey, $false)
        if ($null -ne $ownerKey) {
            try {
                if ($ownerKey.GetValueNames() -contains "AutomationOwnerInstanceIdV1") { throw "Rolled-back owner registry value remains." }
            }
            finally { $ownerKey.Dispose() }
        }

        # NSIS must distinguish an ordinary rollback (exit 0) from the case
        # where Commit crossed its durable boundary but its original host died
        # before reporting success (exit 10).  A terminal journal is enough to
        # exercise that narrow process contract without mutating a real task.
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $begin
        $committedOwner = [string]$receipt.owner_instance_id
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $claim
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $apply
        $journalPath = Join-Path $transaction "installer-transaction-v1.json"
        $journalText = [System.IO.File]::ReadAllText($journalPath, (New-Object System.Text.UTF8Encoding($false, $true)))
        $terminalText = $journalText.Replace('"phase":"static-applied"', '"phase":"committed"')
        if ($terminalText -ceq $journalText) { throw "Committed rollback exit fixture could not update the journal phase." }
        Write-Utf8NoBomV1 -LiteralPath $journalPath -Text $terminalText
        $rollbackTokens = New-Object System.Collections.ArrayList
        foreach ($name in $common.Keys) {
            $null = $rollbackTokens.Add("-$name")
            $null = $rollbackTokens.Add([string]$common[$name])
        }
        $null = $rollbackTokens.Add("-Mode")
        $null = $rollbackTokens.Add("Rollback")
        $terminalOutput = & $shell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $helper @rollbackTokens 2>&1
        if ($LASTEXITCODE -ne 10) { throw "Committed rollback signal used exit $LASTEXITCODE instead of 10: $($terminalOutput -join [Environment]::NewLine)" }
        $terminalReceipt = ($terminalOutput -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop
        if (-not $terminalReceipt.committed -or $terminalReceipt.rolled_back) { throw "Committed rollback signal receipt is invalid." }
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $recover
        if ($receipt.terminal_phase -cne "committed" -or (Test-Path -LiteralPath $transaction)) { throw "Committed rollback signal recovery did not finalize." }

        $verifyUninstall = @{} + $common
        $verifyUninstall.Mode = "VerifyUninstallStatic"
        $verifyUninstall.InstallRoot = $install
        $verifyUninstall.ExpectedOwnerInstanceId = $committedOwner
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $verifyUninstall
        if (-not $receipt.verified -or [int64]$receipt.file_count -ne 3) { throw "Static uninstall verification receipt is invalid." }
        [System.IO.File]::WriteAllBytes((Join-Path $install "miho.exe"), (New-Object byte[] 4097))
        $driftTokens = New-Object System.Collections.ArrayList
        foreach ($name in $verifyUninstall.Keys) {
            $null = $driftTokens.Add("-$name")
            $null = $driftTokens.Add([string]$verifyUninstall[$name])
        }
        $priorErrorPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $driftOutput = & $shell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $helper @driftTokens 2>&1
            $driftExit = $LASTEXITCODE
        }
        finally { $ErrorActionPreference = $priorErrorPreference }
        if ($driftExit -eq 0 -or ($driftOutput -join " ") -notmatch "missing, drifted, or unsafe|changed after uninstall began") {
            throw "Static uninstall accepted a drifted owned file."
        }
        Copy-Item -LiteralPath $payload -Destination (Join-Path $install "miho.exe") -Force -ErrorAction Stop
        [System.IO.File]::Delete((Join-Path $install "miho.exe"))
        $recoverTokens = New-Object System.Collections.ArrayList
        foreach ($name in $recover.Keys) {
            $null = $recoverTokens.Add("-$name")
            $null = $recoverTokens.Add([string]$recover[$name])
        }
        $priorErrorPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $recoverOutput = & $shell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $helper @recoverTokens 2>&1
            $recoverExit = $LASTEXITCODE
        }
        finally { $ErrorActionPreference = $priorErrorPreference }
        if ($recoverExit -eq 0 -or ($recoverOutput -join " ") -notmatch "must be resumed by uninstall.exe") {
            throw "A new install accepted an in-progress static uninstall journal."
        }
        $removeUninstall = @{} + $verifyUninstall
        $removeUninstall.Mode = "RemoveUninstallStatic"
        $installedHelper = Join-Path $install "installer\installer_transaction_v1.ps1"
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $installedHelper -Arguments $removeUninstall
        if (-not $receipt.removed -or (Test-Path -LiteralPath (Join-Path $install "miho.exe")) -or
            (Test-Path -LiteralPath (Join-Path $install "miho-static-ownership-v1.json")) -or
            (Test-Path -LiteralPath $installedHelper) -or
            (Test-Path -LiteralPath (Join-Path $install "installer\task_scheduler_v1.ps1"))) {
            throw "Static uninstall did not remove the exact ownership set."
        }
        if (-not (Test-Path -LiteralPath (Join-Path $transaction "uninstall-static-v1.json"))) {
            throw "Static uninstall did not retain its terminal recovery journal."
        }
        $finalizeUninstall = @{} + $common
        $finalizeUninstall.Mode = "FinalizeUninstallStatic"
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $finalizeUninstall
        if ($receipt.cleanup_pending -or (Test-Path -LiteralPath $transaction)) { throw "Static uninstall finalization failed." }
    }
    finally {
        Remove-Item Env:MIHO_INSTALLER_TRANSACTION_TEST_V1 -ErrorAction SilentlyContinue
        try { [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($testOwnerSubKey, $false) } catch { }
        $full = [System.IO.Path]::GetFullPath($temporary)
        $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
        if ($full.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $full)) {
            Remove-Item -LiteralPath $full -Recurse -Force -ErrorAction Stop
        }
    }
}

$installerTemplate = Get-Content -Raw -LiteralPath (Join-Path $root "crates\miho-desktop\src-tauri\installer.nsi")
$installerHooks = Get-Content -Raw -LiteralPath (Join-Path $root "crates\miho-desktop\src-tauri\nsis\installer-hooks.nsh")
$orderedMarkers = @(
    '!insertmacro MIHO_RUN_INSTALLER_HELPER "Recover"',
    '!insertmacro MIHO_RUN_INSTALLER_HELPER "Begin"',
    '!insertmacro MIHO_RUN_INSTALLER_HELPER "Claim"',
    '!insertmacro MIHO_RUN_INSTALLER_HELPER "ApplyStatic"',
    '!insertmacro MIHO_RUN_INSTALLER_HELPER "Prepare"',
    '!insertmacro MIHO_RUN_INSTALLER_HELPER "VerifyDynamic"',
    '!insertmacro MIHO_RUN_INSTALLER_HELPER "Commit"'
)
$previousIndex = -1
foreach ($marker in $orderedMarkers) {
    $index = $installerTemplate.IndexOf($marker, [System.StringComparison]::Ordinal)
    if ($index -le $previousIndex) { throw "NSIS installer transaction order is missing or invalid at '$marker'." }
    $previousIndex = $index
}
if ($installerTemplate -match 'miho-static-payload-backup' -or $installerTemplate -match 'Call MihoRollbackStaticPayload') {
    throw "NSIS still contains the volatile pre-transaction rollback path."
}
if ($installerHooks -match 'NSIS_HOOK_POSTINSTALL' -or $installerHooks -notmatch 'ExpectedOwnerInstanceId') {
    throw "NSIS hooks still use the single-call install path or an unbound uninstall owner."
}
if ($installerHooks -match '-File "\$INSTDIR\\installer' -or
    $installerHooks -notmatch [regex]::Escape('-File "$MihoUninstallHelper"') -or
    $installerHooks -notmatch [regex]::Escape('-File "$MihoUninstallWrapper"')) {
    throw "NSIS uninstall policy executes mutable installed scripts instead of embedded staged bytes."
}
if ($installerTemplate -notmatch [regex]::Escape('StrCmp $0 "${MIHO_INSTALLER_COMMITTED_EXIT}" miho_install_committed')) {
    throw "NSIS does not recover the terminal Commit handoff signal."
}

Write-Output "installer-transaction-tests: PASS"

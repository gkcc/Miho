[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$pwshCommandForModulePath = Get-Command "pwsh.exe" -ErrorAction SilentlyContinue
$foreignModuleRoot = if ($null -ne $pwshCommandForModulePath) {
    Join-Path (Split-Path -Parent $pwshCommandForModulePath.Source) "Modules"
}
else {
    Join-Path ([System.IO.Path]::GetTempPath()) "miho-no-foreign-powershell-modules-v1"
}
$windowsModuleRoot = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\Modules"
$script:MihoInstallerAdversarialModulePathV1 = $foreignModuleRoot + [System.IO.Path]::PathSeparator + $windowsModuleRoot

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
    # Reproduce NSIS launching Windows PowerShell 5.1 with a pwsh module tree
    # first. The foreign Microsoft.PowerShell.Utility shadows Get-FileHash,
    # while the Windows ScheduledTasks module remains intentionally available.
    $savedPsModulePath = $env:PSModulePath
    try {
        $env:PSModulePath = $script:MihoInstallerAdversarialModulePathV1
        $output = & $Shell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Helper @tokens 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $env:PSModulePath = $savedPsModulePath
    }
    if ($exitCode -ne 0) { throw "Installer helper failed ($exitCode): $($output -join [Environment]::NewLine)" }
    try { return (($output -join [Environment]::NewLine) | ConvertFrom-Json -ErrorAction Stop) }
    catch { throw "Installer helper returned invalid JSON: $($output -join [Environment]::NewLine)" }
}

function Invoke-InstallerHelperFailureV1 {
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
    $savedPsModulePath = $env:PSModulePath
    $savedErrorPreference = $ErrorActionPreference
    try {
        $env:PSModulePath = $script:MihoInstallerAdversarialModulePathV1
        $ErrorActionPreference = "Continue"
        $output = & $Shell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Helper @tokens 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $savedErrorPreference
        $env:PSModulePath = $savedPsModulePath
    }
    return [pscustomobject][ordered]@{ ExitCode = $exitCode; Output = ($output -join [Environment]::NewLine) }
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
    $productRegistrySubKey = "Software\$manufacturer\$product"
    $uninstallRegistrySubKey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\$product"
    $programs = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::StartMenu)) "Programs"
    $rootStartMenuShortcut = Join-Path $programs ($product + ".lnk")
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

        # Tauri renders an empty STARTMENUFOLDER as a shortcut directly under
        # Programs. Windows deletes empty environment values, so the NSIS root
        # marker must override the helper's product-folder default. Exercise
        # the real VerifyDynamic boundary, including its durable failure receipt.
        $dynamicCommon = @{} + $common
        $dynamicCommon.Remove("StartMenuFolder")
        $dynamicCommon.MainBinaryName = "miho"
        $failureReceipt = Join-Path $temporary "installer-last-failure-v1.json"
        $dynamicCommon.FailureReceiptPath = $failureReceipt
        $dynamicBegin = @{} + $dynamicCommon
        $dynamicBegin.Mode = "Begin"
        $dynamicBegin.InstallRoot = $install
        $dynamicBegin.StagingRoot = $staging
        $dynamicBegin.CoordinatorPid = $PID
        # Real upgrades capture present product/uninstall trees. Keep a nested,
        # typed canary before-image so rollback must recreate values and ACLs,
        # not merely delete keys that were absent at Begin.
        $productBefore = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($productRegistrySubKey, $true)
        try {
            $productBefore.SetValue("", "before-product", [Microsoft.Win32.RegistryValueKind]::String)
            $nestedBefore = $productBefore.CreateSubKey("Nested", $true)
            try { $nestedBefore.SetValue("Canary", [int64]42, [Microsoft.Win32.RegistryValueKind]::QWord); $nestedBefore.Flush() }
            finally { $nestedBefore.Dispose() }
            $productBefore.Flush()
        }
        finally { $productBefore.Dispose() }
        $uninstallBefore = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($uninstallRegistrySubKey, $true)
        try { $uninstallBefore.SetValue("BeforeCanary", "preserve", [Microsoft.Win32.RegistryValueKind]::String); $uninstallBefore.Flush() }
        finally { $uninstallBefore.Dispose() }
        $savedRootMarker = $env:MIHO_INSTALLER_START_MENU_ROOT_V1
        $savedStartMenu = $env:MIHO_INSTALLER_START_MENU_V1
        try {
            $env:MIHO_INSTALLER_START_MENU_ROOT_V1 = "1"
            Remove-Item Env:MIHO_INSTALLER_START_MENU_V1 -ErrorAction SilentlyContinue
            $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $dynamicBegin
        }
        finally {
            if ($null -eq $savedRootMarker) { Remove-Item Env:MIHO_INSTALLER_START_MENU_ROOT_V1 -ErrorAction SilentlyContinue }
            else { $env:MIHO_INSTALLER_START_MENU_ROOT_V1 = $savedRootMarker }
            if ($null -eq $savedStartMenu) { Remove-Item Env:MIHO_INSTALLER_START_MENU_V1 -ErrorAction SilentlyContinue }
            else { $env:MIHO_INSTALLER_START_MENU_V1 = $savedStartMenu }
        }
        $journalPath = Join-Path $transaction "installer-transaction-v1.json"
        $journal = Get-Content -Raw -LiteralPath $journalPath | ConvertFrom-Json -ErrorAction Stop
        $dynamicTransactionId = [string]$journal.transaction_id
        $rootRecord = @($journal.dynamic_files | Where-Object { $_.label -ceq "start-menu-shortcut" })
        if ($rootRecord.Count -ne 1 -or $rootRecord[0].path -cne $rootStartMenuShortcut -or -not $rootRecord[0].expected_after_present) {
            throw "Explicit root-of-Programs shortcut policy was not captured."
        }
        $dynamicClaim = @{} + $dynamicCommon
        $dynamicClaim.Mode = "Claim"
        $dynamicClaim.AutomationRoot = $automation
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $dynamicClaim
        $dynamicApply = @{} + $dynamicCommon
        $dynamicApply.Mode = "ApplyStatic"
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $dynamicApply
        [System.IO.File]::WriteAllBytes((Join-Path $install "uninstall.exe"), (New-Object byte[] 4096))
        $productKey = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($productRegistrySubKey, $true)
        try { $productKey.SetValue("", $install, [Microsoft.Win32.RegistryValueKind]::String); $productKey.Flush() }
        finally { $productKey.Dispose() }
        $uninstallKey = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($uninstallRegistrySubKey, $true)
        try {
            $uninstallKey.SetValue("DisplayName", $product, [Microsoft.Win32.RegistryValueKind]::String)
            $uninstallKey.SetValue("DisplayVersion", "1.2.3", [Microsoft.Win32.RegistryValueKind]::String)
            $uninstallKey.SetValue("Publisher", $manufacturer, [Microsoft.Win32.RegistryValueKind]::String)
            $uninstallKey.SetValue("MainBinaryName", "miho.exe", [Microsoft.Win32.RegistryValueKind]::String)
            $uninstallKey.SetValue("DisplayIcon", ('"' + (Join-Path $install "miho.exe") + '"'), [Microsoft.Win32.RegistryValueKind]::String)
            $uninstallKey.SetValue("InstallLocation", ('"' + $install + '"'), [Microsoft.Win32.RegistryValueKind]::String)
            $uninstallKey.SetValue("UninstallString", ('"' + (Join-Path $install "uninstall.exe") + '"'), [Microsoft.Win32.RegistryValueKind]::String)
            $uninstallKey.SetValue("NoModify", 1, [Microsoft.Win32.RegistryValueKind]::DWord)
            $uninstallKey.SetValue("NoRepair", 1, [Microsoft.Win32.RegistryValueKind]::DWord)
            $uninstallKey.SetValue("EstimatedSize", 1, [Microsoft.Win32.RegistryValueKind]::DWord)
            $uninstallKey.Flush()
        }
        finally { $uninstallKey.Dispose() }
        $journal = Get-Content -Raw -LiteralPath $journalPath | ConvertFrom-Json -ErrorAction Stop
        $journal.phase = "prepared"
        Write-Utf8NoBomV1 -LiteralPath $journalPath -Text (($journal | ConvertTo-Json -Depth 20 -Compress) + "`n")
        $dynamicVerify = @{} + $dynamicCommon
        $dynamicVerify.Mode = "VerifyDynamic"
        $failedVerify = Invoke-InstallerHelperFailureV1 -Shell $shell -Helper $helper -Arguments $dynamicVerify
        if ($failedVerify.ExitCode -eq 0 -or $failedVerify.Output -notmatch [regex]::Escape("Required installer dynamic file 'start-menu-shortcut' is missing.")) {
            throw "VerifyDynamic did not reject the missing root Start Menu shortcut precisely: $($failedVerify.Output)"
        }
        $failure = Get-Content -Raw -LiteralPath $failureReceipt | ConvertFrom-Json -ErrorAction Stop
        if ($failure.schema_version -cne "miho-installer-failure-v1" -or $failure.mode -cne "VerifyDynamic" -or
            $failure.phase -cne "prepared" -or $failure.transaction_id -cne $dynamicTransactionId -or
            $failure.error_message -cne "Required installer dynamic file 'start-menu-shortcut' is missing.") {
            throw "VerifyDynamic failure receipt is missing or imprecise."
        }
        $shellObject = New-Object -ComObject WScript.Shell
        $shortcut = $shellObject.CreateShortcut($rootStartMenuShortcut)
        $shortcut.TargetPath = Join-Path $install "miho.exe"
        $shortcut.WorkingDirectory = $staging
        $shortcut.Save()
        $failedWorkingDirectory = Invoke-InstallerHelperFailureV1 -Shell $shell -Helper $helper -Arguments $dynamicVerify
        if ($failedWorkingDirectory.ExitCode -eq 0 -or
            $failedWorkingDirectory.Output -notmatch [regex]::Escape("Installer shortcut target or working directory is invalid.")) {
            throw "VerifyDynamic accepted a shortcut bound to volatile staging: $($failedWorkingDirectory.Output)"
        }
        $failure = Get-Content -Raw -LiteralPath $failureReceipt | ConvertFrom-Json -ErrorAction Stop
        if ($failure.error_message -cne "Installer shortcut target or working directory is invalid.") {
            throw "VerifyDynamic did not persist the invalid WorkingDirectory failure."
        }
        $shortcut = $shellObject.CreateShortcut($rootStartMenuShortcut)
        $shortcut.TargetPath = Join-Path $install "miho.exe"
        $shortcut.WorkingDirectory = $install
        $shortcut.Save()
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $dynamicVerify
        if (-not $receipt.verified) { throw "Root Start Menu VerifyDynamic fixture did not verify." }
        $journal = Get-Content -Raw -LiteralPath $journalPath | ConvertFrom-Json -ErrorAction Stop
        $rootRecord = @($journal.dynamic_files | Where-Object { $_.label -ceq "start-menu-shortcut" })
        if ($rootRecord.Count -ne 1 -or -not $rootRecord[0].after_captured -or [int64]$rootRecord[0].after_size -le 0) {
            throw "VerifyDynamic did not capture the root Start Menu shortcut."
        }
        $dynamicRollback = @{} + $dynamicCommon
        $dynamicRollback.Mode = "Rollback"
        $dynamicRollback.AutomationRoot = $automation
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $dynamicRollback
        $dynamicFinalize = @{} + $dynamicCommon
        $dynamicFinalize.Mode = "Finalize"
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $dynamicFinalize
        $productKeyAfter = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($productRegistrySubKey, $false)
        $uninstallKeyAfter = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($uninstallRegistrySubKey, $false)
        try {
            if ((Test-Path -LiteralPath $transaction) -or (Test-Path -LiteralPath $install) -or
                (Test-Path -LiteralPath $rootStartMenuShortcut) -or $null -eq $productKeyAfter -or $null -eq $uninstallKeyAfter -or
                [string]$productKeyAfter.GetValue("", "") -cne "before-product" -or
                [string]$uninstallKeyAfter.GetValue("BeforeCanary", "") -cne "preserve") {
                throw "VerifyDynamic rollback did not restore its exact before-image."
            }
            $nestedAfter = $productKeyAfter.OpenSubKey("Nested", $false)
            try {
                if ($null -eq $nestedAfter -or $nestedAfter.GetValueKind("Canary") -ne [Microsoft.Win32.RegistryValueKind]::QWord -or
                    [int64]$nestedAfter.GetValue("Canary", 0) -ne 42) {
                    throw "VerifyDynamic rollback did not restore its nested typed registry before-image."
                }
            }
            finally { if ($null -ne $nestedAfter) { $nestedAfter.Dispose() } }
        }
        finally {
            if ($null -ne $productKeyAfter) { $productKeyAfter.Dispose() }
            if ($null -ne $uninstallKeyAfter) { $uninstallKeyAfter.Dispose() }
        }
        [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($productRegistrySubKey, $false)
        [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($uninstallRegistrySubKey, $false)

        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $begin
        $journal = Get-Content -Raw -LiteralPath (Join-Path $transaction "installer-transaction-v1.json") | ConvertFrom-Json -ErrorAction Stop
        if ($journal.install_root_was_present -ne $false) { throw "Fresh install root presence was not journaled exactly." }
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
        if (-not $receipt.rolled_back -or (Test-Path -LiteralPath $install)) { throw "Fresh static rollback did not remove the installer-created empty root." }
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

        [System.IO.Directory]::CreateDirectory($install) | Out-Null
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $begin
        $journalPath = Join-Path $transaction "installer-transaction-v1.json"
        $journal = Get-Content -Raw -LiteralPath $journalPath | ConvertFrom-Json -ErrorAction Stop
        if ($journal.install_root_was_present -ne $true) { throw "Pre-existing install root presence was not journaled exactly." }
        $journal.PSObject.Properties.Remove("install_root_was_present")
        Write-Utf8NoBomV1 -LiteralPath $journalPath -Text (($journal | ConvertTo-Json -Depth 20 -Compress) + "`n")
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $claim
        $journal = Get-Content -Raw -LiteralPath $journalPath | ConvertFrom-Json -ErrorAction Stop
        if ($journal.install_root_was_present -ne $true) { throw "Legacy journal migration did not conservatively preserve the install root." }
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $apply
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $rollback
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $finalize
        if (-not (Test-Path -LiteralPath $install -PathType Container) -or
            @(Get-ChildItem -LiteralPath $install -Force -ErrorAction Stop).Count -ne 0) {
            throw "Rollback removed or changed a pre-existing empty install root."
        }
        Remove-Item -LiteralPath $install -Force -ErrorAction Stop

        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $begin
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $claim
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $apply
        $userFile = Join-Path $install "user-created-during-install.txt"
        Write-Utf8NoBomV1 -LiteralPath $userFile -Text "preserve-me"
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $rollback
        $receipt = Invoke-InstallerHelperV1 -Shell $shell -Helper $helper -Arguments $finalize
        if (-not (Test-Path -LiteralPath $userFile -PathType Leaf) -or
            [System.IO.File]::ReadAllText($userFile) -cne "preserve-me" -or
            (Test-Path -LiteralPath (Join-Path $install "miho.exe"))) {
            throw "Rollback did not preserve a non-empty fresh install root while removing owned bytes."
        }
        Remove-Item -LiteralPath $userFile -Force -ErrorAction Stop
        Remove-Item -LiteralPath $install -Force -ErrorAction Stop

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
        try { [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree(("Software\" + $manufacturer), $false) } catch { }
        try { [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($uninstallRegistrySubKey, $false) } catch { }
        if (Test-Path -LiteralPath $rootStartMenuShortcut -PathType Leaf) {
            Remove-Item -LiteralPath $rootStartMenuShortcut -Force -ErrorAction SilentlyContinue
        }
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
if ($installerTemplate -notmatch 'MIHO_INSTALLER_START_MENU_ROOT_V1' -or
    $installerTemplate -notmatch 'MIHO_INSTALLER_FAILURE_RECEIPT_V1' -or
    $installerTemplate -notmatch 'installer-last-failure-v1\.json') {
    throw "NSIS does not preserve the root Start Menu policy or a durable helper failure receipt."
}
if ($installerTemplate -notmatch '(?s)Function CreateOrUpdateStartMenuShortcut.*?SetOutPath "\$INSTDIR".*?CreateShortcut' -or
    $installerTemplate -notmatch '(?s)Function CreateOrUpdateDesktopShortcut.*?SetOutPath "\$INSTDIR".*?CreateShortcut') {
    throw "NSIS shortcuts do not bind their WorkingDirectory to the durable install root."
}
$uninstallStart = $installerTemplate.IndexOf("Section Uninstall", [System.StringComparison]::Ordinal)
$uninstallEnd = $installerTemplate.IndexOf("SectionEnd", $uninstallStart, [System.StringComparison]::Ordinal)
if ($uninstallStart -lt 0 -or $uninstallEnd -le $uninstallStart) { throw "NSIS uninstall section is unavailable." }
$uninstallSection = $installerTemplate.Substring($uninstallStart, $uninstallEnd - $uninstallStart)
$productRegistryDelete = $uninstallSection.IndexOf('DeleteRegKey SHCTX "${MANUPRODUCTKEY}"', [System.StringComparison]::Ordinal)
if ($productRegistryDelete -lt 0) {
    throw "NSIS does not remove installer-owned product registry metadata."
}
if ($installerTemplate -match 'DeleteAppDataCheckbox|\$\(deleteAppData\)' -or
    $uninstallSection -match '(?i)RmDir\s+/r\s+"\$(?:APPDATA|LOCALAPPDATA)\\\$\{BUNDLEID\}"' -or
    $installerHooks -match 'DeleteAppDataCheckbox') {
    throw "NSIS still exposes or executes recursive AppData deletion despite the preserve-user-data contract."
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
if (-not $installerTemplate.Contains('Var MihoInstalledVersionComparison') -or
    -not $installerTemplate.Contains('StrCpy $MihoInstalledVersionComparison ""') -or
    -not $installerTemplate.Contains('ReadRegStr $R1 SHCTX "${UNINSTKEY}" "DisplayVersion"') -or
    -not $installerTemplate.Contains('Pop $MihoInstalledVersionComparison') -or
    -not $installerTemplate.Contains('${If} $MihoInstalledVersionComparison = -1') -or
    $installerTemplate.Contains('${If} $R0 = -1')) {
    throw "NSIS silent clean-install downgrade detection still depends on a stale scratch register."
}
if ($installerTemplate -match 'System::Call[^\r\n]*\brR[0-9]\b' -or
    $installerHooks -match 'System::Call[^\r\n]*\brR[0-9]\b' -or
    -not $installerTemplate.Contains('GetCurrentProcessId() i.R5') -or
    @([regex]::Matches($installerTemplate, 'SetEnvironmentVariableW[^\r\n]*i\.R9')).Count -ne 2 -or
    @([regex]::Matches($installerTemplate, 'SetEnvironmentVariableW[^\r\n]*p 0\) i\.R9')).Count -ne 1 -or
    @([regex]::Matches($installerHooks, 'SetEnvironmentVariableW[^\r\n]*i\.R9')).Count -ne 3) {
    throw "NSIS installer/uninstaller System calls use a register token that does not match the referenced `$R register."
}

Write-Output "installer-transaction-tests: PASS"

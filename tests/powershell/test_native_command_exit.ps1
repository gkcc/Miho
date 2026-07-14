param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$helper = Join-Path $root "scripts\native_command.ps1"
. $helper

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        throw $Message
    }
}

$updateScript = Get-Content -LiteralPath (Join-Path $root "scripts\update_endgame_data.ps1") -Raw
Assert-True ($updateScript -match 'Invoke-NativeCommand\s+-FilePath\s+\$cli') "The updater is not wired through the guarded native runner"
Assert-True ($updateScript -match '"update",\s*"run"') "The updater does not delegate to the single Rust runner"
Assert-True ($updateScript -notmatch '(?i)python|Update-DateMarker|Set-StateEntry') "The updater still contains legacy Python or freshness business logic"

$buildScript = Get-Content -LiteralPath (Join-Path $root "scripts\build_rust_app.ps1") -Raw
Assert-True (([regex]::Matches($buildScript, 'Invoke-NativeCommand\s+-FilePath')).Count -ge 5) "Not every release/build command is guarded"
Assert-True ($buildScript -match 'cargo.*build.*--locked.*--release.*miho-cli') "The release build does not produce the native update CLI"
Assert-True ($buildScript -match 'Resolve-SafeFileV1\s+-LiteralPath\s+\(Join-Path\s+\$tauriTarget\s+"release\\miho\.exe"\)') "The release build does not verify the isolated native CLI artifact"
Assert-True ($buildScript -notmatch '&\s+\$node') "The desktop build still contains an unguarded Node invocation"
Assert-True ($buildScript -notmatch '(?m)^\s*cargo\s+') "The desktop build still contains an unguarded Cargo invocation"

$continued = $false
Invoke-NativeCommand -FilePath $env:ComSpec -ArgumentList @("/d", "/c", "exit 0")
$continued = $true
Assert-True $continued "A zero native exit code did not continue execution"

function Test-PowerShell7NativePreferenceHandling {
    if ($PSVersionTable.PSVersion.Major -lt 7) {
        return
    }

    $ErrorActionPreference = "Stop"
    $PSNativeCommandUseErrorActionPreference = $true

    Invoke-NativeCommand -FilePath $env:ComSpec -ArgumentList @("/d", "/c", "exit 0")
    Assert-True ($LASTEXITCODE -eq 0) "A successful guarded call did not retain native exit code 0"
    Assert-True ($ErrorActionPreference -eq "Stop") "A successful guarded call changed the caller EAP"
    Assert-True $PSNativeCommandUseErrorActionPreference "A successful guarded call changed the caller native error preference"

    foreach ($expected in @(2, 7)) {
        $threwTypedFailure = $false
        try {
            Invoke-NativeCommand `
                -FilePath $env:ComSpec `
                -ArgumentList @("/d", "/c", "exit $expected") `
                -FailureMessage "PowerShell 7 sentinel failed"
        }
        catch {
            $threwTypedFailure = $true
            Assert-True ($_.Exception.GetType() -eq [System.Exception]) "PowerShell replaced native exit $expected with $($_.Exception.GetType().FullName)"
            Assert-True ($_.Exception.Data["NativeExitCode"] -eq $expected) "The guarded call did not retain native exit $expected"
            Assert-True ($LASTEXITCODE -eq $expected) "LASTEXITCODE did not reflect native exit $expected"
        }
        Assert-True $threwTypedFailure "Native exit $expected did not produce the guarded typed failure"
        Assert-True ($ErrorActionPreference -eq "Stop") "Native exit $expected changed the caller EAP"
        Assert-True $PSNativeCommandUseErrorActionPreference "Native exit $expected changed the caller native error preference"
    }

    $ErrorActionPreference = "Continue"
    $missingExecutable = Join-Path ([System.IO.Path]::GetTempPath()) ("miho-missing-{0}.exe" -f [guid]::NewGuid().ToString("N"))
    $threwLaunchError = $false
    try {
        Invoke-NativeCommand -FilePath $missingExecutable
    }
    catch {
        $threwLaunchError = $true
        Assert-True ($_.Exception -is [System.Management.Automation.CommandNotFoundException]) "A real launch error lost its CommandNotFoundException identity"
        Assert-True (-not $_.Exception.Data.Contains("NativeExitCode")) "A real launch error was mislabeled as a native exit failure"
    }
    Assert-True $threwLaunchError "A missing executable was swallowed when the caller EAP was Continue"
    Assert-True ($ErrorActionPreference -eq "Continue") "A launch error changed the caller EAP"
    Assert-True $PSNativeCommandUseErrorActionPreference "A launch error changed the caller native error preference"

    $invalidExecutable = Join-Path ([System.IO.Path]::GetTempPath()) ("miho-invalid-{0}.exe" -f [guid]::NewGuid().ToString("N"))
    try {
        "not an executable" | Set-Content -LiteralPath $invalidExecutable -Encoding ASCII
        $threwProcessStartError = $false
        try {
            Invoke-NativeCommand -FilePath $invalidExecutable
        }
        catch {
            $threwProcessStartError = $true
            Assert-True ($_.Exception -is [System.Management.Automation.ApplicationFailedException]) "A process-start error lost its ApplicationFailedException identity"
            Assert-True (-not $_.Exception.Data.Contains("NativeExitCode")) "A process-start error was mislabeled as a native exit failure"
        }
        Assert-True $threwProcessStartError "An invalid executable launch was swallowed when the caller EAP was Continue"
        Assert-True ($ErrorActionPreference -eq "Continue") "A process-start error changed the caller EAP"
        Assert-True $PSNativeCommandUseErrorActionPreference "A process-start error changed the caller native error preference"
    }
    finally {
        Remove-Item -LiteralPath $invalidExecutable -Force -ErrorAction SilentlyContinue
    }
}

function Test-NativePreferenceAbsenceDoesNotLeak {
    Remove-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Local -ErrorAction SilentlyContinue
    $preferenceBefore = Get-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Local -ErrorAction SilentlyContinue
    Invoke-NativeCommand -FilePath $env:ComSpec -ArgumentList @("/d", "/c", "exit 0")
    $preferenceAfter = Get-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Local -ErrorAction SilentlyContinue
    Assert-True ($null -eq $preferenceBefore -and $null -eq $preferenceAfter) "The guarded call leaked a native error preference into its caller scope"
}

Test-PowerShell7NativePreferenceHandling
Test-NativePreferenceAbsenceDoesNotLeak

$singleCommand = Join-Path ([System.IO.Path]::GetTempPath()) ("miho-single-command-{0}.cmd" -f [guid]::NewGuid().ToString("N"))
try {
    "@exit /b 0" | Set-Content -LiteralPath $singleCommand -Encoding ASCII
    Invoke-NativeCommandLine -Command @($singleCommand)
}
finally {
    Remove-Item -LiteralPath $singleCommand -Force -ErrorAction SilentlyContinue
}

$threw = $false
try {
    Invoke-NativeCommand -FilePath $env:ComSpec -ArgumentList @("/d", "/c", "exit 7") -FailureMessage "sentinel failed"
}
catch {
    $threw = $true
    Assert-True ($_.Exception.Message -like "*exit code 7*") "The thrown error did not preserve exit code 7"
    Assert-True ($_.Exception.Data["NativeExitCode"] -eq 7) "The typed native failure did not retain exit code 7"
}
Assert-True $threw "Native exit code 7 did not terminate the guarded call"

$tempScript = Join-Path ([System.IO.Path]::GetTempPath()) ("miho-native-exit-{0}.ps1" -f [guid]::NewGuid().ToString("N"))
try {
    $escapedHelper = $helper.Replace("'", "''")
    @(
        '$ErrorActionPreference = "Stop"'
        ". '$escapedHelper'"
        'Invoke-NativeCommand -FilePath $env:ComSpec -ArgumentList @("/d", "/c", "exit 7")'
    ) | Set-Content -LiteralPath $tempScript -Encoding UTF8

    $windowsPowerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $windowsPowerShell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $tempScript *> $null
        $outerExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    Assert-True ($outerExitCode -ne 0) "An uncaught native exit code 7 produced a successful outer PowerShell exit"
}
finally {
    Remove-Item -LiteralPath $tempScript -Force -ErrorAction SilentlyContinue
}

$fakeCli = Join-Path ([System.IO.Path]::GetTempPath()) ("miho-fake-cli-{0}.cmd" -f [guid]::NewGuid().ToString("N"))
$powerShell7Launcher = Join-Path ([System.IO.Path]::GetTempPath()) ("miho-pwsh7-launcher-{0}.ps1" -f [guid]::NewGuid().ToString("N"))
try {
    '@exit /b %MIHO_FAKE_EXIT%' | Set-Content -LiteralPath $fakeCli -Encoding ASCII
    $escapedUpdateScript = (Join-Path $root "scripts\update_endgame_data.ps1").Replace("'", "''")
    $escapedRoot = $root.Replace("'", "''")
    @(
        '$ErrorActionPreference = "Stop"'
        '$PSNativeCommandUseErrorActionPreference = $true'
        "& '$escapedUpdateScript' -Root '$escapedRoot'"
        'exit $LASTEXITCODE'
    ) | Set-Content -LiteralPath $powerShell7Launcher -Encoding UTF8
    $oldCliPath = $env:MIHO_CLI_PATH
    $oldFakeExit = $env:MIHO_FAKE_EXIT
    $env:MIHO_CLI_PATH = $fakeCli
    foreach ($expected in @(7, 2)) {
        $env:MIHO_FAKE_EXIT = [string]$expected
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & $windowsPowerShell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
                -File (Join-Path $root "scripts\update_endgame_data.ps1") -Root $root *> $null
            $launcherExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        Assert-True ($launcherExitCode -eq $expected) "The compatibility launcher changed native exit $expected into $launcherExitCode"

        $powerShell7 = (Get-Command pwsh.exe -ErrorAction Stop).Source
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & $powerShell7 -NoLogo -NoProfile -NonInteractive -File $powerShell7Launcher *> $null
            $powerShell7ExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        Assert-True ($powerShell7ExitCode -eq $expected) "PowerShell 7 changed native exit $expected into $powerShell7ExitCode when native EAP handling was enabled"
    }
}
finally {
    $env:MIHO_CLI_PATH = $oldCliPath
    $env:MIHO_FAKE_EXIT = $oldFakeExit
    Remove-Item -LiteralPath $fakeCli -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $powerShell7Launcher -Force -ErrorAction SilentlyContinue
}

Write-Host "native command exit regression: PASS"

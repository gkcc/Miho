$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$script = Join-Path $root "scripts\verify_gui_render_v1.ps1"
$previousDefineOnly = $env:MIHO_GUI_RENDER_TEST_DEFINE_ONLY_V1
$env:MIHO_GUI_RENDER_TEST_DEFINE_ONLY_V1 = "1"
try {
    . $script -Executable "unused-by-define-only"
}
finally {
    $env:MIHO_GUI_RENDER_TEST_DEFINE_ONLY_V1 = $previousDefineOnly
}

$hashFixture = Join-Path ([System.IO.Path]::GetTempPath()) ("miho-gui-hash-" + [guid]::NewGuid().ToString("N"))
try {
    [System.IO.File]::WriteAllBytes($hashFixture, [System.Text.Encoding]::UTF8.GetBytes("abc"))
    if ((Get-MihoProbeFileSha256V1 -LiteralPath $hashFixture) -cne
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad") {
        throw "GUI render receipt SHA-256 no longer matches the executable bytes"
    }
}
finally {
    if ([System.IO.File]::Exists($hashFixture)) {
        [System.IO.File]::Delete($hashFixture)
    }
}

$valid = [pscustomobject]@{
    type = "page"
    title = "MIHO"
    url = "https://tauri.localhost/#miho-app-ready-v1"
}
if (-not (Test-MihoRenderedTargetV1 -Target $valid)) {
    throw "GUI render contract rejected the production target"
}

$invalid = @(
    [pscustomobject]@{ type = "page"; title = "file not found"; url = "chrome-error://chromewebdata/" },
    [pscustomobject]@{ type = "page"; title = "MIHO"; url = "file:///missing/index.html" },
    [pscustomobject]@{ type = "page"; title = "MIHO"; url = "http://127.0.0.1:5173/" },
    [pscustomobject]@{ type = "page"; title = "MIHO"; url = "https://tauri.localhost/" },
    [pscustomobject]@{ type = "iframe"; title = "MIHO"; url = "https://tauri.localhost/#miho-app-ready-v1" }
)
foreach ($target in $invalid) {
    if (Test-MihoRenderedTargetV1 -Target $target) {
        throw "GUI render contract accepted an invalid target: $($target | ConvertTo-Json -Compress)"
    }
}

$validDom = [pscustomobject]@{
    href = "https://tauri.localhost/#miho-app-ready-v1"
    readyState = "complete"
    ready = "v1"
    brandText = "MIHO ENDGAME"
    appChildCount = 2
    visualizerLoaded = $true
    tauriInternals = $true
    bodyText = "MIHO ENDGAME workspace"
    neterror = $false
}
if (-not (Test-MihoRenderedDomV1 -Dom $validDom)) {
    throw "GUI render contract rejected the production DOM"
}
$invalidDom = @(
    [pscustomobject]@{ href = "chrome-error://chromewebdata/"; readyState = "complete"; ready = "v1"; brandText = "MIHO ENDGAME"; appChildCount = 2; visualizerLoaded = $true; tauriInternals = $true; bodyText = "ERR_FILE_NOT_FOUND"; neterror = $true },
    [pscustomobject]@{ href = "https://tauri.localhost/#miho-app-ready-v1"; readyState = "complete"; ready = ""; brandText = "MIHO ENDGAME"; appChildCount = 2; visualizerLoaded = $true; tauriInternals = $true; bodyText = "workspace"; neterror = $false },
    [pscustomobject]@{ href = "https://tauri.localhost/#miho-app-ready-v1"; readyState = "complete"; ready = "v1"; brandText = ""; appChildCount = 0; visualizerLoaded = $true; tauriInternals = $true; bodyText = "workspace"; neterror = $false },
    [pscustomobject]@{ href = "https://tauri.localhost/#miho-app-ready-v1"; readyState = "complete"; ready = "v1"; brandText = "MIHO ENDGAME"; appChildCount = 2; visualizerLoaded = $false; tauriInternals = $true; bodyText = "workspace"; neterror = $false },
    [pscustomobject]@{ href = "https://tauri.localhost/#miho-app-ready-v1"; readyState = "complete"; ready = "v1"; brandText = "MIHO ENDGAME"; appChildCount = 2; visualizerLoaded = $true; tauriInternals = $false; bodyText = "workspace"; neterror = $false },
    [pscustomobject]@{ href = "https://tauri.localhost/#miho-app-ready-v1"; readyState = "complete"; ready = "v1"; brandText = "MIHO ENDGAME"; appChildCount = 2; visualizerLoaded = $true; tauriInternals = $true; bodyText = "Microsoft Edge ERR_FILE_NOT_FOUND"; neterror = $false }
)
foreach ($dom in $invalidDom) {
    if (Test-MihoRenderedDomV1 -Dom $dom) {
        throw "GUI render contract accepted an invalid DOM: $($dom | ConvertTo-Json -Compress)"
    }
}
if (-not (Test-MihoProcessStartsWithinProbeV1 -ProcessStartTicks 100 -RootStartTicks 100) -or
    -not (Test-MihoProcessStartsWithinProbeV1 -ProcessStartTicks 101 -RootStartTicks 100) -or
    (Test-MihoProcessStartsWithinProbeV1 -ProcessStartTicks 99 -RootStartTicks 100) -or
    (Test-MihoProcessStartsWithinProbeV1 -ProcessStartTicks 100 -RootStartTicks 0)) {
    throw "GUI render process ownership contract accepts a pre-existing or unbounded PID identity"
}

$expectedUserData = "C:\fixture path\EBWebView"
$validUserDataCommands = @(
    '"C:\Program Files\WebView2\msedgewebview2.exe" --user-data-dir="C:\fixture path\EBWebView" --remote-debugging-port=1234',
    'C:\WebView2\msedgewebview2.exe --user-data-dir=C:\fixture\EBWebView --remote-debugging-port=1234'
)
$validUserDataExpected = @($expectedUserData, "C:\fixture\EBWebView")
for ($index = 0; $index -lt $validUserDataCommands.Count; $index += 1) {
    $resolved = Resolve-MihoWebViewUserDataDirectoryArgumentV1 `
        -CommandLine $validUserDataCommands[$index]
    if (-not [string]::Equals(
            $resolved,
            $validUserDataExpected[$index],
            [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "GUI render user-data-dir parser changed a valid browser path"
    }
}
$invalidUserDataCommands = @(
    'msedgewebview2.exe --remote-debugging-port=1234',
    'msedgewebview2.exe --user-data-dir=relative\EBWebView --remote-debugging-port=1234',
    'msedgewebview2.exe --user-data-dir=C:\one --user-data-dir=C:\two --remote-debugging-port=1234',
    'msedgewebview2.exe --user-data-dir="" --remote-debugging-port=1234'
)
foreach ($commandLine in $invalidUserDataCommands) {
    $rejected = $false
    try { $null = Resolve-MihoWebViewUserDataDirectoryArgumentV1 -CommandLine $commandLine }
    catch { $rejected = $true }
    if (-not $rejected) {
        throw "GUI render user-data-dir parser accepted an invalid browser command line: $commandLine"
    }
}
$validBrowserSnapshot = [pscustomobject]@{
    process_name = "msedgewebview2"
    command_line = $validUserDataCommands[0]
}
$boundUserData = Assert-MihoBoundWebViewUserDataDirectoryV1 `
    -BrowserSnapshots @($validBrowserSnapshot) `
    -ExpectedDirectory $expectedUserData
if (-not [string]::Equals(
        $boundUserData,
        $expectedUserData,
        [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "GUI render browser binding changed the expected user-data directory"
}
$escapedBrowserSnapshot = [pscustomobject]@{
    process_name = "msedgewebview2"
    command_line = 'msedgewebview2.exe --user-data-dir="C:\external\EBWebView" --remote-debugging-port=1234'
}
$escapedRejected = $false
try {
    $null = Assert-MihoBoundWebViewUserDataDirectoryV1 `
        -BrowserSnapshots @($escapedBrowserSnapshot) `
        -ExpectedDirectory $expectedUserData
}
catch { $escapedRejected = $true }
if (-not $escapedRejected) {
    throw "GUI render browser binding accepted an external user-data directory"
}
$environmentInfo = [System.Diagnostics.ProcessStartInfo]::new()
$environmentInfo.EnvironmentVariables["WEBVIEW2_USER_DATA_FOLDER"] = "C:\external\override"
$environmentInfo.EnvironmentVariables["MIHO_DATA_ROOT"] = "C:\external\workspace"
Set-MihoGuiRenderChildEnvironmentV1 -StartInfo $environmentInfo -DebugPort 2345
if ($environmentInfo.EnvironmentVariables.ContainsKey("WEBVIEW2_USER_DATA_FOLDER") -or
    $environmentInfo.EnvironmentVariables.ContainsKey("MIHO_DATA_ROOT") -or
    [string]$environmentInfo.EnvironmentVariables["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] -cne
        "--remote-debugging-port=2345") {
    throw "GUI render child environment retained an external WebView/workspace override"
}

$self = Get-Process -Id $PID -ErrorAction Stop
$selfIdentities = @{}
if (-not (Wait-MihoCurrentDescendantProcessIdentitiesV1 `
        -RootProcessId $PID `
        -ExpectedRootStartTicks ([int64]$self.StartTime.ToUniversalTime().Ticks) `
        -ExpectedRootProcessName ([string]$self.ProcessName) `
        -Identities $selfIdentities `
        -TimeoutMilliseconds 2000)) {
    throw "GUI render ownership could not bind a stable live root from CIM and Get-Process snapshots"
}

$processRows = @(
    [pscustomobject]@{ process_id = 201; parent_process_id = 200; start_ticks = 101; process_name = "unrelated-new" },
    [pscustomobject]@{ process_id = 301; parent_process_id = 300; start_ticks = 102; process_name = "valid-grandchild" },
    [pscustomobject]@{ process_id = 200; parent_process_id = 100; start_ticks = 99; process_name = "pre-existing-bridge" },
    [pscustomobject]@{ process_id = 300; parent_process_id = 100; start_ticks = 100; process_name = "valid-child" }
)
$descendants = @(Get-MihoDescendantProcessSnapshotsFromRowsV1 `
    -RootProcessId 100 `
    -MinimumStartTicks 100 `
    -Rows $processRows)
$descendantIds = @($descendants | ForEach-Object { [int]$_.process_id })
if (($descendantIds -join ",") -cne "300,301") {
    throw "GUI render ownership traversal crossed a pre-existing PID bridge: $($descendantIds -join ',')"
}

$identityGenerations = @{}
Add-MihoOwnedProcessSnapshotsV1 `
    -Snapshots @(
        [pscustomobject]@{ process_id = 400; start_ticks = 100; process_name = "python" },
        [pscustomobject]@{ process_id = 400; start_ticks = 101; process_name = "msedgewebview2" }
    ) `
    -Identities $identityGenerations `
    -MinimumStartTicks 100
if ($identityGenerations.Count -ne 2 -or
    -not (Test-MihoCapturedPythonProcessV1 -Identities $identityGenerations)) {
    throw "GUI render ownership collapsed PID generations or forgot a captured short-lived Python identity"
}

$script:mihoSnapshotFixtureRows = @(
    [pscustomobject]@{ process_id = 500; parent_process_id = 1; start_ticks = 5000; process_name = "miho-desktop" },
    [pscustomobject]@{ process_id = 501; parent_process_id = 500; start_ticks = 5001; process_name = "msedgewebview2" }
)
function Get-MihoCurrentProcessSnapshotRowsV1 {
    return @($script:mihoSnapshotFixtureRows)
}
$boundIdentities = @{}
if (-not (Add-MihoCurrentDescendantProcessIdentitiesV1 `
        -RootProcessId 500 `
        -ExpectedRootProcessName "miho-desktop" `
        -Identities $boundIdentities `
        -MinimumStartTicks 5000) -or $boundIdentities.Count -ne 1) {
    throw "GUI render ownership rejected a root identity bound in the same process snapshot"
}
$script:mihoSnapshotFixtureRows = @(
    [pscustomobject]@{ process_id = 500; parent_process_id = 1; start_ticks = 5002; process_name = "miho-desktop" },
    [pscustomobject]@{ process_id = 502; parent_process_id = 500; start_ticks = 5003; process_name = "unrelated" }
)
if (Add-MihoCurrentDescendantProcessIdentitiesV1 `
        -RootProcessId 500 `
        -ExpectedRootProcessName "miho-desktop" `
        -Identities $boundIdentities `
        -MinimumStartTicks 5000) {
    throw "GUI render ownership expanded a PID tree after the root identity changed"
}
if ($boundIdentities.Count -ne 1) {
    throw "GUI render ownership captured descendants through a reused root PID"
}

$diagnosticInfo = [System.Diagnostics.ProcessStartInfo]::new()
$diagnosticInfo.FileName = $env:ComSpec
$diagnosticInfo.Arguments = '/d /s /c "echo setup-hook-failure 1>&2 & exit /b 101"'
$diagnosticInfo.UseShellExecute = $false
$diagnosticInfo.CreateNoWindow = $true
$diagnosticInfo.RedirectStandardOutput = $true
$diagnosticInfo.RedirectStandardError = $true
$diagnosticProcess = [System.Diagnostics.Process]::new()
$diagnosticProcess.StartInfo = $diagnosticInfo
try {
    if (-not $diagnosticProcess.Start()) {
        throw "GUI render diagnostic fixture could not start"
    }
    $diagnostic = Get-MihoExitedProcessDiagnosticV1 `
        -Process $diagnosticProcess `
        -WaitMilliseconds 5000
    if ($null -eq $diagnostic -or [int]$diagnostic.exit_code -ne 101 -or
        [string]$diagnostic.stderr -notmatch 'setup-hook-failure') {
        throw "GUI render diagnostic did not preserve an early setup-hook failure"
    }
}
finally {
    try { if (-not $diagnosticProcess.HasExited) { $diagnosticProcess.Kill() } } catch {}
    $diagnosticProcess.Dispose()
}

$scriptSource = Get-Content -LiteralPath $script -Raw
if ($scriptSource -notmatch 'Desktop process wrote unexpected stdout/stderr after rendering' -or
    $scriptSource -notmatch 'process_observation = "bound-snapshot-sampling-200ms"' -or
    $scriptSource -notmatch 'continuous_process_event_audit = \$false' -or
    $scriptSource -notmatch 'captured_descendants_cleaned = \$true' -or
    $scriptSource -notmatch 'webview_data_isolated = \(\$Mode -ceq "Portable"\)' -or
    $scriptSource -notmatch 'webview_data_scope = ' -or
    $scriptSource -notmatch 'webview_user_data_directory_bound = \$true' -or
    $scriptSource -notmatch 'Set-MihoGuiRenderChildEnvironmentV1 -StartInfo \$startInfo -DebugPort \$port' -or
    $scriptSource -notmatch 'Assert-MihoBoundWebViewUserDataDirectoryV1' -or
    $scriptSource -notmatch 'Get-MihoExitedProcessDiagnosticV1 -Process \$process -WaitMilliseconds 250' -or
    $scriptSource -match 'Get-FileHash' -or
    $scriptSource -match 'Get-MihoDescendantProcessIdsV1' -or
    $scriptSource -match 'Get-MihoOwnedDebugPortProcessIdsV1') {
    throw "GUI render script does not fail closed on process output or still uses unbound descendant PIDs"
}

Write-Output "gui-render-contract-tests: PASS"

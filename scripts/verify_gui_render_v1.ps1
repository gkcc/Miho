[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Executable,

    [ValidateRange(5, 120)]
    [int]$TimeoutSeconds = 45,

    [ValidateSet("Installed", "Portable")]
    [string]$Mode = "Installed",

    [string]$ProductProbeScript = "",

    [int]$ExpectedHsrOwned = -1,

    [int]$ExpectedZzzOwned = -1,

    [int]$ExpectedHsrTotal = -1,

    [int]$ExpectedZzzTotal = -1,

    [switch]$RunProductUpdates,

    [ValidateRange(30, 900)]
    [int]$ProductUpdateTimeoutSeconds = 600
)

$ErrorActionPreference = "Stop"
$readyUrl = "https://tauri.localhost/#miho-app-ready-v1"
$visualizerStartupFailureCodes = @(
    "legacy_protocol_missing",
    "data_load_failed",
    "ready_handshake_rejected",
    "ready_timeout"
)

function Resolve-MihoVisualizerStartupWatchdogSecondsV1 {
    param([Parameter(Mandatory = $true)][ValidateRange(5, 120)][int]$RequestedSeconds)

    return [Math]::Max(45, $RequestedSeconds)
}

function Test-MihoFixedVisualizerStartupFailureCodeV1 {
    param([AllowEmptyString()][string]$Code)

    return $visualizerStartupFailureCodes -ccontains $Code
}

function Assert-MihoVisualizerStartupDidNotFailV1 {
    param([Parameter(Mandatory = $true)]$Dom)

    $code = [string]$Dom.visualizerStartupFailureCode
    if (Test-MihoFixedVisualizerStartupFailureCodeV1 -Code $code) {
        throw ("visualizer_startup_failed code={0} game={1}" -f
            $code,
            [string]$Dom.visualizerStartupGame)
    }
}

function Test-MihoFixedVisualizerStartupFailureMessageV1 {
    param([AllowEmptyString()][string]$Message)

    return $Message -cmatch '^visualizer_startup_failed code=(?:legacy_protocol_missing|data_load_failed|ready_handshake_rejected|ready_timeout) game=[^\r\n]*$'
}

function Get-MihoProbeFileSha256V1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $stream = [System.IO.File]::OpenRead([System.IO.Path]::GetFullPath($LiteralPath))
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        return (($sha256.ComputeHash($stream) | ForEach-Object { $_.ToString("x2") }) -join "")
    }
    finally {
        $sha256.Dispose()
        $stream.Dispose()
    }
}

function Get-MihoPeSubsystemV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $stream = [System.IO.File]::OpenRead([System.IO.Path]::GetFullPath($LiteralPath))
    $reader = [System.IO.BinaryReader]::new($stream)
    try {
        if ($stream.Length -lt 512 -or $reader.ReadUInt16() -ne 0x5A4D) {
            throw "GUI render probe requires a valid PE executable"
        }
        $stream.Position = 0x3C
        $peOffset = $reader.ReadInt32()
        if ($peOffset -lt 0 -or ([int64]$peOffset + 94) -gt $stream.Length) {
            throw "GUI render probe found an invalid PE header offset"
        }
        $stream.Position = $peOffset
        if ($reader.ReadUInt32() -ne 0x00004550) {
            throw "GUI render probe found an invalid PE signature"
        }
        $stream.Position = [int64]$peOffset + 24
        $magic = $reader.ReadUInt16()
        if ($magic -ne 0x010B -and $magic -ne 0x020B) {
            throw "GUI render probe found an unsupported PE optional header"
        }
        $stream.Position = [int64]$peOffset + 24 + 68
        return [int]$reader.ReadUInt16()
    }
    finally {
        $reader.Dispose()
        $stream.Dispose()
    }
}

function Test-MihoRenderedTargetV1 {
    param([Parameter(Mandatory = $true)]$Target)

    if ([string]$Target.url -cne $readyUrl) {
        return $false
    }
    if ($null -ne $Target.PSObject.Properties["type"] -and
        -not [string]::IsNullOrWhiteSpace([string]$Target.type) -and
        [string]$Target.type -cne "page") {
        return $false
    }
    return $true
}

function Test-MihoRenderedDomV1 {
    param([Parameter(Mandatory = $true)]$Dom)

    Assert-MihoVisualizerStartupDidNotFailV1 -Dom $Dom

    if ([string]$Dom.href -cne $readyUrl -or
        [string]$Dom.readyState -cne "complete" -or
        [string]$Dom.ready -cne "v1" -or
        [string]$Dom.brandText -cne "MIHO ENDGAME" -or
        [int]$Dom.appChildCount -lt 2 -or
        [bool]$Dom.visualizerLoaded -ne $true -or
        [string]$Dom.visualizerStartupState -cne "ready" -or
        -not [string]::IsNullOrEmpty([string]$Dom.visualizerStartupFailureCode) -or
        [string]$Dom.visualizerStartupGame -cnotin @("hsr", "zzz") -or
        [bool]$Dom.tauriInternals -ne $true -or
        [bool]$Dom.neterror) {
        return $false
    }
    $errorEvidence = "{0}`n{1}" -f [string]$Dom.href, [string]$Dom.bodyText
    return $errorEvidence -notmatch '(?i)chrome-error://|ERR_FILE_NOT_FOUND|Microsoft Edge'
}

function Test-MihoProcessStartsWithinProbeV1 {
    param(
        [Parameter(Mandatory = $true)][int64]$ProcessStartTicks,
        [Parameter(Mandatory = $true)][int64]$RootStartTicks
    )

    return $RootStartTicks -gt 0 -and $ProcessStartTicks -ge $RootStartTicks
}

function Resolve-MihoWebViewUserDataDirectoryArgumentV1 {
    param([Parameter(Mandatory = $true)][string]$CommandLine)

    $matches = [regex]::Matches(
        $CommandLine,
        '(?i)(?:^|\s)--user-data-dir=(?:"([^"]+)"|([^\s"]+))(?=\s|$)'
    )
    if ($matches.Count -ne 1) {
        throw "WebView2 browser command line must contain exactly one user-data-dir argument"
    }
    $value = if ($matches[0].Groups[1].Success) {
        [string]$matches[0].Groups[1].Value
    }
    else {
        [string]$matches[0].Groups[2].Value
    }
    if ([string]::IsNullOrWhiteSpace($value) -or -not [System.IO.Path]::IsPathRooted($value)) {
        throw "WebView2 browser user-data-dir argument is not an absolute filesystem path"
    }
    try {
        return [System.IO.Path]::GetFullPath($value).TrimEnd("\", "/")
    }
    catch {
        throw "WebView2 browser user-data-dir argument is not a normal filesystem path"
    }
}

function Assert-MihoBoundWebViewUserDataDirectoryV1 {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$BrowserSnapshots,
        [Parameter(Mandatory = $true)][string]$ExpectedDirectory
    )

    if ($BrowserSnapshots.Count -eq 0) {
        throw "WebView2 debug listener has no bound browser process snapshot"
    }
    $expected = [System.IO.Path]::GetFullPath($ExpectedDirectory).TrimEnd("\", "/")
    foreach ($snapshot in $BrowserSnapshots) {
        if ([string]$snapshot.process_name -cne "msedgewebview2" -or
            [string]::IsNullOrWhiteSpace([string]$snapshot.command_line)) {
            throw "WebView2 debug listener process identity is incomplete"
        }
        $actual = Resolve-MihoWebViewUserDataDirectoryArgumentV1 `
            -CommandLine ([string]$snapshot.command_line)
        if (-not [string]::Equals($actual, $expected, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "WebView2 browser user-data-dir escaped the expected application cache"
        }
    }
    return $expected
}

function Set-MihoGuiRenderChildEnvironmentV1 {
    param(
        [Parameter(Mandatory = $true)][System.Diagnostics.ProcessStartInfo]$StartInfo,
        [Parameter(Mandatory = $true)][ValidateRange(1, 65535)][int]$DebugPort
    )

    $StartInfo.EnvironmentVariables["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] =
        "--remote-debugging-port=$DebugPort"
    $StartInfo.EnvironmentVariables.Remove("WEBVIEW2_USER_DATA_FOLDER")
    $StartInfo.EnvironmentVariables.Remove("MIHO_DATA_ROOT")
}

function Get-MihoLoopbackPortV1 {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        return [int]$listener.LocalEndpoint.Port
    }
    finally {
        $listener.Stop()
    }
}

function Invoke-MihoCdpDomProbeV1 {
    param([Parameter(Mandatory = $true)]$Target)

    $webSocketUrl = [string]$Target.webSocketDebuggerUrl
    if ([string]::IsNullOrWhiteSpace($webSocketUrl)) {
        throw "DevTools target does not expose a WebSocket debugger URL"
    }
    $socket = [System.Net.WebSockets.ClientWebSocket]::new()
    $cancellation = [System.Threading.CancellationTokenSource]::new([TimeSpan]::FromSeconds(10))
    try {
        $null = $socket.ConnectAsync([Uri]$webSocketUrl, $cancellation.Token).GetAwaiter().GetResult()
        $expression = "(()=>({href:location.href,readyState:document.readyState,ready:document.documentElement?.dataset?.mihoAppReady??'',brandText:document.querySelector('.brand .eyebrow')?.textContent??'',appChildCount:document.querySelector('#app')?.childElementCount??0,visualizerLoaded:[...document.querySelectorAll('iframe.visualizer-frame')].some(frame=>!!frame.getAttribute('src')&&frame.dataset.loaded==='true'),visualizerStartupState:document.documentElement?.dataset?.visualizerStartupState??'',visualizerStartupFailureCode:document.documentElement?.dataset?.visualizerStartupFailureCode??'',visualizerStartupGame:document.documentElement?.dataset?.visualizerStartupGame??'',tauriInternals:typeof window.__TAURI_INTERNALS__==='object',bodyText:(document.body?.innerText??'').slice(0,2000),neterror:!!document.querySelector('body.neterror')}))()"
        $command = @{
            id = 17
            method = "Runtime.evaluate"
            params = @{
                expression = $expression
                returnByValue = $true
                awaitPromise = $true
            }
        } | ConvertTo-Json -Compress -Depth 6
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($command)
        $null = $socket.SendAsync(
            [ArraySegment[byte]]::new($bytes),
            [System.Net.WebSockets.WebSocketMessageType]::Text,
            $true,
            $cancellation.Token
        ).GetAwaiter().GetResult()
        $buffer = New-Object byte[] 65536
        while ($true) {
            $stream = [System.IO.MemoryStream]::new()
            try {
                do {
                    $receive = $socket.ReceiveAsync(
                        [ArraySegment[byte]]::new($buffer),
                        $cancellation.Token
                    ).GetAwaiter().GetResult()
                    if ($receive.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
                        throw "DevTools WebSocket closed before returning the DOM result"
                    }
                    if ($receive.Count -gt 0) {
                        $stream.Write($buffer, 0, $receive.Count)
                    }
                } while (-not $receive.EndOfMessage)
                $response = [System.Text.Encoding]::UTF8.GetString($stream.ToArray()) | ConvertFrom-Json -ErrorAction Stop
            }
            finally {
                $stream.Dispose()
            }
            if ([int]$response.id -ne 17) { continue }
            if ($null -ne $response.error -or $null -ne $response.result.exceptionDetails) {
                throw "DevTools Runtime.evaluate returned an error"
            }
            return $response.result.result.value
        }
    }
    finally {
        try { $socket.Abort() } catch {}
        $socket.Dispose()
        $cancellation.Dispose()
    }
}

function Get-MihoDescendantProcessSnapshotsFromRowsV1 {
    param(
        [Parameter(Mandatory = $true)][int]$RootProcessId,
        [Parameter(Mandatory = $true)][int64]$MinimumStartTicks,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Rows
    )

    $known = New-Object 'System.Collections.Generic.HashSet[int]'
    $null = $known.Add($RootProcessId)
    $accepted = New-Object System.Collections.ArrayList
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($row in $Rows) {
            $processId = [int]$row.process_id
            if ($processId -eq $RootProcessId -or
                -not $known.Contains([int]$row.parent_process_id) -or
                $known.Contains($processId) -or
                -not (Test-MihoProcessStartsWithinProbeV1 `
                    -ProcessStartTicks ([int64]$row.start_ticks) `
                    -RootStartTicks $MinimumStartTicks)) {
                continue
            }
            $null = $known.Add($processId)
            $null = $accepted.Add($row)
            $changed = $true
        }
    }
    return @($accepted | Sort-Object { [int]$_.process_id })
}

function Get-MihoCurrentProcessSnapshotRowsV1 {
    $snapshots = New-Object System.Collections.ArrayList
    foreach ($row in @(Get-CimInstance -ClassName Win32_Process -ErrorAction Stop)) {
        $processId = [int]$row.ProcessId
        $processItem = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($null -eq $processItem) { continue }
        try {
            $processStartTicks = [int64]$processItem.StartTime.ToUniversalTime().Ticks
            $cimStartTicks = [int64]([datetime]$row.CreationDate).ToUniversalTime().Ticks
            $processName = [string]$processItem.ProcessName
            $cimProcessName = [System.IO.Path]::GetFileNameWithoutExtension([string]$row.Name)
        }
        catch {
            continue
        }
        $processMicrosecondTicks = $processStartTicks - ($processStartTicks % 10)
        $cimMicrosecondTicks = $cimStartTicks - ($cimStartTicks % 10)
        if ($processMicrosecondTicks -ne $cimMicrosecondTicks -or
            -not [string]::Equals($processName, $cimProcessName, [System.StringComparison]::OrdinalIgnoreCase)) {
            continue
        }
        $null = $snapshots.Add([pscustomobject][ordered]@{
            process_id = $processId
            parent_process_id = [int]$row.ParentProcessId
            start_ticks = $processStartTicks
            process_name = $processName
        })
    }
    return @($snapshots)
}

function Get-MihoProcessIdentityKeyV1 {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][int64]$StartTicks,
        [Parameter(Mandatory = $true)][string]$ProcessName
    )

    return "{0}:{1}:{2}" -f $ProcessId, $StartTicks, $ProcessName
}

function Add-MihoCurrentDescendantProcessIdentitiesV1 {
    param(
        [Parameter(Mandatory = $true)][int]$RootProcessId,
        [Parameter(Mandatory = $true)][string]$ExpectedRootProcessName,
        [Parameter(Mandatory = $true)][hashtable]$Identities,
        [Parameter(Mandatory = $true)][int64]$MinimumStartTicks
    )

    $rows = @(Get-MihoCurrentProcessSnapshotRowsV1)
    $boundRoot = @($rows | Where-Object {
        [int]$_.process_id -eq $RootProcessId -and
        [int64]$_.start_ticks -eq $MinimumStartTicks -and
        [string]$_.process_name -ceq $ExpectedRootProcessName
    })
    if ($boundRoot.Count -ne 1) {
        return $false
    }
    $descendants = @(Get-MihoDescendantProcessSnapshotsFromRowsV1 `
        -RootProcessId $RootProcessId `
        -MinimumStartTicks $MinimumStartTicks `
        -Rows $rows)
    foreach ($descendant in $descendants) {
        $key = Get-MihoProcessIdentityKeyV1 `
            -ProcessId ([int]$descendant.process_id) `
            -StartTicks ([int64]$descendant.start_ticks) `
            -ProcessName ([string]$descendant.process_name)
        if (-not $Identities.ContainsKey($key)) {
            $Identities[$key] = [pscustomobject][ordered]@{
                process_id = [int]$descendant.process_id
                start_ticks = [int64]$descendant.start_ticks
                process_name = [string]$descendant.process_name
            }
        }
    }
    return $true
}

function Get-MihoOwnedDebugPortProcessSnapshotsV1 {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][int64]$MinimumStartTicks
    )

    $owned = New-Object System.Collections.ArrayList
    foreach ($connection in @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) {
        $processId = [int]$connection.OwningProcess
        $row = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        if ($null -eq $row -or [string]$row.Name -cne "msedgewebview2.exe" -or
            [string]$row.CommandLine -notmatch ("(?i)(?:^|\s)--remote-debugging-port={0}(?:\s|$)" -f [regex]::Escape([string]$Port))) {
            continue
        }
        $processItem = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($null -eq $processItem) { continue }
        try {
            $startTicks = [int64]$processItem.StartTime.ToUniversalTime().Ticks
            $cimStartTicks = [int64]([datetime]$row.CreationDate).ToUniversalTime().Ticks
            $processName = [string]$processItem.ProcessName
        }
        catch {
            continue
        }
        $sameMicrosecond = ($startTicks - ($startTicks % 10)) -eq ($cimStartTicks - ($cimStartTicks % 10))
        $stillOwnsPort = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Where-Object {
            [int]$_.OwningProcess -eq $processId
        }).Count -gt 0
        if ($sameMicrosecond -and $processName -ceq "msedgewebview2" -and $stillOwnsPort -and
            (Test-MihoProcessStartsWithinProbeV1 -ProcessStartTicks $startTicks -RootStartTicks $MinimumStartTicks)) {
            $null = $owned.Add([pscustomobject][ordered]@{
                process_id = $processId
                start_ticks = $startTicks
                process_name = $processName
                command_line = [string]$row.CommandLine
            })
        }
    }
    return @($owned)
}

function Add-MihoOwnedProcessSnapshotsV1 {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Snapshots,
        [Parameter(Mandatory = $true)][hashtable]$Identities,
        [Parameter(Mandatory = $true)][int64]$MinimumStartTicks
    )

    foreach ($snapshot in $Snapshots) {
        if (-not (Test-MihoProcessStartsWithinProbeV1 `
                -ProcessStartTicks ([int64]$snapshot.start_ticks) `
                -RootStartTicks $MinimumStartTicks)) {
            continue
        }
        $key = Get-MihoProcessIdentityKeyV1 `
            -ProcessId ([int]$snapshot.process_id) `
            -StartTicks ([int64]$snapshot.start_ticks) `
            -ProcessName ([string]$snapshot.process_name)
        if (-not $Identities.ContainsKey($key)) {
            $Identities[$key] = [pscustomobject][ordered]@{
                process_id = [int]$snapshot.process_id
                start_ticks = [int64]$snapshot.start_ticks
                process_name = [string]$snapshot.process_name
            }
        }
    }
}

function Test-MihoCapturedPythonProcessV1 {
    param([Parameter(Mandatory = $true)][hashtable]$Identities)

    return @($Identities.Values | Where-Object {
        [string]$_.process_name -like "python*"
    }).Count -gt 0
}

function Get-MihoLiveOwnedProcessesV1 {
    param([Parameter(Mandatory = $true)][hashtable]$Identities)

    $owned = New-Object System.Collections.ArrayList
    foreach ($identity in @($Identities.Values)) {
        $processItem = Get-Process -Id ([int]$identity.process_id) -ErrorAction SilentlyContinue
        if ($null -eq $processItem) { continue }
        try {
            $sameIdentity = $processItem.StartTime.ToUniversalTime().Ticks -eq [int64]$identity.start_ticks -and
                [string]$processItem.ProcessName -ceq [string]$identity.process_name
        }
        catch {
            $sameIdentity = $false
        }
        if ($sameIdentity) {
            $null = $owned.Add($processItem)
        }
    }
    return @($owned)
}

function Test-MihoLiveProcessIdentityV1 {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][int64]$ExpectedStartTicks,
        [Parameter(Mandatory = $true)][string]$ExpectedProcessName
    )

    $processItem = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $processItem) { return $false }
    try {
        return $processItem.StartTime.ToUniversalTime().Ticks -eq $ExpectedStartTicks -and
            [string]$processItem.ProcessName -ceq $ExpectedProcessName
    }
    catch {
        return $false
    }
}

function Wait-MihoCurrentDescendantProcessIdentitiesV1 {
    param(
        [Parameter(Mandatory = $true)][int]$RootProcessId,
        [Parameter(Mandatory = $true)][int64]$ExpectedRootStartTicks,
        [Parameter(Mandatory = $true)][string]$ExpectedRootProcessName,
        [Parameter(Mandatory = $true)][hashtable]$Identities,
        [ValidateRange(100, 5000)][int]$TimeoutMilliseconds = 2000
    )

    $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMilliseconds)
    do {
        if (Add-MihoCurrentDescendantProcessIdentitiesV1 `
                -RootProcessId $RootProcessId `
                -ExpectedRootProcessName $ExpectedRootProcessName `
                -Identities $Identities `
                -MinimumStartTicks $ExpectedRootStartTicks) {
            return $true
        }
        if (-not (Test-MihoLiveProcessIdentityV1 `
                -ProcessId $RootProcessId `
                -ExpectedStartTicks $ExpectedRootStartTicks `
                -ExpectedProcessName $ExpectedRootProcessName)) {
            return $false
        }
        Start-Sleep -Milliseconds 25
    } while ([DateTime]::UtcNow -lt $deadline)
    return $false
}

function Test-MihoLoopbackPortClosedV1 {
    param([Parameter(Mandatory = $true)][int]$Port)

    return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue).Count -eq 0
}

function Get-MihoExitedProcessDiagnosticV1 {
    param(
        [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process,
        [ValidateRange(0, 5000)][int]$WaitMilliseconds = 0
    )

    if (-not $Process.WaitForExit($WaitMilliseconds)) { return $null }
    return [pscustomobject][ordered]@{
        exit_code = [int]$Process.ExitCode
        stdout = [string]$Process.StandardOutput.ReadToEnd()
        stderr = [string]$Process.StandardError.ReadToEnd()
    }
}

function Resolve-MihoProbeNormalDirectoryV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $full = [System.IO.Path]::GetFullPath($LiteralPath)
    $root = [System.IO.Path]::GetPathRoot($full)
    if ([string]::IsNullOrWhiteSpace($root)) {
        throw "WebView data directory has no filesystem root"
    }
    $current = $root
    $separators = [char[]]@(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    foreach ($component in $full.Substring($root.Length).Split($separators, [System.StringSplitOptions]::RemoveEmptyEntries)) {
        $current = Join-Path $current $component
        $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "WebView data directory contains a reparse point"
        }
    }
    $directory = Get-Item -LiteralPath $full -Force -ErrorAction Stop
    if (-not $directory.PSIsContainer) {
        throw "WebView data path is not a directory"
    }
    return $directory.FullName
}

if ($env:MIHO_GUI_RENDER_TEST_DEFINE_ONLY_V1 -ceq "1") {
    return
}

$effectiveVisualizerStartupWatchdogSeconds = Resolve-MihoVisualizerStartupWatchdogSecondsV1 `
    -RequestedSeconds $TimeoutSeconds
$fullExecutable = [System.IO.Path]::GetFullPath($Executable)
$executableItem = Get-Item -LiteralPath $fullExecutable -Force -ErrorAction Stop
if ($executableItem.PSIsContainer -or
    ($executableItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "GUI render probe requires a normal executable file"
}
if ((Get-MihoPeSubsystemV1 -LiteralPath $fullExecutable) -ne 2) {
    throw "GUI render probe requires a WINDOWS_GUI executable without a console window"
}
$workingDirectory = Split-Path -Parent $fullExecutable
$portableMarker = Join-Path $workingDirectory "miho-portable-v1.json"
$installedProbe = Join-Path $workingDirectory "installer\task_scheduler_v1.ps1"
if ($Mode -ceq "Installed") {
    if (Test-Path -LiteralPath $portableMarker) {
        throw "Installed GUI render probe refuses a portable layout"
    }
    if (-not (Test-Path -LiteralPath $installedProbe -PathType Leaf)) {
        throw "Installed GUI render probe requires the complete installed layout"
    }
}
elseif (-not (Test-Path -LiteralPath $portableMarker -PathType Leaf)) {
    throw "Portable GUI render probe requires the portable marker"
}
$expectedWebViewDataRoot = if ($Mode -ceq "Installed") {
    $localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
    if ([string]::IsNullOrWhiteSpace($localAppData)) {
        throw "Installed GUI render probe could not resolve local AppData"
    }
    Join-Path $localAppData "com.miho.endgame"
}
else {
    Join-Path $workingDirectory "data\.miho\webview2"
}
$expectedWebViewUserDataDirectory = Join-Path $expectedWebViewDataRoot "EBWebView"
$fullProductProbeScript = ""
$nodeCommand = $null
if (-not [string]::IsNullOrWhiteSpace($ProductProbeScript)) {
    $fullProductProbeScript = [System.IO.Path]::GetFullPath($ProductProbeScript)
    $probeItem = Get-Item -LiteralPath $fullProductProbeScript -Force -ErrorAction Stop
    if ($probeItem.PSIsContainer -or
        ($probeItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Product UI probe requires a normal script file"
    }
    if ($ExpectedHsrOwned -lt 0 -or $ExpectedZzzOwned -lt 0 -or
        $ExpectedHsrTotal -le 0 -or $ExpectedZzzTotal -le 0 -or
        $ExpectedHsrOwned -gt $ExpectedHsrTotal -or $ExpectedZzzOwned -gt $ExpectedZzzTotal) {
        throw "Product UI probe requires valid expected Box and roster counts"
    }
    $nodeCommand = Get-Command node -CommandType Application -ErrorAction Stop
}

foreach ($candidate in @(Get-Process -Name $executableItem.BaseName -ErrorAction SilentlyContinue)) {
    $candidatePath = $null
    try { $candidatePath = $candidate.Path } catch { $candidatePath = $null }
    if (-not [string]::IsNullOrWhiteSpace($candidatePath) -and
        [string]::Equals(
            [System.IO.Path]::GetFullPath($candidatePath),
            $fullExecutable,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw "Close the existing application window before running the GUI render probe"
    }
}

$port = Get-MihoLoopbackPortV1
$startInfo = [System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $fullExecutable
$startInfo.WorkingDirectory = $workingDirectory
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
Set-MihoGuiRenderChildEnvironmentV1 -StartInfo $startInfo -DebugPort $port

$process = [System.Diagnostics.Process]::new()
$process.StartInfo = $startInfo
$processStarted = $false
$rootProcessId = 0
$rootStartTicks = [int64]0
$rootProcessName = ""
$readyTarget = $null
$renderedDom = $null
$lastTargets = @()
$lastDom = $null
$lastCdpError = ""
$boundWebViewUserDataDirectory = ""
$ownedDescendantIdentities = @{}
$normalExit = $false
$stdout = ""
$stderr = ""
$probeFailure = $null
$receiptJson = $null
$cleanupFailure = $null
$productProbeReceipt = $null
try {
    if (-not $process.Start()) {
        throw "GUI render probe could not start the desktop process"
    }
    $processStarted = $true
    $rootProcessId = [int]$process.Id
    $rootStartTicks = [int64]$process.StartTime.ToUniversalTime().Ticks
    $rootProcessName = [string]$process.ProcessName
    $deadline = [DateTime]::UtcNow.AddSeconds($effectiveVisualizerStartupWatchdogSeconds)
    do {
        $earlyExit = Get-MihoExitedProcessDiagnosticV1 -Process $process
        if ($null -ne $earlyExit) {
            $stdout = [string]$earlyExit.stdout
            $stderr = [string]$earlyExit.stderr
            throw "Desktop process exited before rendering (exit=$([int]$earlyExit.exit_code), stderr=$stderr)"
        }
        if (-not (Wait-MihoCurrentDescendantProcessIdentitiesV1 `
                -RootProcessId $rootProcessId `
                -ExpectedRootStartTicks $rootStartTicks `
                -ExpectedRootProcessName $rootProcessName `
                -Identities $ownedDescendantIdentities `
                -TimeoutMilliseconds 2000)) {
            $snapshotExit = Get-MihoExitedProcessDiagnosticV1 -Process $process -WaitMilliseconds 250
            if ($null -ne $snapshotExit) {
                $stdout = [string]$snapshotExit.stdout
                $stderr = [string]$snapshotExit.stderr
                throw "Desktop process exited before rendering (exit=$([int]$snapshotExit.exit_code), stderr=$stderr)"
            }
            throw "Desktop root process identity was absent from bound render snapshots after retry"
        }
        if (Test-MihoCapturedPythonProcessV1 -Identities $ownedDescendantIdentities) {
            throw "Desktop GUI render probe observed a Python descendant before rendering"
        }
        try {
            $targetResponse = Invoke-RestMethod `
                -Uri ("http://127.0.0.1:{0}/json/list" -f $port) `
                -Method Get `
                -TimeoutSec 1 `
                -ErrorAction Stop
            $debugOwnerSnapshots = @(Get-MihoOwnedDebugPortProcessSnapshotsV1 -Port $port -MinimumStartTicks $rootStartTicks)
            $boundWebViewUserDataDirectory = Assert-MihoBoundWebViewUserDataDirectoryV1 `
                -BrowserSnapshots $debugOwnerSnapshots `
                -ExpectedDirectory $expectedWebViewUserDataDirectory
            Add-MihoOwnedProcessSnapshotsV1 `
                -Snapshots $debugOwnerSnapshots `
                -Identities $ownedDescendantIdentities `
                -MinimumStartTicks $rootStartTicks
            $lastTargets = if ($targetResponse -is [System.Array]) {
                @($targetResponse.GetEnumerator())
            }
            else {
                @($targetResponse)
            }
            $targetMatch = @($lastTargets | Where-Object { Test-MihoRenderedTargetV1 -Target $_ } | Select-Object -First 1)
            if ($targetMatch.Count -eq 1) {
                $readyTarget = $targetMatch[0]
                try {
                    $lastDom = Invoke-MihoCdpDomProbeV1 -Target $readyTarget
                    if (Test-MihoRenderedDomV1 -Dom $lastDom) {
                        $renderedDom = $lastDom
                        break
                    }
                }
                catch {
                    if (Test-MihoFixedVisualizerStartupFailureMessageV1 `
                            -Message ([string]$_.Exception.Message)) {
                        throw
                    }
                    $lastCdpError = $_.Exception.Message
                }
            }
        }
        catch {
            if (Test-MihoFixedVisualizerStartupFailureMessageV1 `
                    -Message ([string]$_.Exception.Message)) {
                throw
            }
            $lastTargets = @()
            $lastCdpError = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)

    if ($null -eq $renderedDom) {
        $observed = @($lastTargets | ForEach-Object {
            [pscustomobject][ordered]@{
                type = [string]$_.type
                title = [string]$_.title
                url = [string]$_.url
            }
        }) | ConvertTo-Json -Depth 3 -Compress
        $dom = if ($null -eq $lastDom) { "null" } else { $lastDom | ConvertTo-Json -Depth 4 -Compress }
        throw "GUI DOM render sentinel was not observed; targets=$observed; dom=$dom; cdp=$lastCdpError"
    }
    if ([string]::IsNullOrWhiteSpace($boundWebViewUserDataDirectory)) {
        throw "GUI DOM rendered without a bound WebView2 user-data directory"
    }

    if (-not [string]::IsNullOrWhiteSpace($fullProductProbeScript)) {
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $productProbeOutput = @(& $nodeCommand.Source `
                $fullProductProbeScript `
                "--ws" ([string]$readyTarget.webSocketDebuggerUrl) `
                "--expected-hsr-owned" ([string]$ExpectedHsrOwned) `
                "--expected-zzz-owned" ([string]$ExpectedZzzOwned) `
                "--expected-hsr-total" ([string]$ExpectedHsrTotal) `
                "--expected-zzz-total" ([string]$ExpectedZzzTotal) `
                "--timeout-ms" "120000" `
                "--run-updates" ([string]$RunProductUpdates.IsPresent).ToLowerInvariant() `
                "--update-timeout-ms" ([string]($ProductUpdateTimeoutSeconds * 1000)) 2>&1)
            $productProbeExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        $productProbeText = (($productProbeOutput | ForEach-Object { [string]$_ }) -join "`n").Trim()
        if ($productProbeExitCode -ne 0) {
            throw "Product UI probe failed (exit=$productProbeExitCode): $productProbeText"
        }
        try {
            $productProbeReceipt = $productProbeText | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            throw "Product UI probe returned an invalid receipt: $productProbeText"
        }
        if ([string]$productProbeReceipt.schema_version -cne "miho-product-ui-probe-v1") {
            throw "Product UI probe returned an unexpected schema"
        }
    }

    if (-not (Wait-MihoCurrentDescendantProcessIdentitiesV1 `
            -RootProcessId $rootProcessId `
            -ExpectedRootStartTicks $rootStartTicks `
            -ExpectedRootProcessName $rootProcessName `
            -Identities $ownedDescendantIdentities `
            -TimeoutMilliseconds 2000)) {
        throw "Desktop root process identity changed before descendant verification"
    }
    if (Test-MihoCapturedPythonProcessV1 -Identities $ownedDescendantIdentities) {
        throw "Desktop GUI render probe started a Python descendant"
    }
    $holdDeadline = [DateTime]::UtcNow.AddSeconds(5)
    do {
        Start-Sleep -Milliseconds 200
        $process.Refresh()
        if ($process.HasExited) {
            throw "Desktop process did not remain alive for five seconds after rendering"
        }
        if (-not (Wait-MihoCurrentDescendantProcessIdentitiesV1 `
                -RootProcessId $rootProcessId `
                -ExpectedRootStartTicks $rootStartTicks `
                -ExpectedRootProcessName $rootProcessName `
                -Identities $ownedDescendantIdentities `
                -TimeoutMilliseconds 2000)) {
            throw "Desktop root process identity changed during the five-second hold"
        }
        if (Test-MihoCapturedPythonProcessV1 -Identities $ownedDescendantIdentities) {
            throw "Desktop GUI render probe observed a Python descendant during the five-second hold"
        }
    } while ([DateTime]::UtcNow -lt $holdDeadline)
    if (-not $process.CloseMainWindow()) {
        throw "Desktop process did not expose a closable main window after rendering"
    }
    if (-not $process.WaitForExit(10000)) {
        throw "Desktop process did not exit after its main window closed"
    }
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    if ($process.ExitCode -ne 0) {
        throw "Desktop process returned a non-zero exit code after rendering: $($process.ExitCode)"
    }
    if (-not [string]::IsNullOrEmpty($stdout) -or -not [string]::IsNullOrEmpty($stderr)) {
        throw "Desktop process wrote unexpected stdout/stderr after rendering (stdout_length=$($stdout.Length), stderr_length=$($stderr.Length))"
    }
    $cleanupDeadline = [DateTime]::UtcNow.AddSeconds(20)
    do {
        $debugOwnerSnapshots = @(Get-MihoOwnedDebugPortProcessSnapshotsV1 -Port $port -MinimumStartTicks $rootStartTicks)
        Add-MihoOwnedProcessSnapshotsV1 `
            -Snapshots $debugOwnerSnapshots `
            -Identities $ownedDescendantIdentities `
            -MinimumStartTicks $rootStartTicks
        $remainingDescendants = @(Get-MihoLiveOwnedProcessesV1 -Identities $ownedDescendantIdentities)
        if (Test-MihoCapturedPythonProcessV1 -Identities $ownedDescendantIdentities) {
            throw "Desktop GUI render probe started a Python descendant while closing"
        }
        foreach ($ownedProcess in $remainingDescendants) {
            try { $ownedProcess.Kill() } catch {}
        }
        $remainingDescendants = @(Get-MihoLiveOwnedProcessesV1 -Identities $ownedDescendantIdentities)
        $debugPortClosed = Test-MihoLoopbackPortClosedV1 -Port $port
        if ($remainingDescendants.Count -eq 0 -and $debugPortClosed) { break }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $cleanupDeadline)
    if ($remainingDescendants.Count -ne 0 -or -not $debugPortClosed) {
        throw "Desktop GUI render probe left a descendant process or debug listener"
    }
    $observedWebViewDataRoot = Resolve-MihoProbeNormalDirectoryV1 -LiteralPath $expectedWebViewDataRoot
    $observedWebViewUserDataDirectory = Resolve-MihoProbeNormalDirectoryV1 `
        -LiteralPath $boundWebViewUserDataDirectory
    $expectedObservedWebViewUserDataDirectory = [System.IO.Path]::GetFullPath(
        (Join-Path $observedWebViewDataRoot "EBWebView")
    ).TrimEnd("\", "/")
    if (-not [string]::Equals(
            $observedWebViewUserDataDirectory.TrimEnd("\", "/"),
            $expectedObservedWebViewUserDataDirectory,
            [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Observed WebView2 user-data directory escaped the verified cache tree"
    }
    if ($Mode -ceq "Portable") {
        $portableDataPrefix = [System.IO.Path]::GetFullPath($workingDirectory).TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
        if (-not $observedWebViewDataRoot.StartsWith($portableDataPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Portable WebView data directory escaped the portable layout"
        }
    }
    $normalExit = $true
    $receiptJson = [pscustomobject][ordered]@{
        schema_version = "miho-gui-render-verification-v1"
        mode = $Mode.ToLowerInvariant()
        executable = $fullExecutable
        executable_sha256 = Get-MihoProbeFileSha256V1 -LiteralPath $fullExecutable
        title = [string]$readyTarget.title
        url = [string]$renderedDom.href
        render_sentinel = "data-miho-app-ready=v1"
        dom_ready_state = [string]$renderedDom.readyState
        dom_brand = [string]$renderedDom.brandText
        dom_app_child_count = [int]$renderedDom.appChildCount
        visualizer_loaded_before_close = [bool]$renderedDom.visualizerLoaded
        visualizer_startup_state = [string]$renderedDom.visualizerStartupState
        visualizer_startup_failure_code = [string]$renderedDom.visualizerStartupFailureCode
        visualizer_startup_game = [string]$renderedDom.visualizerStartupGame
        visualizer_startup_watchdog_seconds = [int]$effectiveVisualizerStartupWatchdogSeconds
        tauri_internals = [bool]$renderedDom.tauriInternals
        error_page_rejected = $true
        minimum_alive_seconds = 5
        normal_exit = $normalExit
        exit_code = [int]$process.ExitCode
        captured_descendants_cleaned = $true
        debug_port_closed = $true
        stdout_empty = [string]::IsNullOrEmpty($stdout)
        stderr_empty = [string]::IsNullOrEmpty($stderr)
        process_observation = "bound-snapshot-sampling-200ms"
        continuous_process_event_audit = $false
        python_identity_observed = $false
        webview_data_isolated = ($Mode -ceq "Portable")
        webview_data_scope = $(if ($Mode -ceq "Portable") { "portable-layout" } else { "default-installed-cache" })
        webview_user_data_directory_bound = $true
        product_probe = $productProbeReceipt
    } | ConvertTo-Json -Depth 20
}
catch {
    $probeFailure = $_
}
finally {
    if ($null -ne $process -and $processStarted) {
        try {
            if ($rootProcessId -gt 0 -and
                (Test-MihoLiveProcessIdentityV1 `
                    -ProcessId $rootProcessId `
                    -ExpectedStartTicks $rootStartTicks `
                    -ExpectedProcessName $rootProcessName)) {
                Add-MihoCurrentDescendantProcessIdentitiesV1 `
                    -RootProcessId $rootProcessId `
                    -ExpectedRootProcessName $rootProcessName `
                    -Identities $ownedDescendantIdentities `
                    -MinimumStartTicks $rootStartTicks | Out-Null
            }
            if (-not $process.HasExited) {
                $null = $process.CloseMainWindow()
                if (-not $process.WaitForExit(3000)) {
                    $process.Kill()
                    $null = $process.WaitForExit(5000)
                }
            }
            if ($rootProcessId -gt 0) {
                $forcedCleanupDeadline = [DateTime]::UtcNow.AddSeconds(20)
                do {
                    $debugOwnerSnapshots = @(Get-MihoOwnedDebugPortProcessSnapshotsV1 -Port $port -MinimumStartTicks $rootStartTicks)
                    Add-MihoOwnedProcessSnapshotsV1 `
                        -Snapshots $debugOwnerSnapshots `
                        -Identities $ownedDescendantIdentities `
                        -MinimumStartTicks $rootStartTicks
                    $remainingDescendants = @(Get-MihoLiveOwnedProcessesV1 -Identities $ownedDescendantIdentities)
                    foreach ($ownedProcess in $remainingDescendants) {
                        try { $ownedProcess.Kill() } catch {}
                    }
                    $remainingDescendants = @(Get-MihoLiveOwnedProcessesV1 -Identities $ownedDescendantIdentities)
                    $debugPortClosed = Test-MihoLoopbackPortClosedV1 -Port $port
                    if ($remainingDescendants.Count -eq 0 -and $debugPortClosed) { break }
                    Start-Sleep -Milliseconds 200
                } while ([DateTime]::UtcNow -lt $forcedCleanupDeadline)
                if ($remainingDescendants.Count -ne 0 -or -not $debugPortClosed) {
                    $remainingIdentity = @($remainingDescendants | ForEach-Object {
                        "{0}:{1}" -f $_.Id, $_.ProcessName
                    }) -join ","
                    $cleanupFailure = "GUI render probe cleanup left descendant=$remainingIdentity port_closed=$debugPortClosed"
                }
            }
        }
        catch {
            try { if (-not $process.HasExited) { $process.Kill() } } catch {}
            $cleanupFailure = "GUI render probe cleanup failed: $($_.Exception.Message)"
        }
        $process.Dispose()
    }
    elseif ($null -ne $process) {
        $process.Dispose()
    }
}

if ($null -ne $cleanupFailure) {
    $primary = if ($null -eq $probeFailure) { "none" } else { $probeFailure.Exception.Message }
    throw "$primary; $cleanupFailure"
}
if ($null -ne $probeFailure) {
    throw $probeFailure
}
Write-Output $receiptJson

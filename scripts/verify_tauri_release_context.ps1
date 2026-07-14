[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Get-Sha256HexV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    $stream = [System.IO.File]::OpenRead($LiteralPath)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try { return (($algorithm.ComputeHash($stream) | ForEach-Object { $_.ToString("x2") }) -join "") }
    finally { $algorithm.Dispose(); $stream.Dispose() }
}

function Get-TextSha256HexV1 {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        return (($algorithm.ComputeHash($utf8.GetBytes($Text)) | ForEach-Object { $_.ToString("x2") }) -join "")
    }
    finally { $algorithm.Dispose() }
}

function Resolve-SafePathV1 {
    param(
        [Parameter(Mandatory = $true)][string]$LiteralPath,
        [Parameter(Mandatory = $true)][bool]$Directory
    )
    $full = [System.IO.Path]::GetFullPath($LiteralPath)
    $rootPath = [System.IO.Path]::GetPathRoot($full)
    if ([string]::IsNullOrWhiteSpace($rootPath)) { throw "Release context path has no filesystem root." }
    $current = $rootPath
    foreach ($component in $full.Substring($rootPath.Length).Split(@("\", "/"), [System.StringSplitOptions]::RemoveEmptyEntries)) {
        $current = Join-Path $current $component
        $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Release context path contains a reparse point."
        }
    }
    $leaf = Get-Item -LiteralPath $full -Force -ErrorAction Stop
    if ([bool]$leaf.PSIsContainer -ne $Directory) { throw "Release context path has the wrong filesystem type." }
    return $leaf.FullName
}

function Read-StrictJsonFileV1 {
    param(
        [Parameter(Mandatory = $true)][string]$LiteralPath,
        [int64]$MaximumBytes = 1048576
    )
    $path = Resolve-SafePathV1 -LiteralPath $LiteralPath -Directory $false
    $metadata = Get-Item -LiteralPath $path -Force -ErrorAction Stop
    if ([int64]$metadata.Length -gt $MaximumBytes) { throw "Release JSON exceeds its supported size." }
    $content = [System.IO.File]::ReadAllBytes($path)
    if ([int64]$content.Length -gt $MaximumBytes) { throw "Release JSON exceeds its supported size." }
    try {
        $decoder = New-Object System.Text.UTF8Encoding($false, $true)
        $text = $decoder.GetString($content)
        $value = $text | ConvertFrom-Json -ErrorAction Stop
    }
    catch { throw "Release JSON is not strict UTF-8 JSON." }
    if ($null -eq $value -or $value -isnot [pscustomobject]) { throw "Release JSON must contain one object." }
    return $value
}

function Get-SafeFilesV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    $directory = Resolve-SafePathV1 -LiteralPath $LiteralPath -Directory $true
    $files = New-Object System.Collections.ArrayList
    foreach ($entry in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
        if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Release input tree contains a reparse point."
        }
        if ($entry.PSIsContainer) {
            foreach ($nested in @(Get-SafeFilesV1 -LiteralPath $entry.FullName)) { $null = $files.Add($nested) }
        }
        else { $null = $files.Add((Get-Item -LiteralPath (Resolve-SafePathV1 -LiteralPath $entry.FullName -Directory $false) -Force)) }
    }
    return @($files)
}

function Get-FileSetDigestV1 {
    param(
        [Parameter(Mandatory = $true)][string]$BaseRoot,
        [Parameter(Mandatory = $true)][object[]]$Files
    )
    $base = (Resolve-SafePathV1 -LiteralPath $BaseRoot -Directory $true).TrimEnd("\", "/")
    $prefix = $base + [System.IO.Path]::DirectorySeparatorChar
    $relativePaths = New-Object 'System.Collections.Generic.List[string]'
    $byRelative = @{}
    foreach ($entry in @($Files)) {
        $file = Get-Item -LiteralPath (Resolve-SafePathV1 -LiteralPath ([string]$entry.FullName) -Directory $false) -Force
        if (-not $file.FullName.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Release fingerprint input escapes its base root."
        }
        $relative = $file.FullName.Substring($prefix.Length).Replace("\", "/")
        if ($byRelative.ContainsKey($relative)) { throw "Release fingerprint contains a duplicate path." }
        $relativePaths.Add($relative)
        $byRelative[$relative] = $file
    }
    $relativePaths.Sort([System.StringComparer]::Ordinal)
    $builder = New-Object System.Text.StringBuilder
    foreach ($relative in $relativePaths) {
        $file = $byRelative[$relative]
        $null = $builder.Append($relative.Length).Append(":").Append($relative).Append(":")
        $null = $builder.Append([int64]$file.Length).Append(":").Append((Get-Sha256HexV1 -LiteralPath $file.FullName)).Append("`n")
    }
    return [pscustomobject][ordered]@{
        digest = Get-TextSha256HexV1 -Text $builder.ToString()
        file_count = $relativePaths.Count
    }
}

function Get-PrunedSourceFilesV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)
    $directory = Resolve-SafePathV1 -LiteralPath $LiteralPath -Directory $true
    $files = New-Object System.Collections.ArrayList
    foreach ($entry in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
        if ($entry.PSIsContainer -and $entry.Name -in @("node_modules", "dist", "target")) { continue }
        if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Release source tree contains a non-excluded reparse point."
        }
        if ($entry.PSIsContainer) {
            foreach ($nested in @(Get-PrunedSourceFilesV1 -LiteralPath $entry.FullName)) { $null = $files.Add($nested) }
        }
        else { $null = $files.Add((Get-Item -LiteralPath (Resolve-SafePathV1 -LiteralPath $entry.FullName -Directory $false) -Force)) }
    }
    return @($files)
}

function Get-WorkspaceInputsDigestV1 {
    param([Parameter(Mandatory = $true)][string]$Root)
    $workspace = Resolve-SafePathV1 -LiteralPath $Root -Directory $true
    $files = New-Object System.Collections.ArrayList
    foreach ($relative in @("Cargo.toml", "Cargo.lock", "package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml")) {
        $path = Join-Path $workspace $relative
        if (Test-Path -LiteralPath $path) {
            $null = $files.Add((Get-Item -LiteralPath (Resolve-SafePathV1 -LiteralPath $path -Directory $false) -Force))
        }
    }
    foreach ($relativeRoot in @("configs", "scripts")) {
        foreach ($file in @(Get-SafeFilesV1 -LiteralPath (Join-Path $workspace $relativeRoot))) {
            $null = $files.Add($file)
        }
    }
    foreach ($file in @(Get-PrunedSourceFilesV1 -LiteralPath (Join-Path $workspace "crates"))) { $null = $files.Add($file) }
    return Get-FileSetDigestV1 -BaseRoot $workspace -Files @($files)
}

foreach ($name in @("MIHO_RELEASE_CONTEXT_V1", "MIHO_RELEASE_WORKSPACE_ROOT_V1", "MIHO_RELEASE_STAGING_ROOT_V1")) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, [EnvironmentVariableTarget]::Process))) {
        throw "Direct 'tauri build/bundle' is unsupported. Run the release wrapper with a one-use immutable-staging context."
    }
}
$workspace = Resolve-SafePathV1 -LiteralPath $env:MIHO_RELEASE_WORKSPACE_ROOT_V1 -Directory $true
$staging = Resolve-SafePathV1 -LiteralPath $env:MIHO_RELEASE_STAGING_ROOT_V1 -Directory $true
$contextRoot = Resolve-SafePathV1 -LiteralPath (Join-Path $workspace "target\release\release-context") -Directory $true
$contextPath = Resolve-SafePathV1 -LiteralPath $env:MIHO_RELEASE_CONTEXT_V1 -Directory $false
if (-not [string]::Equals((Split-Path -Parent $contextPath), $contextRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Release context is not a direct child of the trusted context directory."
}
$metadata = Get-Item -LiteralPath $contextPath -Force
if ($metadata.Length -gt 16384) { throw "Release context exceeds its supported size." }
$bytes = [System.IO.File]::ReadAllBytes($contextPath)
if ($bytes.Length -gt 16384) { throw "Release context exceeds its supported size." }
try {
    $utf8 = New-Object System.Text.UTF8Encoding($false, $true)
    $json = $utf8.GetString($bytes)
    $context = $json | ConvertFrom-Json -ErrorAction Stop
}
catch { throw "Release context is not strict UTF-8 JSON." }
if ($null -eq $context -or $context -isnot [pscustomobject]) { throw "Release context must be one JSON object." }
$expectedNames = @(
    "schema_version", "nonce", "workspace_root_sha256", "staging_root_sha256",
    "base_config_sha256", "release_config_sha256", "staged_overlay_sha256",
    "workspace_inputs_sha256", "staging_tree_sha256", "cli_sha256", "sidecar_sha256"
)
if (@($context.PSObject.Properties).Count -ne $expectedNames.Count) { throw "Release context fields are invalid." }
foreach ($name in $expectedNames) {
    if ($null -eq $context.PSObject.Properties[$name] -or -not ($context.$name -is [string])) { throw "Release context fields are invalid." }
}
$ordered = [ordered]@{}
foreach ($name in $expectedNames) { $ordered[$name] = [string]$context.$name }
$canonical = ([pscustomobject]$ordered | ConvertTo-Json -Compress) + "`n"
if ($json -cne $canonical) { throw "Release context is non-canonical, duplicated, or contains unknown fields." }
if ($context.schema_version -cne "miho-tauri-release-context-v1" -or $context.nonce -notmatch '^[0-9a-f]{32}$') {
    throw "Release context identity is invalid."
}
if ([System.IO.Path]::GetFileName($contextPath) -cne "tauri-release-$($context.nonce).json") {
    throw "Release context nonce does not bind its file name."
}
foreach ($name in $expectedNames | Where-Object { $_ -like "*_sha256" }) {
    if ([string]$context.$name -notmatch '^[0-9a-f]{64}$') { throw "Release context hash is invalid." }
}
$workspaceIdentity = [System.IO.Path]::GetFullPath($workspace).TrimEnd("\", "/").ToLowerInvariant()
$stagingIdentity = [System.IO.Path]::GetFullPath($staging).TrimEnd("\", "/").ToLowerInvariant()
if ((Get-TextSha256HexV1 -Text $workspaceIdentity) -cne $context.workspace_root_sha256 -or
    (Get-TextSha256HexV1 -Text $stagingIdentity) -cne $context.staging_root_sha256) {
    throw "Release context belongs to another workspace or staging tree."
}

$baseConfigPath = Resolve-SafePathV1 -LiteralPath (Join-Path $workspace "crates\miho-desktop\src-tauri\tauri.conf.json") -Directory $false
$releaseConfigPath = Resolve-SafePathV1 -LiteralPath (Join-Path $workspace "crates\miho-desktop\src-tauri\tauri.release.conf.json") -Directory $false
$overlayPath = Resolve-SafePathV1 -LiteralPath (Join-Path $staging "tauri.release.staged.conf.json") -Directory $false
$cliPath = Resolve-SafePathV1 -LiteralPath (Join-Path $workspace "target\release\miho.exe") -Directory $false
$sidecars = @(Get-SafeFilesV1 -LiteralPath (Join-Path $staging "sidecars") | Where-Object { $_.Name -like "miho-*.exe" })
if ($sidecars.Count -ne 1) { throw "Immutable staging must contain exactly one release sidecar." }
$tree = Get-FileSetDigestV1 -BaseRoot $staging -Files @(Get-SafeFilesV1 -LiteralPath $staging)
$workspaceInputs = Get-WorkspaceInputsDigestV1 -Root $workspace
$actual = @{
    base_config_sha256 = Get-Sha256HexV1 -LiteralPath $baseConfigPath
    release_config_sha256 = Get-Sha256HexV1 -LiteralPath $releaseConfigPath
    staged_overlay_sha256 = Get-Sha256HexV1 -LiteralPath $overlayPath
    workspace_inputs_sha256 = $workspaceInputs.digest
    staging_tree_sha256 = $tree.digest
    cli_sha256 = Get-Sha256HexV1 -LiteralPath $cliPath
    sidecar_sha256 = Get-Sha256HexV1 -LiteralPath $sidecars[0].FullName
}
foreach ($name in $actual.Keys) {
    if ([string]$actual[$name] -cne [string]$context.$name) { throw "Release context hash no longer matches immutable inputs." }
}
if ($actual.cli_sha256 -cne $actual.sidecar_sha256) { throw "Release sidecar is stale or does not match miho.exe." }

$baseConfig = Read-StrictJsonFileV1 -LiteralPath $baseConfigPath
$releasePolicy = Read-StrictJsonFileV1 -LiteralPath $releaseConfigPath
$overlay = Read-StrictJsonFileV1 -LiteralPath $overlayPath
if ($baseConfig.bundle.active -ne $false -or @($baseConfig.bundle.targets).Count -ne 0 -or
    $releasePolicy.bundle.active -ne $false -or @($releasePolicy.bundle.targets).Count -ne 0) {
    throw "Repository Tauri configs must be incapable of producing a bundle without generated immutable staging."
}
$expectedSidecarBase = $sidecars[0].FullName.Substring(0, $sidecars[0].FullName.Length - ("-" + ($sidecars[0].BaseName -replace '^miho-', '') + ".exe").Length)
if ($overlay.bundle.active -ne $true) { throw "Generated release overlay is not bundle-active." }
if (@($overlay.bundle.targets).Count -ne 1 -or [string]$overlay.bundle.targets[0] -cne "nsis") {
    throw "Generated release overlay has invalid bundle targets."
}
if (@($overlay.bundle.externalBin).Count -ne 1 -or
    -not ([string]::Equals([string]$overlay.bundle.externalBin[0], $expectedSidecarBase, [System.StringComparison]::OrdinalIgnoreCase))) {
    throw "Generated release overlay has an invalid sidecar mapping."
}
if (-not ([string]::Equals([string]$overlay.bundle.windows.nsis.template, (Join-Path $staging "packaging\installer.nsi"), [System.StringComparison]::OrdinalIgnoreCase))) {
    throw "Generated release overlay has an invalid NSIS template."
}
if (-not ([string]::Equals([string]$overlay.bundle.windows.nsis.installerHooks, (Join-Path $staging "packaging\installer-hooks.nsh"), [System.StringComparison]::OrdinalIgnoreCase))) {
    throw "Generated release overlay has invalid NSIS hooks."
}
if (-not ([string]::Equals([string]$overlay.build.frontendDist, (Join-Path $staging "frontend-dist"), [System.StringComparison]::OrdinalIgnoreCase))) {
    throw "Generated release overlay has an invalid frontend directory."
}
$verifierPath = Join-Path $staging "packaging\verify_tauri_release_context.ps1"
$verifierInvocation = "& '" + $verifierPath.Replace("'", "''") + "'"
$encodedVerifierInvocation = [System.Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($verifierInvocation))
$expectedVerifierCommand = "powershell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $encodedVerifierInvocation"
if ([string]$overlay.build.beforeBuildCommand -cne $expectedVerifierCommand -or
    [string]$overlay.build.beforeBundleCommand -cne $expectedVerifierCommand) {
    throw "Generated release overlay does not gate both build and bundle with the staged verifier."
}
if (-not ([string]::Equals([string]$overlay.app.security.pattern.options.dir, (Join-Path $staging "isolation"), [System.StringComparison]::OrdinalIgnoreCase))) {
    throw "Generated release overlay has an invalid isolation directory."
}
$expectedResourceMappings = [ordered]@{
    (Join-Path $staging "resources\configs") = "defaults/configs"
    (Join-Path $staging "resources\installer\task_scheduler_v1.ps1") = "installer/task_scheduler_v1.ps1"
    (Join-Path $staging "resources\installer\install_daily_update_task.ps1") = "installer/install_daily_update_task.ps1"
    (Join-Path $staging "resources\installer\uninstall_daily_update_task.ps1") = "installer/uninstall_daily_update_task.ps1"
    (Join-Path $staging "resources\installer\installer_transaction_v1.ps1") = "installer/installer_transaction_v1.ps1"
    (Join-Path $staging "resources\miho-static-ownership-v1.json") = "miho-static-ownership-v1.json"
}
$actualResourceSources = @($overlay.bundle.resources.PSObject.Properties | ForEach-Object { $_.Name })
if ($actualResourceSources.Count -ne $expectedResourceMappings.Count) { throw "Generated release resources are incomplete." }
foreach ($source in $expectedResourceMappings.Keys) {
    $matches = @($overlay.bundle.resources.PSObject.Properties | Where-Object {
        [string]::Equals([string]$_.Name, [string]$source, [System.StringComparison]::OrdinalIgnoreCase)
    })
    if ($matches.Count -ne 1 -or [string]$matches[0].Value -cne [string]$expectedResourceMappings[$source]) {
        throw "Generated release resources escape immutable staging."
    }
}

# Consume only after every source, staging byte, and generated mapping has been
# revalidated. The wrapper rejects a context that survives the Tauri command.
[System.IO.File]::Delete($contextPath)
if (Test-Path -LiteralPath $contextPath) { throw "Release context could not be consumed." }

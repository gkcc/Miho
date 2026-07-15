[CmdletBinding()]
param(
    [switch]$Release,
    [switch]$NoBundle,
    [switch]$ProjectGatesApproved
)
$ErrorActionPreference = "Stop"
$projectGatesApprovedMode = [bool]$ProjectGatesApproved
if ($projectGatesApprovedMode -and (-not $Release -or $NoBundle)) {
    throw "Project-gate approval requires a full release bundle"
}
$root = Split-Path -Parent $PSScriptRoot
$desktop = Join-Path $root "crates\miho-desktop"
$node = if ($env:CODEX_NODE) { $env:CODEX_NODE } else { (Get-Command node -ErrorAction Stop).Source }
. (Join-Path $PSScriptRoot "native_command.ps1")

function Get-Sha256Hex {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LiteralPath
    )
    $stream = [System.IO.File]::OpenRead($LiteralPath)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha256.ComputeHash($stream)
        return (($digest | ForEach-Object { $_.ToString("x2") }) -join "")
    }
    finally {
        $sha256.Dispose()
        $stream.Dispose()
    }
}

function Assert-PathBelow {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LiteralPath,

        [Parameter(Mandatory = $true)]
        [string]$Parent
    )
    $full = [System.IO.Path]::GetFullPath($LiteralPath)
    $fullParent = [System.IO.Path]::GetFullPath($Parent).TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    if (-not $full.StartsWith($fullParent, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Release output path escapes its expected parent"
    }
    return $full
}

function Assert-NoReparseChainV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $full = [System.IO.Path]::GetFullPath($LiteralPath)
    $rootPath = [System.IO.Path]::GetPathRoot($full)
    if ([string]::IsNullOrWhiteSpace($rootPath)) {
        throw "Release path has no filesystem root"
    }
    $current = $rootPath
    $separators = [char[]]@(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    foreach ($component in $full.Substring($rootPath.Length).Split($separators, [System.StringSplitOptions]::RemoveEmptyEntries)) {
        $current = Join-Path $current $component
        if (-not (Test-Path -LiteralPath $current)) { break }
        $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Release path contains a reparse point"
        }
    }
    return $full
}

function Resolve-SafeFileV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $full = Assert-NoReparseChainV1 -LiteralPath $LiteralPath
    $item = Get-Item -LiteralPath $full -Force -ErrorAction Stop
    if ($item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Release input is not a normal file"
    }
    return $item.FullName
}

function Resolve-SafeDirectoryV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $full = Assert-NoReparseChainV1 -LiteralPath $LiteralPath
    $item = Get-Item -LiteralPath $full -Force -ErrorAction Stop
    if (-not $item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Release input is not a normal directory"
    }
    return $item.FullName
}

function Assert-MihoTauriCustomProtocolFeatureV1 {
    param([Parameter(Mandatory = $true)][string]$Root)

    $workspace = Resolve-SafeDirectoryV1 -LiteralPath $Root
    $manifest = Resolve-SafeFileV1 -LiteralPath (Join-Path $workspace "crates\miho-desktop\src-tauri\Cargo.toml")
    $text = [System.IO.File]::ReadAllText($manifest)
    $featureTable = [System.Text.RegularExpressions.Regex]::Match(
        $text,
        '(?ms)^\[features\][ \t]*\r?\n(?<body>.*?)(?=^\[|\z)'
    )
    if (-not $featureTable.Success) {
        throw "Desktop Cargo manifest does not declare a [features] table"
    }
    $customProtocol = [System.Text.RegularExpressions.Regex]::Match(
        $featureTable.Groups["body"].Value,
        '(?m)^custom-protocol[ \t]*=[ \t]*\[[ \t]*"tauri/custom-protocol"[ \t]*\][ \t]*(?:#.*)?$'
    )
    if (-not $customProtocol.Success) {
        throw "Desktop Cargo feature custom-protocol must map exactly to tauri/custom-protocol"
    }
}

function Ensure-SafeDirectoryV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $full = Assert-NoReparseChainV1 -LiteralPath $LiteralPath
    if (-not (Test-Path -LiteralPath $full)) {
        $parent = Split-Path -Parent $full
        $null = Resolve-SafeDirectoryV1 -LiteralPath $parent
        New-Item -ItemType Directory -Path $full -ErrorAction Stop | Out-Null
    }
    return Resolve-SafeDirectoryV1 -LiteralPath $full
}

function Copy-MihoSafeTreeV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    $sourceDirectory = Resolve-SafeDirectoryV1 -LiteralPath $Source
    if (Test-Path -LiteralPath $Destination) {
        throw "Release copy destination already exists"
    }
    New-Item -ItemType Directory -Path $Destination -ErrorAction Stop | Out-Null
    $destinationDirectory = Resolve-SafeDirectoryV1 -LiteralPath $Destination
    foreach ($entry in @(Get-ChildItem -LiteralPath $sourceDirectory -Force -ErrorAction Stop)) {
        if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Release source tree contains a reparse point"
        }
        $target = Join-Path $destinationDirectory $entry.Name
        if ($entry.PSIsContainer) {
            Copy-MihoSafeTreeV1 -Source $entry.FullName -Destination $target
        }
        else {
            $sourceFile = Resolve-SafeFileV1 -LiteralPath $entry.FullName
            Copy-Item -LiteralPath $sourceFile -Destination $target -ErrorAction Stop
            $targetFile = Resolve-SafeFileV1 -LiteralPath $target
            if ((Get-Sha256Hex -LiteralPath $sourceFile) -cne (Get-Sha256Hex -LiteralPath $targetFile)) {
                throw "Release source copy hash mismatch"
            }
        }
    }
}

function Remove-MihoSafeTreeV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    if (-not (Test-Path -LiteralPath $LiteralPath)) { return }
    $directory = Resolve-SafeDirectoryV1 -LiteralPath $LiteralPath
    foreach ($entry in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
        if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Release cleanup refused a reparse point"
        }
        if ($entry.PSIsContainer) {
            Remove-MihoSafeTreeV1 -LiteralPath $entry.FullName
        }
        else {
            $file = Resolve-SafeFileV1 -LiteralPath $entry.FullName
            Remove-Item -LiteralPath $file -Force -ErrorAction Stop
        }
    }
    if (@(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop).Count -ne 0) {
        throw "Release cleanup directory is not empty"
    }
    Remove-Item -LiteralPath $directory -Force -ErrorAction Stop
}

function Remove-MihoReleaseScratchTreeV1 {
    param(
        [Parameter(Mandatory = $true)][string]$LiteralPath,
        [Parameter(Mandatory = $true)][string]$Parent
    )

    $full = Assert-PathBelow -LiteralPath $LiteralPath -Parent $Parent
    if (-not (Test-Path -LiteralPath $full)) { return }
    $item = Get-Item -LiteralPath $full -Force -ErrorAction Stop
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        # pnpm deliberately builds its isolated dependency graph with junctions.
        # Delete the link object without enumerating or resolving its target.
        $isDirectoryLink = $item.PSIsContainer -or
            (($item.Attributes -band [System.IO.FileAttributes]::Directory) -ne 0)
        if ($isDirectoryLink) {
            [System.IO.Directory]::Delete($full, $false)
        }
        else {
            [System.IO.File]::Delete($full)
        }
        if ($null -ne (Get-Item -LiteralPath $full -Force -ErrorAction SilentlyContinue)) {
            throw "Release scratch reparse point could not be unlinked"
        }
        return
    }
    if (-not $item.PSIsContainer) {
        Remove-Item -LiteralPath $full -Force -ErrorAction Stop
        return
    }
    foreach ($entry in @(Get-ChildItem -LiteralPath $full -Force -ErrorAction Stop)) {
        Remove-MihoReleaseScratchTreeV1 -LiteralPath $entry.FullName -Parent $Parent
    }
    if (@(Get-ChildItem -LiteralPath $full -Force -ErrorAction Stop).Count -ne 0) {
        throw "Release scratch directory is not empty"
    }
    [System.IO.Directory]::Delete($full, $false)
}

function Clear-MihoReleaseScratchV1 {
    param([Parameter(Mandatory = $true)][string]$Root)

    $workspace = Resolve-SafeDirectoryV1 -LiteralPath $Root
    $releaseRoot = Join-Path $workspace "target\release"
    if (-not (Test-Path -LiteralPath $releaseRoot)) { return }
    $releaseDirectory = Resolve-SafeDirectoryV1 -LiteralPath $releaseRoot
    foreach ($name in @("release-workspace", "release-staging")) {
        $candidate = Assert-PathBelow -LiteralPath (Join-Path $releaseDirectory $name) -Parent $releaseDirectory
        if (-not (Test-Path -LiteralPath $candidate)) { continue }
        $scratch = Resolve-SafeDirectoryV1 -LiteralPath $candidate
        foreach ($entry in @(Get-ChildItem -LiteralPath $scratch -Force -ErrorAction Stop)) {
            if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                Remove-MihoReleaseScratchTreeV1 -LiteralPath $entry.FullName -Parent $scratch
                continue
            }
            if (-not $entry.PSIsContainer) {
                throw "Release scratch parent contains an unexpected file"
            }
            Remove-MihoReleaseScratchTreeV1 -LiteralPath $entry.FullName -Parent $scratch
        }
        if (@(Get-ChildItem -LiteralPath $scratch -Force -ErrorAction Stop).Count -ne 0) {
            throw "Release scratch parent is not empty"
        }
        Remove-Item -LiteralPath $scratch -Force -ErrorAction Stop
    }
}

function Get-MihoSafeFilesV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $directory = Resolve-SafeDirectoryV1 -LiteralPath $LiteralPath
    $files = New-Object System.Collections.ArrayList
    foreach ($entry in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
        if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Release tree contains a reparse point"
        }
        if ($entry.PSIsContainer) {
            foreach ($nested in @(Get-MihoSafeFilesV1 -LiteralPath $entry.FullName)) {
                $null = $files.Add($nested)
            }
        }
        else {
            $null = $files.Add((Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $entry.FullName) -Force -ErrorAction Stop))
        }
    }
    return @($files)
}

function Sort-MihoStringsOrdinalV1 {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Values
    )

    $sorted = New-Object 'System.Collections.Generic.List[string]'
    foreach ($value in @($Values)) {
        if ($null -eq $value) { throw "Ordinal sort input contains a null string" }
        $sorted.Add([string]$value)
    }
    $sorted.Sort([System.StringComparer]::Ordinal)
    return @($sorted)
}

function Sort-MihoObjectsByStringPropertyOrdinalV1 {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]]$Values,

        [Parameter(Mandatory = $true)]
        [string]$Property
    )

    $keys = New-Object 'System.Collections.Generic.List[string]'
    $byKey = @{}
    foreach ($value in @($Values)) {
        if ($null -eq $value -or $null -eq $value.PSObject.Properties[$Property]) {
            throw "Ordinal object sort input is missing its key property"
        }
        $key = [string]$value.$Property
        if ($byKey.ContainsKey($key)) {
            throw "Ordinal object sort input contains a duplicate key"
        }
        $keys.Add($key)
        $byKey[$key] = $value
    }
    $keys.Sort([System.StringComparer]::Ordinal)
    return @(
        foreach ($key in $keys) {
            $byKey[$key]
        }
    )
}

function Get-MihoFileSetDigestV1 {
    param(
        [Parameter(Mandatory = $true)][string]$BaseRoot,
        [Parameter(Mandatory = $true)][object[]]$Files
    )

    $base = (Resolve-SafeDirectoryV1 -LiteralPath $BaseRoot).TrimEnd("\", "/")
    $prefix = $base + [System.IO.Path]::DirectorySeparatorChar
    $relativePaths = New-Object 'System.Collections.Generic.List[string]'
    $byRelative = @{}
    foreach ($entry in @($Files)) {
        $file = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath ([string]$entry.FullName)) -Force -ErrorAction Stop
        if (-not $file.FullName.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Release fingerprint input escapes its base root"
        }
        $relative = $file.FullName.Substring($prefix.Length).Replace("\", "/")
        if ($byRelative.ContainsKey($relative)) {
            throw "Release fingerprint contains a duplicate relative path"
        }
        $relativePaths.Add($relative)
        $byRelative[$relative] = $file
    }
    $relativePaths.Sort([System.StringComparer]::Ordinal)
    $builder = New-Object System.Text.StringBuilder
    foreach ($relative in $relativePaths) {
        $file = $byRelative[$relative]
        $hash = Get-Sha256Hex -LiteralPath $file.FullName
        $null = $builder.Append($relative.Length).Append(":").Append($relative).Append(":")
        $null = $builder.Append([int64]$file.Length).Append(":").Append($hash).Append("`n")
    }
    return [pscustomobject][ordered]@{
        digest = Get-Sha256HexForTextV1 -Text $builder.ToString()
        file_count = $relativePaths.Count
    }
}

function Get-MihoTreeDigestV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $rootDirectory = Resolve-SafeDirectoryV1 -LiteralPath $LiteralPath
    return Get-MihoFileSetDigestV1 -BaseRoot $rootDirectory -Files @(Get-MihoSafeFilesV1 -LiteralPath $rootDirectory)
}

function Get-MihoDependencyTreeDigestV1 {
    param([Parameter(Mandatory = $true)][string]$Root)

    $workspace = Resolve-SafeDirectoryV1 -LiteralPath $Root
    $workspacePrefix = $workspace.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    $roots = @(
        (Join-Path $workspace "node_modules")
        (Join-Path $workspace "crates\miho-desktop\node_modules")
    )
    $dependencyRoots = @(
        foreach ($rootPath in $roots) {
            Resolve-SafeDirectoryV1 -LiteralPath $rootPath
        }
    )
    $workspacePackageRoot = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $workspace "crates\miho-desktop")
    $records = New-Object 'System.Collections.Generic.List[string]'
    $stack = New-Object 'System.Collections.Generic.Stack[string]'
    foreach ($rootDirectory in $dependencyRoots) {
        $stack.Push($rootDirectory)
    }
    $fileCount = 0
    while ($stack.Count -gt 0) {
        $directory = $stack.Pop()
        foreach ($entry in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
            if (-not $entry.FullName.StartsWith($workspacePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Dependency tree entry escapes the isolated workspace"
            }
            $relative = $entry.FullName.Substring($workspacePrefix.Length).Replace("\", "/")
            if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                $targets = @($entry.Target)
                if ($targets.Count -ne 1 -or [string]::IsNullOrWhiteSpace([string]$targets[0])) {
                    throw "Dependency tree contains an unresolved reparse target"
                }
                $targetText = [string]$targets[0]
                $targetPath = if ([System.IO.Path]::IsPathRooted($targetText)) {
                    [System.IO.Path]::GetFullPath($targetText)
                }
                else {
                    [System.IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $entry.FullName) $targetText))
                }
                if (-not $targetPath.StartsWith($workspacePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                    throw "Dependency tree reparse target escapes the isolated workspace"
                }
                $targetIsDependencyInternal = $false
                foreach ($dependencyRoot in $dependencyRoots) {
                    $dependencyPrefix = $dependencyRoot.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
                    if ($targetPath.StartsWith($dependencyPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                        $targetIsDependencyInternal = $true
                        break
                    }
                }
                $targetIsExactWorkspacePackage = [string]::Equals(
                    $targetPath.TrimEnd("\", "/"),
                    $workspacePackageRoot.TrimEnd("\", "/"),
                    [System.StringComparison]::OrdinalIgnoreCase
                )
                if (-not $targetIsDependencyInternal -and -not $targetIsExactWorkspacePackage) {
                    throw "Dependency tree reparse target is outside the frozen dependency target set"
                }
                if ($targetIsExactWorkspacePackage) {
                    $null = Resolve-SafeDirectoryV1 -LiteralPath $targetPath
                }
                else {
                    $targetItem = Get-Item -LiteralPath $targetPath -Force -ErrorAction Stop
                    if ($targetItem.PSIsContainer) {
                        $null = Resolve-SafeDirectoryV1 -LiteralPath $targetPath
                    }
                    else {
                        $null = Resolve-SafeFileV1 -LiteralPath $targetPath
                    }
                }
                $relativeTarget = $targetPath.Substring($workspacePrefix.Length).Replace("\", "/")
                $records.Add("L:$($relative.Length):${relative}:$($relativeTarget.Length):$relativeTarget")
            }
            elseif ($entry.PSIsContainer) {
                $records.Add("D:$($relative.Length):$relative")
                $stack.Push($entry.FullName)
            }
            else {
                $file = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $entry.FullName) -Force -ErrorAction Stop
                $hash = Get-Sha256Hex -LiteralPath $file.FullName
                $records.Add("F:$($relative.Length):${relative}:$([int64]$file.Length):$hash")
                $fileCount += 1
            }
            if ($records.Count -gt 200000) { throw "Dependency tree exceeds its supported entry count" }
        }
    }
    $records.Sort([System.StringComparer]::Ordinal)
    return [pscustomobject][ordered]@{
        digest = Get-Sha256HexForTextV1 -Text ([string]::Join("`n", $records))
        entry_count = [int]$records.Count
        file_count = [int]$fileCount
    }
}

function Remove-MihoEmptyViteConfigScratchV1 {
    param([Parameter(Mandatory = $true)][string]$Root)

    $workspace = Resolve-SafeDirectoryV1 -LiteralPath $Root
    $desktopNodeModules = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $workspace "crates\miho-desktop\node_modules")
    $scratchPath = Join-Path $desktopNodeModules ".vite-temp"
    if (-not (Test-Path -LiteralPath $scratchPath)) { return }

    $scratch = Resolve-SafeDirectoryV1 -LiteralPath $scratchPath
    if (@(Get-ChildItem -LiteralPath $scratch -Force -ErrorAction Stop).Count -ne 0) {
        throw "Vite config scratch is not empty after the frontend build"
    }
    [System.IO.Directory]::Delete($scratch)
    if (Test-Path -LiteralPath $scratchPath) {
        throw "Empty Vite config scratch could not be removed"
    }
}

function Get-MihoPrunedSourceFilesV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $directory = Resolve-SafeDirectoryV1 -LiteralPath $LiteralPath
    $files = New-Object System.Collections.ArrayList
    foreach ($entry in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
        if ($entry.PSIsContainer -and $entry.Name -in @("node_modules", "dist", "target")) {
            continue
        }
        if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Release source tree contains a non-excluded reparse point"
        }
        if ($entry.PSIsContainer) {
            foreach ($nested in @(Get-MihoPrunedSourceFilesV1 -LiteralPath $entry.FullName)) {
                $null = $files.Add($nested)
            }
        }
        else {
            $null = $files.Add((Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $entry.FullName) -Force -ErrorAction Stop))
        }
    }
    return @($files)
}

function Copy-MihoPrunedSourceTreeV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    $sourceDirectory = Resolve-SafeDirectoryV1 -LiteralPath $Source
    if (Test-Path -LiteralPath $Destination) { throw "Isolated source destination already exists" }
    New-Item -ItemType Directory -Path $Destination -ErrorAction Stop | Out-Null
    $destinationDirectory = Resolve-SafeDirectoryV1 -LiteralPath $Destination
    foreach ($entry in @(Get-ChildItem -LiteralPath $sourceDirectory -Force -ErrorAction Stop)) {
        if ($entry.PSIsContainer -and $entry.Name -in @("node_modules", "dist", "target")) { continue }
        if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Isolated release source contains a non-excluded reparse point"
        }
        $target = Join-Path $destinationDirectory $entry.Name
        if ($entry.PSIsContainer) {
            Copy-MihoPrunedSourceTreeV1 -Source $entry.FullName -Destination $target
        }
        else {
            $sourceFile = Resolve-SafeFileV1 -LiteralPath $entry.FullName
            Copy-Item -LiteralPath $sourceFile -Destination $target -ErrorAction Stop
            $targetFile = Resolve-SafeFileV1 -LiteralPath $target
            if ((Get-Sha256Hex -LiteralPath $sourceFile) -cne (Get-Sha256Hex -LiteralPath $targetFile)) {
                throw "Isolated release source copy hash mismatch"
            }
        }
    }
}

function New-MihoIsolatedReleaseWorkspaceV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)]$ExpectedInputs
    )

    $workspace = Resolve-SafeDirectoryV1 -LiteralPath $Root
    $targetRoot = Ensure-SafeDirectoryV1 -LiteralPath (Join-Path $workspace "target")
    $releaseRoot = Ensure-SafeDirectoryV1 -LiteralPath (Join-Path $targetRoot "release")
    $parent = Ensure-SafeDirectoryV1 -LiteralPath (Join-Path $releaseRoot "release-workspace")
    $isolated = Assert-PathBelow `
        -LiteralPath (Join-Path $parent ("build-" + [guid]::NewGuid().ToString("N"))) `
        -Parent $parent
    New-Item -ItemType Directory -Path $isolated -ErrorAction Stop | Out-Null
    $isolated = Resolve-SafeDirectoryV1 -LiteralPath $isolated
    try {
        foreach ($relative in @("Cargo.toml", "Cargo.lock", "package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml")) {
            $source = Resolve-SafeFileV1 -LiteralPath (Join-Path $workspace $relative)
            $destination = Join-Path $isolated $relative
            Copy-Item -LiteralPath $source -Destination $destination -ErrorAction Stop
            if ((Get-Sha256Hex -LiteralPath $source) -cne (Get-Sha256Hex -LiteralPath $destination)) {
                throw "Isolated release root input copy hash mismatch"
            }
        }
        Copy-MihoSafeTreeV1 -Source (Join-Path $workspace "configs") -Destination (Join-Path $isolated "configs")
        Copy-MihoSafeTreeV1 -Source (Join-Path $workspace "scripts") -Destination (Join-Path $isolated "scripts")
        Copy-MihoPrunedSourceTreeV1 -Source (Join-Path $workspace "crates") -Destination (Join-Path $isolated "crates")
        $inputs = Get-MihoWorkspaceReleaseInputsDigestV1 -Root $isolated
        if ([string]$inputs.digest -cne [string]$ExpectedInputs.digest -or
            [int]$inputs.file_count -ne [int]$ExpectedInputs.file_count) {
            throw "Isolated release workspace does not exactly match frozen inputs"
        }
        return [pscustomobject][ordered]@{
            Root = $isolated
            Desktop = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $isolated "crates\miho-desktop")
            Inputs = $inputs
        }
    }
    catch {
        if (Test-Path -LiteralPath $isolated) { Remove-MihoSafeTreeV1 -LiteralPath $isolated }
        throw
    }
}

function Get-MihoWorkspaceReleaseInputsDigestV1 {
    param([Parameter(Mandatory = $true)][string]$Root)

    $workspace = Resolve-SafeDirectoryV1 -LiteralPath $Root
    $files = New-Object System.Collections.ArrayList
    foreach ($relative in @("Cargo.toml", "Cargo.lock", "package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml")) {
        $path = Join-Path $workspace $relative
        if (Test-Path -LiteralPath $path) {
            $null = $files.Add((Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $path) -Force -ErrorAction Stop))
        }
    }
    foreach ($relativeRoot in @("configs", "scripts")) {
        $directory = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $workspace $relativeRoot)
        foreach ($file in @(Get-MihoSafeFilesV1 -LiteralPath $directory)) {
            $null = $files.Add($file)
        }
    }
    foreach ($file in @(Get-MihoPrunedSourceFilesV1 -LiteralPath (Join-Path $workspace "crates"))) {
        $null = $files.Add($file)
    }
    return Get-MihoFileSetDigestV1 -BaseRoot $workspace -Files @($files)
}

function Initialize-MihoDeterministicZipWriterV1 {
    if ($null -ne ("MihoDeterministicZipWriterV1" -as [type])) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

public static class MihoDeterministicZipWriterV1
{
    private sealed class EntryRecord
    {
        public byte[] Name;
        public uint Crc32;
        public uint Size;
        public uint LocalOffset;
    }

    private static readonly uint[] CrcTable = BuildCrcTable();

    private static uint[] BuildCrcTable()
    {
        uint[] table = new uint[256];
        for (uint index = 0; index < table.Length; index++)
        {
            uint value = index;
            for (int bit = 0; bit < 8; bit++)
            {
                value = (value & 1U) != 0U
                    ? 0xEDB88320U ^ (value >> 1)
                    : value >> 1;
            }
            table[index] = value;
        }
        return table;
    }

    private static void WriteUInt16(Stream stream, ushort value)
    {
        stream.WriteByte((byte)(value & 0xff));
        stream.WriteByte((byte)((value >> 8) & 0xff));
    }

    private static void WriteUInt32(Stream stream, uint value)
    {
        stream.WriteByte((byte)(value & 0xff));
        stream.WriteByte((byte)((value >> 8) & 0xff));
        stream.WriteByte((byte)((value >> 16) & 0xff));
        stream.WriteByte((byte)((value >> 24) & 0xff));
    }

    private static void WriteBytes(Stream stream, byte[] bytes)
    {
        stream.Write(bytes, 0, bytes.Length);
    }

    public static void Create(string outputPath, string[] entryNames, string[] sourcePaths)
    {
        if (entryNames == null || sourcePaths == null || entryNames.Length != sourcePaths.Length)
            throw new InvalidDataException("Deterministic ZIP input arrays are invalid.");
        if (entryNames.Length == 0 || entryNames.Length > ushort.MaxValue)
            throw new InvalidDataException("Deterministic ZIP entry count exceeds the non-ZIP64 contract.");

        UTF8Encoding utf8 = new UTF8Encoding(false, true);
        List<EntryRecord> records = new List<EntryRecord>(entryNames.Length);
        using (FileStream output = new FileStream(outputPath, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None))
        {
            byte[] buffer = new byte[1024 * 1024];
            for (int index = 0; index < entryNames.Length; index++)
            {
                byte[] name = utf8.GetBytes(entryNames[index]);
                if (name.Length == 0 || name.Length > ushort.MaxValue)
                    throw new InvalidDataException("Deterministic ZIP entry name exceeds the non-ZIP64 contract.");
                long localOffsetLong = output.Position;
                if (localOffsetLong > uint.MaxValue)
                    throw new InvalidDataException("Deterministic ZIP offset exceeds the non-ZIP64 contract.");

                using (FileStream input = new FileStream(sourcePaths[index], FileMode.Open, FileAccess.Read, FileShare.Read))
                {
                    long sizeLong = input.Length;
                    if (sizeLong < 0 || sizeLong > uint.MaxValue)
                        throw new InvalidDataException("Deterministic ZIP entry exceeds the non-ZIP64 contract.");
                    uint size = (uint)sizeLong;

                    WriteUInt32(output, 0x04034b50U);
                    WriteUInt16(output, 20);
                    WriteUInt16(output, 0x0800);
                    WriteUInt16(output, 0);
                    WriteUInt16(output, 0);
                    WriteUInt16(output, 0x0021);
                    WriteUInt32(output, 0);
                    WriteUInt32(output, size);
                    WriteUInt32(output, size);
                    WriteUInt16(output, (ushort)name.Length);
                    WriteUInt16(output, 0);
                    WriteBytes(output, name);

                    uint crc = 0xffffffffU;
                    long copied = 0;
                    int read;
                    while ((read = input.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        output.Write(buffer, 0, read);
                        copied += read;
                        for (int byteIndex = 0; byteIndex < read; byteIndex++)
                            crc = CrcTable[(crc ^ buffer[byteIndex]) & 0xffU] ^ (crc >> 8);
                    }
                    if (copied != sizeLong || input.Length != sizeLong)
                        throw new IOException("Deterministic ZIP source changed while it was read.");
                    crc ^= 0xffffffffU;
                    long end = output.Position;
                    output.Position = localOffsetLong + 14;
                    WriteUInt32(output, crc);
                    output.Position = end;
                    records.Add(new EntryRecord
                    {
                        Name = name,
                        Crc32 = crc,
                        Size = size,
                        LocalOffset = (uint)localOffsetLong
                    });
                }
            }

            long centralOffsetLong = output.Position;
            if (centralOffsetLong > uint.MaxValue)
                throw new InvalidDataException("Deterministic ZIP central offset exceeds the non-ZIP64 contract.");
            foreach (EntryRecord record in records)
            {
                WriteUInt32(output, 0x02014b50U);
                WriteUInt16(output, 20);
                WriteUInt16(output, 20);
                WriteUInt16(output, 0x0800);
                WriteUInt16(output, 0);
                WriteUInt16(output, 0);
                WriteUInt16(output, 0x0021);
                WriteUInt32(output, record.Crc32);
                WriteUInt32(output, record.Size);
                WriteUInt32(output, record.Size);
                WriteUInt16(output, (ushort)record.Name.Length);
                WriteUInt16(output, 0);
                WriteUInt16(output, 0);
                WriteUInt16(output, 0);
                WriteUInt16(output, 0);
                WriteUInt32(output, 0);
                WriteUInt32(output, record.LocalOffset);
                WriteBytes(output, record.Name);
            }
            long centralSizeLong = output.Position - centralOffsetLong;
            if (centralSizeLong > uint.MaxValue || output.Position > uint.MaxValue)
                throw new InvalidDataException("Deterministic ZIP central directory exceeds the non-ZIP64 contract.");

            WriteUInt32(output, 0x06054b50U);
            WriteUInt16(output, 0);
            WriteUInt16(output, 0);
            WriteUInt16(output, (ushort)records.Count);
            WriteUInt16(output, (ushort)records.Count);
            WriteUInt32(output, (uint)centralSizeLong);
            WriteUInt32(output, (uint)centralOffsetLong);
            WriteUInt16(output, 0);
            output.Flush(true);
        }
    }
}
'@
}

function New-MihoDeterministicZipV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [Parameter(Mandatory = $true)][string]$OutputPath
    )

    $sourceRoot = Resolve-SafeDirectoryV1 -LiteralPath $Directory
    $outputFull = [System.IO.Path]::GetFullPath($OutputPath)
    if (Test-Path -LiteralPath $outputFull) {
        throw "Deterministic ZIP output already exists"
    }
    $outputParent = Resolve-SafeDirectoryV1 -LiteralPath (Split-Path -Parent $outputFull)
    $null = Assert-PathBelow -LiteralPath $outputFull -Parent $outputParent

    $prefix = $sourceRoot.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    $relativePaths = New-Object 'System.Collections.Generic.List[string]'
    $fullPaths = New-Object 'System.Collections.Generic.List[string]'
    $filesByRelative = @{}
    foreach ($file in @(Get-MihoSafeFilesV1 -LiteralPath $sourceRoot)) {
        $relative = $file.FullName.Substring($prefix.Length).Replace("\", "/")
        Assert-MihoReleaseRelativePathV1 -Path $relative -Label "deterministic_zip.entry"
        if ($filesByRelative.ContainsKey($relative)) {
            throw "Deterministic ZIP contains a duplicate path"
        }
        $relativePaths.Add($relative)
        $filesByRelative[$relative] = $file.FullName
    }
    $relativePaths.Sort([System.StringComparer]::Ordinal)
    foreach ($relative in $relativePaths) {
        $fullPaths.Add([string]$filesByRelative[$relative])
    }

    try {
        Initialize-MihoDeterministicZipWriterV1
        [MihoDeterministicZipWriterV1]::Create(
            $outputFull,
            [string[]]$relativePaths.ToArray(),
            [string[]]$fullPaths.ToArray()
        )
        return Resolve-SafeFileV1 -LiteralPath $outputFull
    }
    catch {
        if (Test-Path -LiteralPath $outputFull) {
            Remove-Item -LiteralPath $outputFull -Force -ErrorAction SilentlyContinue
        }
        throw
    }
}

function Assert-MihoZipMatchesDirectoryV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Archive,
        [Parameter(Mandatory = $true)][string]$Directory
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archivePath = Resolve-SafeFileV1 -LiteralPath $Archive
    $directoryPath = Resolve-SafeDirectoryV1 -LiteralPath $Directory
    $prefix = $directoryPath.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    $expected = @{}
    foreach ($file in @(Get-MihoSafeFilesV1 -LiteralPath $directoryPath)) {
        $relative = $file.FullName.Substring($prefix.Length).Replace("\", "/")
        $expected[$relative] = $file
    }
    $seen = @{}
    $zip = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
    try {
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName.Replace("\", "/")
            if ([string]::IsNullOrWhiteSpace($name) -or $name.StartsWith("/", [System.StringComparison]::Ordinal) -or
                $name.Split('/') -contains "..") {
                throw "Portable archive contains an unsafe entry"
            }
            if ($name.EndsWith("/", [System.StringComparison]::Ordinal)) { continue }
            if (-not $expected.ContainsKey($name) -or $seen.ContainsKey($name)) {
                throw "Portable archive file set differs from its content-addressed directory"
            }
            $file = $expected[$name]
            if ([int64]$entry.Length -ne [int64]$file.Length) {
                throw "Portable archive file size differs from its content-addressed directory"
            }
            $stream = $entry.Open()
            $algorithm = [System.Security.Cryptography.SHA256]::Create()
            try { $hash = (($algorithm.ComputeHash($stream) | ForEach-Object { $_.ToString("x2") }) -join "") }
            finally { $algorithm.Dispose(); $stream.Dispose() }
            if ($hash -cne (Get-Sha256Hex -LiteralPath $file.FullName)) {
                throw "Portable archive bytes differ from its content-addressed directory"
            }
            $seen[$name] = $true
        }
    }
    finally { $zip.Dispose() }
    if ($seen.Count -ne $expected.Count) {
        throw "Portable archive omits files from its content-addressed directory"
    }
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LiteralPath,

        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Text
    )
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($LiteralPath, $Text, $utf8)
}

function Move-MihoJsonWhitespaceV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Json,
        [Parameter(Mandatory = $true)][ref]$Index
    )

    while ($Index.Value -lt $Json.Length -and
        ($Json[$Index.Value] -eq ' ' -or $Json[$Index.Value] -eq "`t" -or
         $Json[$Index.Value] -eq "`r" -or $Json[$Index.Value] -eq "`n")) {
        $Index.Value += 1
    }
}

function Read-MihoJsonStringTokenV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Json,
        [Parameter(Mandatory = $true)][ref]$Index
    )

    if ($Index.Value -ge $Json.Length -or $Json[$Index.Value] -ne '"') {
        throw "Release JSON object key is invalid"
    }
    $start = $Index.Value
    $Index.Value += 1
    $escaped = $false
    while ($Index.Value -lt $Json.Length) {
        $character = $Json[$Index.Value]
        if ($escaped) {
            $escaped = $false
            $Index.Value += 1
            continue
        }
        if ($character -eq '\') {
            $escaped = $true
            $Index.Value += 1
            continue
        }
        if ($character -eq '"') {
            $Index.Value += 1
            $literal = $Json.Substring($start, $Index.Value - $start)
            try {
                $decodedHolder = ConvertFrom-Json -InputObject ('{"value":' + $literal + '}') -ErrorAction Stop
            }
            catch { throw "Release JSON string token is invalid" }
            $decodedProperties = @($decodedHolder.PSObject.Properties)
            if ($null -eq $decodedHolder -or $decodedHolder -isnot [pscustomobject] -or
                $decodedProperties.Count -ne 1 -or
                -not [string]::Equals([string]$decodedProperties[0].Name, "value", [System.StringComparison]::Ordinal)) {
                throw "Release JSON string token is invalid"
            }
            $decoded = $decodedHolder.value
            if ($decoded -isnot [string]) { throw "Release JSON string token is invalid" }
            return [string]$decoded
        }
        $Index.Value += 1
    }
    throw "Release JSON string token is unterminated"
}

function Read-MihoJsonValueShapeV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Json,
        [Parameter(Mandatory = $true)][ref]$Index
    )

    Move-MihoJsonWhitespaceV1 -Json $Json -Index $Index
    if ($Index.Value -ge $Json.Length) { throw "Release JSON value is incomplete" }
    $character = $Json[$Index.Value]
    if ($character -eq '{') {
        $Index.Value += 1
        $keys = New-Object System.Collections.ArrayList
        Move-MihoJsonWhitespaceV1 -Json $Json -Index $Index
        if ($Index.Value -lt $Json.Length -and $Json[$Index.Value] -eq '}') {
            $Index.Value += 1
            return
        }
        while ($true) {
            Move-MihoJsonWhitespaceV1 -Json $Json -Index $Index
            $key = Read-MihoJsonStringTokenV1 -Json $Json -Index $Index
            foreach ($existing in @($keys)) {
                if ([string]::Equals([string]$existing, $key, [System.StringComparison]::Ordinal)) {
                    throw "Release JSON contains a duplicate object key"
                }
            }
            $null = $keys.Add($key)
            Move-MihoJsonWhitespaceV1 -Json $Json -Index $Index
            if ($Index.Value -ge $Json.Length -or $Json[$Index.Value] -ne ':') {
                throw "Release JSON object separator is invalid"
            }
            $Index.Value += 1
            Read-MihoJsonValueShapeV1 -Json $Json -Index $Index
            Move-MihoJsonWhitespaceV1 -Json $Json -Index $Index
            if ($Index.Value -ge $Json.Length) { throw "Release JSON object is incomplete" }
            if ($Json[$Index.Value] -eq '}') {
                $Index.Value += 1
                return
            }
            if ($Json[$Index.Value] -ne ',') { throw "Release JSON object delimiter is invalid" }
            $Index.Value += 1
        }
    }
    if ($character -eq '[') {
        $Index.Value += 1
        Move-MihoJsonWhitespaceV1 -Json $Json -Index $Index
        if ($Index.Value -lt $Json.Length -and $Json[$Index.Value] -eq ']') {
            $Index.Value += 1
            return
        }
        while ($true) {
            Read-MihoJsonValueShapeV1 -Json $Json -Index $Index
            Move-MihoJsonWhitespaceV1 -Json $Json -Index $Index
            if ($Index.Value -ge $Json.Length) { throw "Release JSON array is incomplete" }
            if ($Json[$Index.Value] -eq ']') {
                $Index.Value += 1
                return
            }
            if ($Json[$Index.Value] -ne ',') { throw "Release JSON array delimiter is invalid" }
            $Index.Value += 1
        }
    }
    if ($character -eq '"') {
        $null = Read-MihoJsonStringTokenV1 -Json $Json -Index $Index
        return
    }
    $start = $Index.Value
    while ($Index.Value -lt $Json.Length) {
        $character = $Json[$Index.Value]
        if ($character -eq ',' -or $character -eq '}' -or $character -eq ']' -or
            $character -eq ' ' -or $character -eq "`t" -or $character -eq "`r" -or $character -eq "`n") {
            break
        }
        $Index.Value += 1
    }
    if ($Index.Value -eq $start) { throw "Release JSON primitive is invalid" }
}

function Assert-MihoJsonUniqueObjectKeysV1 {
    param([Parameter(Mandatory = $true)][string]$Json)

    $index = 0
    Read-MihoJsonValueShapeV1 -Json $Json -Index ([ref]$index)
    Move-MihoJsonWhitespaceV1 -Json $Json -Index ([ref]$index)
    if ($index -ne $Json.Length) { throw "Release JSON contains trailing content" }
}

function Read-MihoStrictJsonFileV1 {
    param(
        [Parameter(Mandatory = $true)][string]$LiteralPath,
        [int64]$MaximumBytes = 1048576
    )
    $path = Resolve-SafeFileV1 -LiteralPath $LiteralPath
    $metadata = Get-Item -LiteralPath $path -Force -ErrorAction Stop
    if ([int64]$metadata.Length -gt $MaximumBytes) { throw "Release JSON exceeds its supported size" }
    $bytes = [System.IO.File]::ReadAllBytes($path)
    if ([int64]$bytes.Length -gt $MaximumBytes -or [int64]$bytes.Length -ne [int64]$metadata.Length) {
        throw "Release JSON exceeds its supported size or changed while reading"
    }
    $secondBytes = [System.IO.File]::ReadAllBytes((Resolve-SafeFileV1 -LiteralPath $path))
    if ([int64]$secondBytes.Length -ne [int64]$bytes.Length -or
        [System.Convert]::ToBase64String($secondBytes) -cne [System.Convert]::ToBase64String($bytes)) {
        throw "Release JSON changed while reading"
    }
    try {
        $decoder = New-Object System.Text.UTF8Encoding($false, $true)
        $json = $decoder.GetString($bytes)
        Assert-MihoJsonUniqueObjectKeysV1 -Json $json
        $value = $json | ConvertFrom-Json -ErrorAction Stop
    }
    catch { throw "Release JSON is not strict UTF-8 JSON" }
    if ($null -eq $value -or $value -isnot [pscustomobject]) { throw "Release JSON must contain one object" }
    return $value
}

function Assert-MihoExactObjectPropertiesV1 {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string[]]$Names
    )
    if ($null -eq $Object -or $Object -isnot [pscustomobject] -or @($Object.PSObject.Properties).Count -ne $Names.Count) {
        throw "Release JSON object fields are invalid"
    }
    $actualNames = @($Object.PSObject.Properties | ForEach-Object { [string]$_.Name })
    foreach ($name in $Names) {
        $matches = @($actualNames | Where-Object {
            [string]::Equals([string]$_, $name, [System.StringComparison]::Ordinal)
        })
        if ($matches.Count -ne 1) { throw "Release JSON object fields are invalid" }
    }
}

function Assert-MihoJsonValueTypeV1 {
    param(
        [Parameter(Mandatory = $true)][AllowNull()][AllowEmptyCollection()]$Value,
        [Parameter(Mandatory = $true)][ValidateSet("string", "integer", "boolean", "array", "object")][string]$Kind,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $valid = switch ($Kind) {
        "string" { $Value -is [string] }
        "integer" { $Value -is [int] -or $Value -is [long] }
        "boolean" { $Value -is [bool] }
        "array" { $Value -is [System.Array] }
        "object" { $Value -is [pscustomobject] }
    }
    if (-not $valid) { throw "Release JSON $Label has an invalid $Kind type" }
}

function Assert-MihoJsonPropertyTypeV1 {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][ValidateSet("string", "integer", "boolean", "array", "object")][string]$Kind,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ($null -eq $Object -or $Object -isnot [pscustomobject]) {
        throw "Release JSON $Label parent is invalid"
    }
    $properties = @($Object.PSObject.Properties | Where-Object {
        [string]::Equals([string]$_.Name, $Name, [System.StringComparison]::Ordinal)
    })
    if ($properties.Count -ne 1) { throw "Release JSON $Label property is missing" }
    Assert-MihoJsonValueTypeV1 -Value $properties[0].Value -Kind $Kind -Label $Label
}

function Get-AuthenticodeStatusV1 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LiteralPath
    )

    try {
        $signature = Get-AuthenticodeSignature -LiteralPath $LiteralPath -ErrorAction Stop
        return [string]$signature.Status
    }
    catch {
        # Some minimal Windows PowerShell environments expose the command name
        # while the Microsoft.PowerShell.Security module itself cannot load.
        # This is evidence that verification was unavailable, never evidence
        # that an unsigned or unverifiable binary is trusted.
        return "Unavailable"
    }
}

function Assert-MihoReleaseRelativePathV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ([string]::IsNullOrWhiteSpace($Path) -or
        [System.IO.Path]::IsPathRooted($Path) -or
        $Path.Contains("\") -or $Path.StartsWith("/", [System.StringComparison]::Ordinal) -or
        $Path.EndsWith("/", [System.StringComparison]::Ordinal) -or
        $Path.Contains("//")) {
        throw "Release JSON $Label contains an unsafe relative path"
    }
    foreach ($segment in $Path.Split('/')) {
        if ([string]::IsNullOrEmpty($segment) -or $segment -ceq "." -or $segment -ceq ".." -or
            $segment.TrimEnd(@(' ', '.')).Length -ne $segment.Length -or
            $segment.IndexOfAny([System.IO.Path]::GetInvalidFileNameChars()) -ge 0) {
            throw "Release JSON $Label contains an unsafe relative path"
        }
        $stem = $segment.Split('.')[0]
        if ($stem -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$') {
            throw "Release JSON $Label contains a reserved Windows path"
        }
    }
}

function Assert-MihoSha256ValueV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ($Value -cnotmatch '^[0-9a-f]{64}$') {
        throw "Release JSON $Label is not a canonical SHA-256 value"
    }
}

function Assert-MihoNoCaseCollidingPathV1 {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$PriorPaths,
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label
    )

    foreach ($prior in $PriorPaths) {
        if ([string]::Equals($prior, $Path, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Release JSON $Label contains a duplicate or case-colliding path"
        }
    }
}

function Assert-MihoPortablePayloadManifestV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [Parameter(Mandatory = $true)][string]$Manifest,
        [Parameter(Mandatory = $true)][string]$ProductVersion,
        [Parameter(Mandatory = $true)][string]$HostTriple
    )

    $payloadRoot = Resolve-SafeDirectoryV1 -LiteralPath $Directory
    $manifestPath = Resolve-SafeFileV1 -LiteralPath $Manifest
    if (-not [string]::Equals(
            [System.IO.Path]::GetDirectoryName($manifestPath),
            $payloadRoot,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -or [System.IO.Path]::GetFileName($manifestPath) -cne "miho-release-files-v1.json") {
        throw "Portable payload manifest is not the canonical payload-root manifest"
    }

    $payload = Read-MihoStrictJsonFileV1 -LiteralPath $manifestPath
    Assert-MihoExactObjectPropertiesV1 -Object $payload -Names @(
        "schema_version", "product_version", "target_triple", "files", "signature_boundary"
    )
    foreach ($field in @("schema_version", "product_version", "target_triple")) {
        Assert-MihoJsonValueTypeV1 -Value $payload.$field -Kind string -Label "portable_manifest.$field"
    }
    Assert-MihoJsonPropertyTypeV1 -Object $payload -Name "files" -Kind array -Label "portable_manifest.files"
    Assert-MihoJsonValueTypeV1 -Value $payload.signature_boundary -Kind object -Label "portable_manifest.signature_boundary"
    if ([string]$payload.schema_version -cne "miho-release-files-v1" -or
        [string]$payload.product_version -cne $ProductVersion -or
        [string]$payload.target_triple -cne $HostTriple) {
        throw "Portable payload manifest identity is invalid"
    }

    $prefix = $payloadRoot.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    $actualFiles = @(Get-MihoSafeFilesV1 -LiteralPath $payloadRoot | Where-Object {
        -not [string]::Equals($_.FullName, $manifestPath, [System.StringComparison]::OrdinalIgnoreCase)
    })
    $records = @($payload.files)
    if ($records.Count -eq 0 -or $records.Count -ne $actualFiles.Count) {
        throw "Portable payload manifest file set is incomplete"
    }
    $seenPaths = New-Object 'System.Collections.Generic.List[string]'
    foreach ($record in $records) {
        Assert-MihoExactObjectPropertiesV1 -Object $record -Names @("path", "size", "sha256")
        Assert-MihoJsonValueTypeV1 -Value $record.path -Kind string -Label "portable_manifest.files.path"
        Assert-MihoJsonValueTypeV1 -Value $record.size -Kind integer -Label "portable_manifest.files.size"
        Assert-MihoJsonValueTypeV1 -Value $record.sha256 -Kind string -Label "portable_manifest.files.sha256"
        $relative = [string]$record.path
        Assert-MihoReleaseRelativePathV1 -Path $relative -Label "portable_manifest.files.path"
        Assert-MihoNoCaseCollidingPathV1 -PriorPaths @($seenPaths) -Path $relative -Label "portable_manifest.files"
        if ($relative -ieq "miho-release-files-v1.json" -or [int64]$record.size -lt 0) {
            throw "Portable payload manifest contains an invalid file record"
        }
        Assert-MihoSha256ValueV1 -Value ([string]$record.sha256) -Label "portable_manifest.files.sha256"
        $candidate = Resolve-SafeFileV1 -LiteralPath (Join-Path $payloadRoot $relative)
        $null = Assert-PathBelow -LiteralPath $candidate -Parent $payloadRoot
        $actualRelative = $candidate.Substring($prefix.Length).Replace("\", "/")
        if ($actualRelative -cne $relative -or
            [int64](Get-Item -LiteralPath $candidate -Force -ErrorAction Stop).Length -ne [int64]$record.size -or
            (Get-Sha256Hex -LiteralPath $candidate) -cne [string]$record.sha256) {
            throw "Portable payload manifest record differs from payload bytes"
        }
        $seenPaths.Add($relative)
    }

    Assert-MihoExactObjectPropertiesV1 -Object $payload.signature_boundary -Names @(
        "guarantee", "executables", "nsis_container"
    )
    Assert-MihoJsonValueTypeV1 -Value $payload.signature_boundary.guarantee -Kind string -Label "portable_manifest.signature_boundary.guarantee"
    Assert-MihoJsonPropertyTypeV1 -Object $payload.signature_boundary -Name "executables" -Kind array -Label "portable_manifest.signature_boundary.executables"
    Assert-MihoJsonValueTypeV1 -Value $payload.signature_boundary.nsis_container -Kind string -Label "portable_manifest.signature_boundary.nsis_container"
    if ([string]$payload.signature_boundary.guarantee -cne "This manifest records payload size and SHA-256 only; it does not claim Authenticode trust." -or
        [string]$payload.signature_boundary.nsis_container -cne "The NSIS container and external miho.exe require release-pipeline signing outside this repository unless their status is Valid.") {
        throw "Portable payload signature boundary is invalid"
    }
    $executableRecords = @($payload.signature_boundary.executables)
    $expectedExecutables = @("miho-desktop.exe", "miho.exe")
    if ($executableRecords.Count -ne $expectedExecutables.Count) {
        throw "Portable payload executable signature record set is invalid"
    }
    for ($index = 0; $index -lt $expectedExecutables.Count; $index += 1) {
        $record = $executableRecords[$index]
        $expectedPath = $expectedExecutables[$index]
        Assert-MihoExactObjectPropertiesV1 -Object $record -Names @("path", "authenticode_status")
        Assert-MihoJsonValueTypeV1 -Value $record.path -Kind string -Label "portable_manifest.signature_boundary.executables.path"
        Assert-MihoJsonValueTypeV1 -Value $record.authenticode_status -Kind string -Label "portable_manifest.signature_boundary.executables.authenticode_status"
        $executable = Resolve-SafeFileV1 -LiteralPath (Join-Path $payloadRoot $expectedPath)
        if ([string]$record.path -cne $expectedPath -or
            [string]$record.authenticode_status -cne (Get-AuthenticodeStatusV1 -LiteralPath $executable)) {
            throw "Portable payload executable signature record is stale"
        }
    }

    $manifestHash = Get-Sha256Hex -LiteralPath $manifestPath
    return [pscustomobject][ordered]@{
        PayloadId = $manifestHash.Substring(0, 16)
        FileCount = $records.Count
        ManifestSha256 = $manifestHash
    }
}

function Get-MihoInstalledStaticSourceRecordsV1 {
    param(
        [Parameter(Mandatory = $true)][string]$StagingRoot,
        [Parameter(Mandatory = $true)][string]$MainExecutable,
        [Parameter(Mandatory = $true)][string]$Sidecar,
        [switch]$IncludeOwnershipManifest
    )

    $staging = Resolve-SafeDirectoryV1 -LiteralPath $StagingRoot
    $expected = New-Object System.Collections.ArrayList
    foreach ($record in @(
        [pscustomobject]@{ InstallPath = "miho-desktop.exe"; Source = $MainExecutable },
        [pscustomobject]@{ InstallPath = "miho.exe"; Source = $Sidecar }
    )) {
        $source = Resolve-SafeFileV1 -LiteralPath ([string]$record.Source)
        $null = $expected.Add([pscustomobject][ordered]@{
            InstallPath = [string]$record.InstallPath
            Source = $source
        })
    }
    $configsRoot = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $staging "resources\configs")
    $configPrefix = $configsRoot.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    foreach ($file in @(Sort-MihoObjectsByStringPropertyOrdinalV1 `
            -Values @(Get-MihoSafeFilesV1 -LiteralPath $configsRoot) `
            -Property "FullName")) {
        $relative = $file.FullName.Substring($configPrefix.Length).Replace("\", "/")
        $null = $expected.Add([pscustomobject][ordered]@{
            InstallPath = "defaults/configs/$relative"
            Source = $file.FullName
        })
    }
    $installerRoot = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $staging "resources\installer")
    $expectedScripts = @(
        "task_scheduler_v1.ps1",
        "install_daily_update_task.ps1",
        "uninstall_daily_update_task.ps1",
        "installer_transaction_v1.ps1"
    )
    $actualScripts = @(Get-MihoSafeFilesV1 -LiteralPath $installerRoot)
    if ($actualScripts.Count -ne $expectedScripts.Count) {
        throw "Immutable installer resources do not contain the exact installed script set"
    }
    foreach ($name in $expectedScripts) {
        $source = Resolve-SafeFileV1 -LiteralPath (Join-Path $installerRoot $name)
        $null = $expected.Add([pscustomobject][ordered]@{ InstallPath = "installer/$name"; Source = $source })
    }
    if ($IncludeOwnershipManifest) {
        $ownership = Resolve-SafeFileV1 -LiteralPath (Join-Path $staging "resources\miho-static-ownership-v1.json")
        $null = $expected.Add([pscustomobject][ordered]@{
            InstallPath = "miho-static-ownership-v1.json"
            Source = $ownership
        })
    }
    return @(Sort-MihoObjectsByStringPropertyOrdinalV1 -Values @($expected) -Property "InstallPath")
}

function Assert-MihoStaticOwnershipManifestV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Manifest,
        [Parameter(Mandatory = $true)][object[]]$ExpectedFiles,
        [Parameter(Mandatory = $true)][string]$ProductVersion,
        [Parameter(Mandatory = $true)][string]$HostTriple
    )

    $manifestPath = Resolve-SafeFileV1 -LiteralPath $Manifest
    $ownershipManifest = Read-MihoStrictJsonFileV1 -LiteralPath $manifestPath
    Assert-MihoExactObjectPropertiesV1 -Object $ownershipManifest -Names @(
        "schema_version", "product_version", "target_triple", "files", "ownership"
    )
    foreach ($field in @("schema_version", "product_version", "target_triple")) {
        Assert-MihoJsonValueTypeV1 -Value $ownershipManifest.$field -Kind string -Label "static_ownership.$field"
    }
    Assert-MihoJsonPropertyTypeV1 -Object $ownershipManifest -Name "files" -Kind array -Label "static_ownership.files"
    Assert-MihoJsonValueTypeV1 -Value $ownershipManifest.ownership -Kind object -Label "static_ownership.ownership"
    if ([string]$ownershipManifest.schema_version -cne "miho-static-ownership-v1" -or
        [string]$ownershipManifest.product_version -cne $ProductVersion -or
        [string]$ownershipManifest.target_triple -cne $HostTriple) {
        throw "Static ownership manifest identity is invalid"
    }

    $expected = @(Sort-MihoObjectsByStringPropertyOrdinalV1 -Values @($ExpectedFiles) -Property "InstallPath")
    $records = @($ownershipManifest.files)
    if ($expected.Count -lt 1 -or $records.Count -ne $expected.Count) {
        throw "Static ownership manifest file set is incomplete"
    }
    $seenPaths = New-Object 'System.Collections.Generic.List[string]'
    for ($index = 0; $index -lt $records.Count; $index += 1) {
        $record = $records[$index]
        $sourceRecord = $expected[$index]
        Assert-MihoExactObjectPropertiesV1 -Object $record -Names @("install_path", "size", "sha256")
        Assert-MihoJsonValueTypeV1 -Value $record.install_path -Kind string -Label "static_ownership.files.install_path"
        Assert-MihoJsonValueTypeV1 -Value $record.size -Kind integer -Label "static_ownership.files.size"
        Assert-MihoJsonValueTypeV1 -Value $record.sha256 -Kind string -Label "static_ownership.files.sha256"
        $installPath = [string]$record.install_path
        Assert-MihoReleaseRelativePathV1 -Path $installPath -Label "static_ownership.files.install_path"
        Assert-MihoNoCaseCollidingPathV1 -PriorPaths @($seenPaths) -Path $installPath -Label "static_ownership.files"
        Assert-MihoSha256ValueV1 -Value ([string]$record.sha256) -Label "static_ownership.files.sha256"
        if ($installPath -ceq "miho-static-ownership-v1.json") {
            throw "Static ownership manifest must not list itself"
        }
        $source = Resolve-SafeFileV1 -LiteralPath ([string]$sourceRecord.Source)
        $sourceItem = Get-Item -LiteralPath $source -Force -ErrorAction Stop
        if ($installPath -cne [string]$sourceRecord.InstallPath -or
            [int64]$record.size -ne [int64]$sourceItem.Length -or
            [string]$record.sha256 -cne (Get-Sha256Hex -LiteralPath $source)) {
            throw "Static ownership manifest differs from installer-owned bytes"
        }
        $seenPaths.Add($installPath)
    }

    Assert-MihoExactObjectPropertiesV1 -Object $ownershipManifest.ownership -Names @(
        "manifest_install_path", "manifest_self_in_files", "files_are_complete",
        "retired_file_policy", "mutable_data_excluded"
    )
    Assert-MihoJsonValueTypeV1 -Value $ownershipManifest.ownership.manifest_install_path -Kind string -Label "static_ownership.ownership.manifest_install_path"
    Assert-MihoJsonValueTypeV1 -Value $ownershipManifest.ownership.manifest_self_in_files -Kind boolean -Label "static_ownership.ownership.manifest_self_in_files"
    Assert-MihoJsonValueTypeV1 -Value $ownershipManifest.ownership.files_are_complete -Kind boolean -Label "static_ownership.ownership.files_are_complete"
    Assert-MihoJsonValueTypeV1 -Value $ownershipManifest.ownership.retired_file_policy -Kind string -Label "static_ownership.ownership.retired_file_policy"
    Assert-MihoJsonValueTypeV1 -Value $ownershipManifest.ownership.mutable_data_excluded -Kind boolean -Label "static_ownership.ownership.mutable_data_excluded"
    if ([string]$ownershipManifest.ownership.manifest_install_path -cne "miho-static-ownership-v1.json" -or
        $ownershipManifest.ownership.manifest_self_in_files -ne $false -or
        $ownershipManifest.ownership.files_are_complete -ne $true -or
        [string]$ownershipManifest.ownership.retired_file_policy -cne "delete-only-if-old-size-and-sha256-match" -or
        $ownershipManifest.ownership.mutable_data_excluded -ne $true) {
        throw "Static ownership manifest semantics are invalid"
    }
    return $true
}

function New-MihoStaticOwnershipManifestV1 {
    param(
        [Parameter(Mandatory = $true)][string]$ProductVersion,
        [Parameter(Mandatory = $true)][string]$HostTriple,
        [Parameter(Mandatory = $true)][string]$StagingRoot,
        [Parameter(Mandatory = $true)][string]$MainExecutable,
        [Parameter(Mandatory = $true)][string]$Sidecar,
        [Parameter(Mandatory = $true)][string]$OutputPath
    )

    if (Test-Path -LiteralPath $OutputPath) { throw "Static ownership manifest output already exists" }
    $sources = @(Get-MihoInstalledStaticSourceRecordsV1 `
        -StagingRoot $StagingRoot `
        -MainExecutable $MainExecutable `
        -Sidecar $Sidecar)
    $records = @(
        foreach ($sourceRecord in $sources) {
            $source = Resolve-SafeFileV1 -LiteralPath ([string]$sourceRecord.Source)
            $item = Get-Item -LiteralPath $source -Force -ErrorAction Stop
            [pscustomobject][ordered]@{
                install_path = [string]$sourceRecord.InstallPath
                size = [int64]$item.Length
                sha256 = Get-Sha256Hex -LiteralPath $source
            }
        }
    )
    $manifest = [pscustomobject][ordered]@{
        schema_version = "miho-static-ownership-v1"
        product_version = $ProductVersion
        target_triple = $HostTriple
        files = $records
        ownership = [pscustomobject][ordered]@{
            manifest_install_path = "miho-static-ownership-v1.json"
            manifest_self_in_files = $false
            files_are_complete = $true
            retired_file_policy = "delete-only-if-old-size-and-sha256-match"
            mutable_data_excluded = $true
        }
    }
    Write-Utf8NoBom -LiteralPath $OutputPath -Text (($manifest | ConvertTo-Json -Depth 8 -Compress) + "`n")
    $result = Resolve-SafeFileV1 -LiteralPath $OutputPath
    $null = Assert-MihoStaticOwnershipManifestV1 `
        -Manifest $result `
        -ExpectedFiles $sources `
        -ProductVersion $ProductVersion `
        -HostTriple $HostTriple
    return $result
}

function Get-MihoExpectedStaticInstalledFilesV1 {
    param(
        [Parameter(Mandatory = $true)][string]$PortableDirectory,
        [Parameter(Mandatory = $true)][string]$StagingRoot
    )

    $payloadRoot = Resolve-SafeDirectoryV1 -LiteralPath $PortableDirectory
    $staging = Resolve-SafeDirectoryV1 -LiteralPath $StagingRoot
    $expected = New-Object System.Collections.ArrayList
    foreach ($path in @("miho-desktop.exe", "miho.exe")) {
        $source = Resolve-SafeFileV1 -LiteralPath (Join-Path $payloadRoot $path)
        $null = $expected.Add([pscustomobject][ordered]@{ InstallPath = $path; Source = $source })
    }
    $configsRoot = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $payloadRoot "defaults\configs")
    $configPrefix = $configsRoot.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    foreach ($file in @(Sort-MihoObjectsByStringPropertyOrdinalV1 `
            -Values @(Get-MihoSafeFilesV1 -LiteralPath $configsRoot) `
            -Property "FullName")) {
        $relative = $file.FullName.Substring($configPrefix.Length).Replace("\", "/")
        $null = $expected.Add([pscustomobject][ordered]@{
            InstallPath = "defaults/configs/$relative"
            Source = $file.FullName
        })
    }
    $automationRoot = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $payloadRoot "automation")
    $portableScripts = @(
        "task_scheduler_v1.ps1",
        "install_daily_update_task.ps1",
        "uninstall_daily_update_task.ps1",
        "portable_daily_update_task.ps1"
    )
    $actualScripts = @(Get-MihoSafeFilesV1 -LiteralPath $automationRoot)
    if ($actualScripts.Count -ne $portableScripts.Count) {
        throw "Portable automation payload does not contain the exact script set"
    }
    foreach ($name in $portableScripts) {
        $null = Resolve-SafeFileV1 -LiteralPath (Join-Path $automationRoot $name)
    }
    foreach ($name in @("task_scheduler_v1.ps1", "install_daily_update_task.ps1", "uninstall_daily_update_task.ps1")) {
        $source = Resolve-SafeFileV1 -LiteralPath (Join-Path $automationRoot $name)
        $null = $expected.Add([pscustomobject][ordered]@{ InstallPath = "installer/$name"; Source = $source })
    }
    $transaction = Resolve-SafeFileV1 -LiteralPath (Join-Path $staging "resources\installer\installer_transaction_v1.ps1")
    $null = $expected.Add([pscustomobject][ordered]@{
        InstallPath = "installer/installer_transaction_v1.ps1"
        Source = $transaction
    })
    $ownership = Resolve-SafeFileV1 -LiteralPath (Join-Path $payloadRoot "miho-static-ownership-v1.json")
    $stagedOwnership = Resolve-SafeFileV1 -LiteralPath (Join-Path $staging "resources\miho-static-ownership-v1.json")
    if ((Get-Sha256Hex -LiteralPath $ownership) -cne (Get-Sha256Hex -LiteralPath $stagedOwnership)) {
        throw "Portable static ownership manifest differs from immutable installer staging"
    }
    $null = $expected.Add([pscustomobject][ordered]@{
        InstallPath = "miho-static-ownership-v1.json"
        Source = $ownership
    })
    return @(Sort-MihoObjectsByStringPropertyOrdinalV1 -Values @($expected) -Property "InstallPath")
}

function Assert-MihoStaticInstalledPayloadManifestV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Manifest,
        [Parameter(Mandatory = $true)][string]$PortableDirectory,
        [Parameter(Mandatory = $true)][string]$StagingRoot,
        [Parameter(Mandatory = $true)][string]$ProductVersion,
        [Parameter(Mandatory = $true)][string]$HostTriple
    )

    $manifestPath = Resolve-SafeFileV1 -LiteralPath $Manifest
    $installed = Read-MihoStrictJsonFileV1 -LiteralPath $manifestPath
    Assert-MihoExactObjectPropertiesV1 -Object $installed -Names @(
        "schema_version", "product_version", "target_triple", "files", "ownership",
        "container_verification", "signature_boundary"
    )
    foreach ($field in @("schema_version", "product_version", "target_triple")) {
        Assert-MihoJsonValueTypeV1 -Value $installed.$field -Kind string -Label "installed.$field"
    }
    Assert-MihoJsonPropertyTypeV1 -Object $installed -Name "files" -Kind array -Label "installed.files"
    Assert-MihoJsonValueTypeV1 -Value $installed.ownership -Kind object -Label "installed.ownership"
    Assert-MihoJsonValueTypeV1 -Value $installed.container_verification -Kind object -Label "installed.container_verification"
    Assert-MihoJsonValueTypeV1 -Value $installed.signature_boundary -Kind object -Label "installed.signature_boundary"
    if ([string]$installed.schema_version -cne "miho-static-installed-payload-v1" -or
        [string]$installed.product_version -cne $ProductVersion -or
        [string]$installed.target_triple -cne $HostTriple) {
        throw "Final static installed-payload manifest schema is invalid"
    }

    $expectedFiles = @(Get-MihoExpectedStaticInstalledFilesV1 `
        -PortableDirectory $PortableDirectory `
        -StagingRoot $StagingRoot)
    $ownershipExpected = @($expectedFiles | Where-Object {
        [string]$_.InstallPath -cne "miho-static-ownership-v1.json"
    })
    $null = Assert-MihoStaticOwnershipManifestV1 `
        -Manifest (Join-Path $PortableDirectory "miho-static-ownership-v1.json") `
        -ExpectedFiles $ownershipExpected `
        -ProductVersion $ProductVersion `
        -HostTriple $HostTriple
    $records = @($installed.files)
    if ($records.Count -eq 0 -or $records.Count -ne $expectedFiles.Count) {
        throw "Static installed-payload manifest file set is incomplete"
    }
    $seenPaths = New-Object 'System.Collections.Generic.List[string]'
    for ($index = 0; $index -lt $records.Count; $index += 1) {
        $record = $records[$index]
        $expected = $expectedFiles[$index]
        Assert-MihoExactObjectPropertiesV1 -Object $record -Names @("install_path", "size", "sha256")
        Assert-MihoJsonValueTypeV1 -Value $record.install_path -Kind string -Label "installed.files.install_path"
        Assert-MihoJsonValueTypeV1 -Value $record.size -Kind integer -Label "installed.files.size"
        Assert-MihoJsonValueTypeV1 -Value $record.sha256 -Kind string -Label "installed.files.sha256"
        $installPath = [string]$record.install_path
        Assert-MihoReleaseRelativePathV1 -Path $installPath -Label "installed.files.install_path"
        Assert-MihoNoCaseCollidingPathV1 -PriorPaths @($seenPaths) -Path $installPath -Label "installed.files"
        Assert-MihoSha256ValueV1 -Value ([string]$record.sha256) -Label "installed.files.sha256"
        $source = Resolve-SafeFileV1 -LiteralPath ([string]$expected.Source)
        if ($installPath -cne [string]$expected.InstallPath -or [int64]$record.size -lt 0 -or
            [int64]$record.size -ne [int64](Get-Item -LiteralPath $source -Force -ErrorAction Stop).Length -or
            [string]$record.sha256 -cne (Get-Sha256Hex -LiteralPath $source)) {
            throw "Static installed-payload record differs from immutable payload bytes at index $index ($installPath vs $([string]$expected.InstallPath))"
        }
        $seenPaths.Add($installPath)
    }

    Assert-MihoExactObjectPropertiesV1 -Object $installed.ownership -Names @(
        "mutable_workspace_excluded", "automation_owner_instance_required", "guarantee"
    )
    Assert-MihoJsonValueTypeV1 -Value $installed.ownership.mutable_workspace_excluded -Kind boolean -Label "installed.ownership.mutable_workspace_excluded"
    Assert-MihoJsonValueTypeV1 -Value $installed.ownership.automation_owner_instance_required -Kind boolean -Label "installed.ownership.automation_owner_instance_required"
    Assert-MihoJsonValueTypeV1 -Value $installed.ownership.guarantee -Kind string -Label "installed.ownership.guarantee"
    if ($installed.ownership.mutable_workspace_excluded -ne $true -or
        $installed.ownership.automation_owner_instance_required -ne $true -or
        [string]$installed.ownership.guarantee -cne "This external manifest covers only static bundled payload bytes. Dynamic uninstall.exe, registry values, shortcuts, workspace, Box, reports, browser state, and automation owned by another instance are outside this file list.") {
        throw "Static installed-payload ownership boundary is invalid"
    }

    Assert-MihoExactObjectPropertiesV1 -Object $installed.signature_boundary -Names @("guarantee", "executables")
    Assert-MihoJsonValueTypeV1 -Value $installed.signature_boundary.guarantee -Kind string -Label "installed.signature_boundary.guarantee"
    Assert-MihoJsonPropertyTypeV1 -Object $installed.signature_boundary -Name "executables" -Kind array -Label "installed.signature_boundary.executables"
    if ([string]$installed.signature_boundary.guarantee -cne "Observed status is evidence only. Any status other than Valid is not an Authenticode trust claim.") {
        throw "Static installed-payload signature boundary is invalid"
    }
    $executables = @($installed.signature_boundary.executables)
    $expectedExecutablePaths = @("miho-desktop.exe", "miho.exe")
    if ($executables.Count -ne $expectedExecutablePaths.Count) {
        throw "Static installed-payload executable signature record set is invalid"
    }
    for ($index = 0; $index -lt $executables.Count; $index += 1) {
        $record = $executables[$index]
        $expectedPath = $expectedExecutablePaths[$index]
        Assert-MihoExactObjectPropertiesV1 -Object $record -Names @("install_path", "authenticode_status")
        Assert-MihoJsonValueTypeV1 -Value $record.install_path -Kind string -Label "installed.signature_boundary.executables.install_path"
        Assert-MihoJsonValueTypeV1 -Value $record.authenticode_status -Kind string -Label "installed.signature_boundary.executables.authenticode_status"
        $sourceRecord = @($expectedFiles | Where-Object { [string]$_.InstallPath -ceq $expectedPath })
        if ($sourceRecord.Count -ne 1 -or [string]$record.install_path -cne $expectedPath -or
            [string]$record.authenticode_status -cne (Get-AuthenticodeStatusV1 -LiteralPath ([string]$sourceRecord[0].Source))) {
            throw "Static installed-payload executable signature record is stale"
        }
    }

    Assert-MihoExactObjectPropertiesV1 -Object $installed.container_verification -Names @(
        "status", "method", "nsis_size", "nsis_sha256", "files_verified"
    )
    foreach ($field in @("status", "method", "nsis_sha256")) {
        Assert-MihoJsonValueTypeV1 -Value $installed.container_verification.$field -Kind string -Label "installed.container_verification.$field"
    }
    foreach ($field in @("nsis_size", "files_verified")) {
        Assert-MihoJsonValueTypeV1 -Value $installed.container_verification.$field -Kind integer -Label "installed.container_verification.$field"
    }
    if ([int64]$installed.container_verification.nsis_size -lt 0 -or
        [int64]$installed.container_verification.files_verified -lt 0 -or
        (-not [string]::IsNullOrEmpty([string]$installed.container_verification.nsis_sha256) -and
            [string]$installed.container_verification.nsis_sha256 -cnotmatch '^[0-9a-f]{64}$')) {
        throw "Static installed-payload container verification fields are invalid"
    }
    return [pscustomobject][ordered]@{ Manifest = $installed; FileCount = $records.Count }
}

function Enter-MihoReleaseBuildLeaseV1 {
    param([Parameter(Mandatory = $true)][string]$Root)

    $workspace = Resolve-SafeDirectoryV1 -LiteralPath $Root
    $leaseKey = Get-Sha256HexForTextV1 -Text $workspace.TrimEnd("\", "/").ToLowerInvariant()
    $mutex = New-Object System.Threading.Mutex($false, "Local\MihoReleaseBuildV1-$leaseKey")
    $mutexAcquired = $false
    $fileLease = $null
    try {
        try {
            $mutexAcquired = $mutex.WaitOne(0, $false)
        }
        catch [System.Threading.AbandonedMutexException] {
            $mutexAcquired = $true
        }
        if (-not $mutexAcquired) {
            throw "Another Miho release build is active"
        }
        $targetPath = Join-Path $workspace "target"
        if (-not (Test-Path -LiteralPath $targetPath)) {
            New-Item -ItemType Directory -Path $targetPath -ErrorAction Stop | Out-Null
        }
        $target = Resolve-SafeDirectoryV1 -LiteralPath $targetPath
        $lockPath = Join-Path $target ".miho-release-build-v1.lock"
        if (Test-Path -LiteralPath $lockPath) {
            $null = Resolve-SafeFileV1 -LiteralPath $lockPath
        }
        try {
            $fileLease = [System.IO.File]::Open(
                $lockPath,
                [System.IO.FileMode]::OpenOrCreate,
                [System.IO.FileAccess]::ReadWrite,
                [System.IO.FileShare]::None
            )
        }
        catch [System.IO.IOException] {
            throw "Another Miho release build is active"
        }
        return [pscustomobject][ordered]@{
            Mutex = $mutex
            File = $fileLease
            LockPath = $lockPath
        }
    }
    catch {
        if ($null -ne $fileLease) { $fileLease.Dispose() }
        if ($mutexAcquired) {
            try { $mutex.ReleaseMutex() } catch {}
        }
        $mutex.Dispose()
        throw
    }
}

function Exit-MihoReleaseBuildLeaseV1 {
    param([Parameter(Mandatory = $true)]$Lease)

    try { $Lease.File.Dispose() }
    finally {
        try { $Lease.Mutex.ReleaseMutex() }
        finally { $Lease.Mutex.Dispose() }
    }
}

function Get-MihoGitProvenanceV1 {
    param([Parameter(Mandatory = $true)][string]$Root)

    $workspace = Resolve-SafeDirectoryV1 -LiteralPath $Root
    $headLines = @(& git -C $workspace rev-parse --verify HEAD 2>$null)
    if ($LASTEXITCODE -ne 0 -or $headLines.Count -ne 1 -or [string]$headLines[0] -cnotmatch '^[0-9a-f]{40}$') {
        throw "Release source commit is unavailable"
    }
    $statusLines = @(& git -C $workspace status --porcelain=v1 --untracked-files=all 2>$null)
    if ($LASTEXITCODE -ne 0) { throw "Release source tree status is unavailable" }
    $statusText = [string]::Join("`n", @($statusLines | ForEach-Object { [string]$_ }))
    return [pscustomobject][ordered]@{
        source_commit = [string]$headLines[0]
        source_tree_state = $(if ($statusLines.Count -eq 0) { "clean" } else { "dirty" })
        source_status_sha256 = Get-Sha256HexForTextV1 -Text $statusText
        source_status_entry_count = [int]$statusLines.Count
    }
}

function Get-MihoPackageManagerPolicyV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$NodePath
    )

    $workspace = Resolve-SafeDirectoryV1 -LiteralPath $Root
    $packagePath = Resolve-SafeFileV1 -LiteralPath (Join-Path $workspace "package.json")
    $package = Read-MihoStrictJsonFileV1 -LiteralPath $packagePath
    Assert-MihoJsonPropertyTypeV1 -Object $package -Name "packageManager" -Kind string -Label "packageManager"
    Assert-MihoJsonPropertyTypeV1 -Object $package -Name "engines" -Kind object -Label "engines"
    Assert-MihoExactObjectPropertiesV1 -Object $package.engines -Names @("node", "pnpm")
    Assert-MihoJsonPropertyTypeV1 -Object $package.engines -Name "node" -Kind string -Label "engines.node"
    Assert-MihoJsonPropertyTypeV1 -Object $package.engines -Name "pnpm" -Kind string -Label "engines.pnpm"

    $packageManager = [string]$package.packageManager
    $nodeEngine = [string]$package.engines.node
    $pnpmEngine = [string]$package.engines.pnpm
    if ($packageManager -cnotmatch '^pnpm@(\d+\.\d+\.\d+)$') {
        throw "packageManager must pin one exact pnpm version"
    }
    $requiredPnpm = [string]$Matches[1]
    if ($pnpmEngine -cne $requiredPnpm) {
        throw "packageManager and engines.pnpm do not pin the same version"
    }
    if ($nodeEngine -cnotmatch '^>=(\d+\.\d+\.\d+) <(\d+)$') {
        throw "engines.node must use the supported bounded release grammar"
    }
    $minimumNode = New-Object System.Version([string]$Matches[1])
    $maximumNodeMajor = [int]$Matches[2]

    $nodeFile = Resolve-SafeFileV1 -LiteralPath $NodePath
    $nodeOutput = @(Invoke-NativeCommand -FilePath $nodeFile -ArgumentList @("--version") -FailureMessage "Node version detection failed")
    if ($nodeOutput.Count -ne 1 -or [string]$nodeOutput[0] -cnotmatch '^v(\d+\.\d+\.\d+)$') {
        throw "Actual Node version is not canonical"
    }
    $actualNodeText = [string]$Matches[1]
    $actualNode = New-Object System.Version($actualNodeText)
    if ($actualNode.CompareTo($minimumNode) -lt 0 -or $actualNode.Major -ge $maximumNodeMajor) {
        throw "Actual Node version does not satisfy package.json engines.node"
    }

    $pnpmCommand = Get-Command pnpm -ErrorAction Stop
    $pnpmOutput = @(Invoke-NativeCommand -FilePath $pnpmCommand.Source -ArgumentList @("--version") -FailureMessage "pnpm version detection failed")
    if ($pnpmOutput.Count -ne 1 -or [string]$pnpmOutput[0] -cnotmatch '^(\d+\.\d+\.\d+)$') {
        throw "Actual pnpm version is not canonical"
    }
    $actualPnpm = [string]$Matches[1]
    if ($actualPnpm -cne $requiredPnpm) {
        throw "Actual pnpm version does not match the pinned package manager"
    }

    return [pscustomobject][ordered]@{
        PackagePath = $packagePath
        PackageManager = $packageManager
        NodeEngine = $nodeEngine
        PnpmEngine = $pnpmEngine
        NodeFile = $nodeFile
        PnpmLauncher = [string]$pnpmCommand.Source
        NodeVersion = $actualNodeText
        PnpmVersion = $actualPnpm
    }
}

function Get-MihoReleaseToolchainEvidenceV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$NodePath
    )

    $workspace = Resolve-SafeDirectoryV1 -LiteralPath $Root
    $policy = Get-MihoPackageManagerPolicyV1 -Root $workspace -NodePath $NodePath
    $packagePath = [string]$policy.PackagePath
    $packageManager = [string]$policy.PackageManager
    $nodeEngine = [string]$policy.NodeEngine
    $pnpmEngine = [string]$policy.PnpmEngine
    $nodeFile = [string]$policy.NodeFile
    $pnpmLauncher = [string]$policy.PnpmLauncher
    $actualNodeText = [string]$policy.NodeVersion
    $actualPnpm = [string]$policy.PnpmVersion

    $rootPnpmLock = Resolve-SafeFileV1 -LiteralPath (Join-Path $workspace "pnpm-lock.yaml")
    $installedPnpmLock = Resolve-SafeFileV1 -LiteralPath (Join-Path $workspace "node_modules\.pnpm\lock.yaml")
    $rootPnpmLockHash = Get-Sha256Hex -LiteralPath $rootPnpmLock
    $installedPnpmLockHash = Get-Sha256Hex -LiteralPath $installedPnpmLock
    if ($rootPnpmLockHash -cne $installedPnpmLockHash) {
        throw "Installed pnpm graph does not exactly match the root frozen lock"
    }
    $dependencyTree = Get-MihoDependencyTreeDigestV1 -Root $workspace
    $entrypointPaths = [ordered]@{
        typescript_entrypoint_sha256 = Join-Path $workspace "crates\miho-desktop\node_modules\typescript\bin\tsc"
        vite_entrypoint_sha256 = Join-Path $workspace "crates\miho-desktop\node_modules\vite\bin\vite.js"
        tauri_entrypoint_sha256 = Join-Path $workspace "crates\miho-desktop\node_modules\@tauri-apps\cli\tauri.js"
    }
    $entrypointHashes = @{}
    foreach ($field in $entrypointPaths.Keys) {
        $entrypoint = Get-Item -LiteralPath ([string]$entrypointPaths[$field]) -Force -ErrorAction Stop
        if ($entrypoint.PSIsContainer) { throw "Release dependency entrypoint is not a file" }
        $entrypointHashes[$field] = Get-Sha256Hex -LiteralPath $entrypoint.FullName
    }

    $rustcOutput = @(Invoke-NativeCommand -FilePath "rustc" -ArgumentList @("-vV") -FailureMessage "Rust toolchain detection failed")
    $rustcReleaseLine = @($rustcOutput | Where-Object { [string]$_ -cmatch '^release: (.+)$' })
    if ($rustcReleaseLine.Count -ne 1 -or [string]$rustcReleaseLine[0] -cnotmatch '^release: (\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$') {
        throw "Rust release version is unavailable"
    }
    $rustcRelease = [string]$Matches[1]
    $rustcHostLine = @($rustcOutput | Where-Object { [string]$_ -cmatch '^host: (.+)$' })
    if ($rustcHostLine.Count -ne 1 -or [string]$rustcHostLine[0] -cnotmatch '^host: ([0-9A-Za-z_.-]+)$') {
        throw "Rust host triple is unavailable"
    }
    $rustcHost = [string]$Matches[1]
    $rustcText = [string]::Join("`n", @($rustcOutput | ForEach-Object { [string]$_ }))
    $cargoOutput = @(Invoke-NativeCommand -FilePath "cargo" -ArgumentList @("--version") -FailureMessage "Cargo version detection failed")
    if ($cargoOutput.Count -ne 1 -or [string]::IsNullOrWhiteSpace([string]$cargoOutput[0])) {
        throw "Cargo version is unavailable"
    }

    return [pscustomobject][ordered]@{
        dependency_graph_state = "frozen-lock-matches-isolated-full-dependency-tree-hash-bound"
        pnpm_install_mode = "isolated-empty-tree-frozen-prefer-offline-force-verified-copy"
        package_json_sha256 = Get-Sha256Hex -LiteralPath $packagePath
        cargo_lock_sha256 = Get-Sha256Hex -LiteralPath (Resolve-SafeFileV1 -LiteralPath (Join-Path $workspace "Cargo.lock"))
        pnpm_lock_sha256 = $rootPnpmLockHash
        installed_pnpm_lock_sha256 = $installedPnpmLockHash
        dependency_tree_sha256 = [string]$dependencyTree.digest
        dependency_tree_entry_count = [int]$dependencyTree.entry_count
        dependency_tree_file_count = [int]$dependencyTree.file_count
        package_manager = $packageManager
        node_engine = $nodeEngine
        pnpm_engine = $pnpmEngine
        node_version = $actualNodeText
        pnpm_version = $actualPnpm
        node_executable_sha256 = Get-Sha256Hex -LiteralPath $nodeFile
        pnpm_launcher_sha256 = Get-Sha256Hex -LiteralPath (Resolve-SafeFileV1 -LiteralPath $pnpmLauncher)
        typescript_entrypoint_sha256 = [string]$entrypointHashes.typescript_entrypoint_sha256
        vite_entrypoint_sha256 = [string]$entrypointHashes.vite_entrypoint_sha256
        tauri_entrypoint_sha256 = [string]$entrypointHashes.tauri_entrypoint_sha256
        rustc_release = $rustcRelease
        rustc_host = $rustcHost
        rustc_vv_sha256 = Get-Sha256HexForTextV1 -Text $rustcText
        cargo_version = [string]$cargoOutput[0]
    }
}

function Invoke-MihoFrozenPnpmInstallV1 {
    param([Parameter(Mandatory = $true)][string]$Root)

    $workspace = Resolve-SafeDirectoryV1 -LiteralPath $Root
    foreach ($relative in @("node_modules", "crates\miho-desktop\node_modules")) {
        if (Test-Path -LiteralPath (Join-Path $workspace $relative)) {
            throw "Frozen pnpm install requires an empty isolated dependency tree"
        }
    }
    $pnpmCommand = Get-Command pnpm -ErrorAction Stop
    Push-Location $workspace
    try {
        Invoke-NativeCommand `
            -FilePath $pnpmCommand.Source `
            -ArgumentList @(
                "install", "--frozen-lockfile", "--prefer-offline", "--force",
                "--verify-store-integrity", "--package-import-method", "copy"
            ) `
            -FailureMessage "Pinned frozen pnpm dependency installation failed"
    }
    finally { Pop-Location }
    foreach ($relative in @("node_modules", "crates\miho-desktop\node_modules")) {
        $null = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $workspace $relative)
    }
}

function Get-MihoReleasePublicationDecisionV1 {
    param(
        [Parameter(Mandatory = $true)][string]$SourceTreeState,
        [Parameter(Mandatory = $true)][bool]$NoBundleMode,
        [bool]$ProjectGatesApproved = $false
    )

    if ($SourceTreeState -notin @("clean", "dirty")) {
        throw "Release source-tree state is invalid"
    }
    if ($ProjectGatesApproved) {
        if ($SourceTreeState -cne "clean" -or $NoBundleMode) {
            throw "Project-gate approval requires a clean full-bundle source"
        }
        return [pscustomobject][ordered]@{
            state = "active"
            reason = "project-gates-approved-clean-source-and-full-bundle"
        }
    }
    $reason = if ($SourceTreeState -ceq "dirty" -and $NoBundleMode) {
        "dirty-source-tree-and-no-bundle"
    }
    elseif ($SourceTreeState -ceq "dirty") {
        "dirty-source-tree"
    }
    elseif (-not $NoBundleMode) {
        "project-gates-not-approved"
    }
    else {
        "no-bundle"
    }
    return [pscustomobject][ordered]@{ state = "verification-only"; reason = $reason }
}

function Assert-MihoFrozenReleaseStateV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$BuildWorkspaceRoot,
        [Parameter(Mandatory = $true)][string]$ToolchainRoot,
        [Parameter(Mandatory = $true)][string]$NodePath,
        [Parameter(Mandatory = $true)]$ExpectedGitProvenance,
        [Parameter(Mandatory = $true)]$ExpectedWorkspaceInputs,
        [Parameter(Mandatory = $true)]$ExpectedBuildWorkspaceInputs,
        [Parameter(Mandatory = $true)]$ExpectedToolchainEvidence,
        [AllowNull()][string]$StagingRoot,
        [AllowNull()]$ExpectedStagingEvidence
    )

    $actualGit = Get-MihoGitProvenanceV1 -Root $Root
    foreach ($field in @("source_commit", "source_tree_state", "source_status_sha256", "source_status_entry_count")) {
        if ([string]$actualGit.$field -cne [string]$ExpectedGitProvenance.$field) {
            throw "Release Git provenance changed during the transaction"
        }
    }
    $actualWorkspace = Get-MihoWorkspaceReleaseInputsDigestV1 -Root $Root
    foreach ($field in @("digest", "file_count")) {
        if ([string]$actualWorkspace.$field -cne [string]$ExpectedWorkspaceInputs.$field) {
            throw "Workspace release inputs changed during the transaction"
        }
    }
    $actualBuildWorkspace = Get-MihoWorkspaceReleaseInputsDigestV1 -Root $BuildWorkspaceRoot
    foreach ($field in @("digest", "file_count")) {
        if ([string]$actualBuildWorkspace.$field -cne [string]$ExpectedBuildWorkspaceInputs.$field) {
            throw "Isolated build workspace inputs changed during the transaction"
        }
    }
    if ([string]$actualWorkspace.digest -cne [string]$actualBuildWorkspace.digest -or
        [int]$actualWorkspace.file_count -ne [int]$actualBuildWorkspace.file_count) {
        throw "Isolated build workspace no longer matches the original frozen inputs"
    }
    $actualToolchain = Get-MihoReleaseToolchainEvidenceV1 -Root $ToolchainRoot -NodePath $NodePath
    foreach ($field in @(
        "dependency_graph_state", "pnpm_install_mode", "package_json_sha256", "cargo_lock_sha256", "pnpm_lock_sha256",
        "installed_pnpm_lock_sha256", "dependency_tree_sha256", "dependency_tree_entry_count",
        "dependency_tree_file_count", "package_manager", "node_engine", "pnpm_engine", "node_version",
        "pnpm_version", "node_executable_sha256", "pnpm_launcher_sha256", "typescript_entrypoint_sha256",
        "vite_entrypoint_sha256", "tauri_entrypoint_sha256", "rustc_release", "rustc_host",
        "rustc_vv_sha256", "cargo_version"
    )) {
        if ([string]$actualToolchain.$field -cne [string]$ExpectedToolchainEvidence.$field) {
            throw "Release toolchain or frozen dependency graph changed during the transaction"
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($StagingRoot) -or $null -ne $ExpectedStagingEvidence) {
        if ([string]::IsNullOrWhiteSpace($StagingRoot) -or $null -eq $ExpectedStagingEvidence) {
            throw "Frozen release staging evidence is incomplete"
        }
        $actualStaging = Get-MihoTreeDigestV1 -LiteralPath $StagingRoot
        foreach ($field in @("digest", "file_count")) {
            if ([string]$actualStaging.$field -cne [string]$ExpectedStagingEvidence.$field) {
                throw "Immutable release staging changed during the transaction"
            }
        }
    }
    return $true
}

function Clear-MihoStaleReleaseContextsV1 {
    param([Parameter(Mandatory = $true)][string]$Root)

    $contextRootPath = Join-Path $Root "target\release\release-context"
    if (-not (Test-Path -LiteralPath $contextRootPath)) { return }
    $contextRoot = Resolve-SafeDirectoryV1 -LiteralPath $contextRootPath
    foreach ($entry in @(Get-ChildItem -LiteralPath $contextRoot -Force -ErrorAction Stop)) {
        $knownLegacy = $entry.Name -ceq "miho-installed-files-v1.json"
        if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or $entry.PSIsContainer -or
            (-not $knownLegacy -and $entry.Name -notmatch '^tauri-release-[0-9a-f]{32}\.json$')) {
            throw "Release context directory contains a foreign entry"
        }
        Remove-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $entry.FullName) -Force -ErrorAction Stop
    }
}

function New-MihoStaticInstalledPayloadManifestV1 {
    param(
        [Parameter(Mandatory = $true)][string]$ProductVersion,
        [Parameter(Mandatory = $true)][string]$HostTriple,
        [Parameter(Mandatory = $true)][string]$StagingRoot,
        [Parameter(Mandatory = $true)][string]$Sidecar,
        [Parameter(Mandatory = $true)][string]$MainExecutable,
        [Parameter(Mandatory = $true)][string]$OutputPath,
        [Parameter(Mandatory = $true)][bool]$NoBundleMode
    )

    $sourceRecords = @(Get-MihoInstalledStaticSourceRecordsV1 `
        -StagingRoot $StagingRoot `
        -MainExecutable $MainExecutable `
        -Sidecar $Sidecar `
        -IncludeOwnershipManifest)
    $null = Assert-MihoStaticOwnershipManifestV1 `
        -Manifest (Join-Path $StagingRoot "resources\miho-static-ownership-v1.json") `
        -ExpectedFiles @($sourceRecords | Where-Object {
            [string]$_.InstallPath -cne "miho-static-ownership-v1.json"
        }) `
        -ProductVersion $ProductVersion `
        -HostTriple $HostTriple
    $records = New-Object System.Collections.ArrayList
    foreach ($record in $sourceRecords) {
        $source = Resolve-SafeFileV1 -LiteralPath ([string]$record.Source)
        $item = Get-Item -LiteralPath $source -Force -ErrorAction Stop
        $null = $records.Add([pscustomobject][ordered]@{
            install_path = [string]$record.InstallPath
            size = [int64]$item.Length
            sha256 = Get-Sha256Hex -LiteralPath $source
        })
    }
    $manifest = [pscustomobject][ordered]@{
        schema_version = "miho-static-installed-payload-v1"
        product_version = $ProductVersion
        target_triple = $HostTriple
        files = @(Sort-MihoObjectsByStringPropertyOrdinalV1 -Values @($records) -Property "install_path")
        ownership = [pscustomobject][ordered]@{
            mutable_workspace_excluded = $true
            automation_owner_instance_required = $true
            guarantee = "This external manifest covers only static bundled payload bytes. Dynamic uninstall.exe, registry values, shortcuts, workspace, Box, reports, browser state, and automation owned by another instance are outside this file list."
        }
        container_verification = [pscustomobject][ordered]@{
            status = $(if ($NoBundleMode) { "not-applicable-no-bundle" } else { "pending" })
            method = $(if ($NoBundleMode) { "none" } else { "nsis-build-only-extraction" })
            nsis_size = [int64]0
            nsis_sha256 = ""
            files_verified = 0
        }
        signature_boundary = [pscustomobject][ordered]@{
            guarantee = "Observed status is evidence only. Any status other than Valid is not an Authenticode trust claim."
            executables = @(
                [pscustomobject][ordered]@{ install_path = "miho-desktop.exe"; authenticode_status = Get-AuthenticodeStatusV1 -LiteralPath $MainExecutable },
                [pscustomobject][ordered]@{ install_path = "miho.exe"; authenticode_status = Get-AuthenticodeStatusV1 -LiteralPath $Sidecar }
            )
        }
    }
    try {
        Write-Utf8NoBom -LiteralPath $OutputPath -Text (($manifest | ConvertTo-Json -Depth 8 -Compress) + "`n")
        return Resolve-SafeFileV1 -LiteralPath $OutputPath
    }
    catch {
        if (Test-Path -LiteralPath $OutputPath) {
            Remove-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $OutputPath) -Force -ErrorAction SilentlyContinue
        }
        throw
    }
}

function Expand-MihoStaticPayloadFromNsisV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$VerificationNonce,
        [Parameter(Mandatory = $true)][string]$NsisInstaller,
        [int]$TimeoutSeconds = 300
    )

    if ($VerificationNonce -notmatch '^[0-9a-f]{32}$' -or $TimeoutSeconds -le 0) {
        throw "NSIS container verification parameters are invalid"
    }
    $installer = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $NsisInstaller) -Force -ErrorAction Stop
    if ($installer.Extension -cne ".exe") { throw "NSIS container verifier input is not an executable" }
    $verificationParent = Ensure-SafeDirectoryV1 -LiteralPath (Join-Path $Root "target\release\container-verification")
    $verificationRoot = Assert-PathBelow -LiteralPath (Join-Path $verificationParent ("verify-" + [guid]::NewGuid().ToString("N"))) -Parent $verificationParent
    try {
        New-Item -ItemType Directory -Path $verificationRoot -ErrorAction Stop | Out-Null
        $verificationRoot = Resolve-SafeDirectoryV1 -LiteralPath $verificationRoot
        $marker = Join-Path $verificationRoot ".miho-static-container-verification-v1"
        Write-Utf8NoBom -LiteralPath $marker -Text $VerificationNonce
        $start = New-Object System.Diagnostics.ProcessStartInfo
        $start.FileName = $installer.FullName
        $start.Arguments = '/S /MIHO_VERIFY_STATIC="' + $verificationRoot + '"'
        $start.UseShellExecute = $false
        $start.CreateNoWindow = $true
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $start
        try {
            if (-not $process.Start()) { throw "NSIS container verifier did not start" }
            if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
                try { $process.Kill() } catch {}
                throw "NSIS container verifier timed out"
            }
            $process.WaitForExit()
            if ($process.ExitCode -ne 0) { throw "NSIS container verifier failed with exit code $($process.ExitCode)" }
        }
        finally { $process.Dispose() }
        if (Test-Path -LiteralPath $marker) { throw "NSIS container verifier did not consume its one-use marker" }
        return $verificationRoot
    }
    catch {
        if ($null -ne $verificationRoot -and (Test-Path -LiteralPath $verificationRoot)) {
            Remove-MihoSafeTreeV1 -LiteralPath $verificationRoot
        }
        throw
    }
}

function Confirm-MihoStaticInstalledPayloadFromNsisV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$VerificationNonce,
        [Parameter(Mandatory = $true)][string]$NsisInstaller,
        [Parameter(Mandatory = $true)][string]$InstalledPayloadManifest,
        [int]$TimeoutSeconds = 300
    )

    if ($VerificationNonce -notmatch '^[0-9a-f]{32}$' -or $TimeoutSeconds -le 0) {
        throw "NSIS container verification parameters are invalid"
    }
    $installer = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $NsisInstaller) -Force -ErrorAction Stop
    if ($installer.Extension -cne ".exe") { throw "NSIS container verifier input is not an executable" }
    $manifestPath = Resolve-SafeFileV1 -LiteralPath $InstalledPayloadManifest
    $manifest = Read-MihoStrictJsonFileV1 -LiteralPath $manifestPath
    if ([string]$manifest.schema_version -cne "miho-static-installed-payload-v1" -or -not ($manifest.files -is [System.Array])) {
        throw "Static installed-payload manifest is invalid before container verification"
    }
    $verificationRoot = Expand-MihoStaticPayloadFromNsisV1 `
        -Root $Root `
        -VerificationNonce $VerificationNonce `
        -NsisInstaller $installer.FullName `
        -TimeoutSeconds $TimeoutSeconds
    try {

        $prefix = $verificationRoot.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
        $actual = @{}
        foreach ($file in @(Get-MihoSafeFilesV1 -LiteralPath $verificationRoot)) {
            $relative = $file.FullName.Substring($prefix.Length).Replace("\", "/")
            if ($actual.ContainsKey($relative)) { throw "NSIS container extraction contains a duplicate path" }
            $actual[$relative] = $file
        }
        $expected = @{}
        foreach ($record in @($manifest.files)) {
            Assert-MihoExactObjectPropertiesV1 -Object $record -Names @("install_path", "size", "sha256")
            $relative = [string]$record.install_path
            if ([string]::IsNullOrWhiteSpace($relative) -or [System.IO.Path]::IsPathRooted($relative) -or
                $relative.Replace("\", "/").Split('/') -contains ".." -or $expected.ContainsKey($relative)) {
                throw "Static installed-payload manifest contains an unsafe or duplicate path"
            }
            $expected[$relative] = $record
        }
        if ($actual.Count -ne $expected.Count) {
            $actualPaths = [string]::Join(",", @(Sort-MihoStringsOrdinalV1 -Values @($actual.Keys)))
            $expectedPaths = [string]::Join(",", @(Sort-MihoStringsOrdinalV1 -Values @($expected.Keys)))
            throw "NSIS static container file set differs from the external manifest: expected=$($expected.Count)[$expectedPaths] actual=$($actual.Count)[$actualPaths]"
        }
        foreach ($relative in $expected.Keys) {
            if (-not $actual.ContainsKey($relative)) {
                throw "NSIS static container omits external-manifest file: $relative"
            }
            $record = $expected[$relative]
            $file = $actual[$relative]
            $actualSha256 = Get-Sha256Hex -LiteralPath $file.FullName
            if ([int64]$file.Length -ne [int64]$record.size -or $actualSha256 -cne [string]$record.sha256) {
                throw "NSIS static container bytes differ from the external manifest: path=$relative expected_size=$($record.size) actual_size=$($file.Length) expected_sha256=$($record.sha256) actual_sha256=$actualSha256"
            }
        }

        Assert-MihoExactObjectPropertiesV1 -Object $manifest.container_verification -Names @(
            "status", "method", "nsis_size", "nsis_sha256", "files_verified"
        )
        $manifest.container_verification.status = "verified"
        $manifest.container_verification.method = "nsis-build-only-extraction"
        $manifest.container_verification.nsis_size = [int64]$installer.Length
        $manifest.container_verification.nsis_sha256 = Get-Sha256Hex -LiteralPath $installer.FullName
        $manifest.container_verification.files_verified = $expected.Count
        Write-Utf8NoBom -LiteralPath $manifestPath -Text (($manifest | ConvertTo-Json -Depth 10 -Compress) + "`n")
        $verified = Read-MihoStrictJsonFileV1 -LiteralPath $manifestPath
        if ([string]$verified.container_verification.status -cne "verified" -or
            [string]$verified.container_verification.nsis_sha256 -cne (Get-Sha256Hex -LiteralPath $installer.FullName) -or
            [int64]$verified.container_verification.files_verified -ne $expected.Count) {
            throw "Static installed-payload container verification receipt is stale"
        }
        return $manifestPath
    }
    finally {
        if (Test-Path -LiteralPath $verificationRoot) {
            Remove-MihoSafeTreeV1 -LiteralPath $verificationRoot
        }
    }
}

function New-MihoIsolatedTauriTargetV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Nonce
    )

    if ($Nonce -cnotmatch '^[0-9a-f]{32}$') { throw "Tauri release-output nonce is invalid" }
    $parent = Ensure-SafeDirectoryV1 -LiteralPath (Join-Path $Root "target\release\release-output")
    $target = Assert-PathBelow -LiteralPath (Join-Path $parent "build-$Nonce") -Parent $parent
    if (Test-Path -LiteralPath $target) { throw "Isolated Tauri release target already exists" }
    New-Item -ItemType Directory -Path $target -ErrorAction Stop | Out-Null
    return Resolve-SafeDirectoryV1 -LiteralPath $target
}

function Resolve-MihoGeneratedNsisInstallerV1 {
    param(
        [Parameter(Mandatory = $true)][string]$TauriTarget,
        [Parameter(Mandatory = $true)][string]$ProductVersion
    )

    $generatedRoot = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $TauriTarget "release\bundle\nsis")
    $generated = @(Get-MihoSafeFilesV1 -LiteralPath $generatedRoot | Where-Object {
        $_.Extension -ieq ".exe" -and $_.Name -like "*$ProductVersion*"
    })
    if ($generated.Count -ne 1) { throw "Expected exactly one isolated NSIS installer" }
    return $generated[0].FullName
}

function Publish-MihoImmutableNsisArtifactV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$TauriTarget,
        [Parameter(Mandatory = $true)][string]$ProductVersion
    )

    $source = Get-Item -LiteralPath (Resolve-MihoGeneratedNsisInstallerV1 `
        -TauriTarget $TauriTarget `
        -ProductVersion $ProductVersion) -Force -ErrorAction Stop
    $sourceSize = [int64]$source.Length
    $hash = Get-Sha256Hex -LiteralPath $source.FullName
    $canonicalRoot = Ensure-SafeDirectoryV1 -LiteralPath (Join-Path $Root "target\release\bundle\nsis")
    $destinationName = "{0}.sha256-{1}.exe" -f [System.IO.Path]::GetFileNameWithoutExtension($source.Name), $hash
    $destination = Assert-PathBelow -LiteralPath (Join-Path $canonicalRoot $destinationName) -Parent $canonicalRoot
    if (Test-Path -LiteralPath $destination) {
        $existing = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $destination) -Force -ErrorAction Stop
        if ([int64]$existing.Length -ne $sourceSize -or
            (Get-Sha256Hex -LiteralPath $existing.FullName) -cne $hash) {
            throw "Content-addressed NSIS artifact has drifted"
        }
        return $existing.FullName
    }
    Move-Item -LiteralPath $source.FullName -Destination $destination -ErrorAction Stop
    $published = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $destination) -Force -ErrorAction Stop
    if ([int64]$published.Length -ne $sourceSize -or (Get-Sha256Hex -LiteralPath $published.FullName) -cne $hash) {
        throw "Immutable NSIS artifact changed while publishing"
    }
    return $published.FullName
}

function Publish-MihoImmutableStaticManifestV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$PendingManifest
    )

    $bundleRoot = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $Root "target\release\bundle")
    $pending = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $PendingManifest) -Force -ErrorAction Stop
    $prefix = $bundleRoot.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    if (-not $pending.FullName.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase) -or
        $pending.Name -cnotmatch '^\.miho-static-installed-payload-v1\.[0-9a-f]{32}\.pending\.json$') {
        throw "Static installed-payload pending manifest path is invalid"
    }
    $hash = Get-Sha256Hex -LiteralPath $pending.FullName
    $destination = Join-Path $bundleRoot "miho-static-installed-payload-v1.$hash.json"
    if (Test-Path -LiteralPath $destination) {
        $existing = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $destination) -Force -ErrorAction Stop
        if ([int64]$existing.Length -ne [int64]$pending.Length -or
            (Get-Sha256Hex -LiteralPath $existing.FullName) -cne $hash) {
            throw "Content-addressed installed-payload manifest has drifted"
        }
        Remove-Item -LiteralPath $pending.FullName -Force -ErrorAction Stop
        return $existing.FullName
    }
    Move-Item -LiteralPath $pending.FullName -Destination $destination -ErrorAction Stop
    $published = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $destination) -Force -ErrorAction Stop
    if ((Get-Sha256Hex -LiteralPath $published.FullName) -cne $hash) {
        throw "Immutable installed-payload manifest changed while publishing"
    }
    return $published.FullName
}

function New-MihoReleaseContextV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$StagingRoot,
        [Parameter(Mandatory = $true)][string]$StagedOverlay,
        [Parameter(Mandatory = $true)][string]$WorkspaceInputsSha256,
        [Parameter(Mandatory = $true)][string]$StagingTreeSha256,
        [Parameter(Mandatory = $true)][string]$ReleaseCli,
        [Parameter(Mandatory = $true)][string]$Sidecar
    )

    $contextRoot = Ensure-SafeDirectoryV1 -LiteralPath (Join-Path $Root "target\release\release-context")
    $nonce = [guid]::NewGuid().ToString("N")
    $path = Join-Path $contextRoot "tauri-release-$nonce.json"
    $context = [pscustomobject][ordered]@{
        schema_version = "miho-tauri-release-context-v1"
        nonce = $nonce
        workspace_root_sha256 = Get-Sha256HexForTextV1 -Text ([System.IO.Path]::GetFullPath($Root).TrimEnd("\", "/").ToLowerInvariant())
        staging_root_sha256 = Get-Sha256HexForTextV1 -Text ([System.IO.Path]::GetFullPath($StagingRoot).TrimEnd("\", "/").ToLowerInvariant())
        base_config_sha256 = Get-Sha256Hex -LiteralPath (Resolve-SafeFileV1 -LiteralPath (Join-Path $Root "crates\miho-desktop\src-tauri\tauri.conf.json"))
        release_config_sha256 = Get-Sha256Hex -LiteralPath (Resolve-SafeFileV1 -LiteralPath (Join-Path $Root "crates\miho-desktop\src-tauri\tauri.release.conf.json"))
        staged_overlay_sha256 = Get-Sha256Hex -LiteralPath (Resolve-SafeFileV1 -LiteralPath $StagedOverlay)
        workspace_inputs_sha256 = $WorkspaceInputsSha256
        staging_tree_sha256 = $StagingTreeSha256
        cli_sha256 = Get-Sha256Hex -LiteralPath (Resolve-SafeFileV1 -LiteralPath $ReleaseCli)
        sidecar_sha256 = Get-Sha256Hex -LiteralPath (Resolve-SafeFileV1 -LiteralPath $Sidecar)
    }
    Write-Utf8NoBom -LiteralPath $path -Text (($context | ConvertTo-Json -Depth 4 -Compress) + "`n")
    return Resolve-SafeFileV1 -LiteralPath $path
}

function Invoke-MihoTauriReleasePassV1 {
    param(
        [Parameter(Mandatory = $true)][string]$NodePath,
        [Parameter(Mandatory = $true)][string]$Overlay,
        [Parameter(Mandatory = $true)][string]$ContextPath,
        [Parameter(Mandatory = $true)][string]$WorkspaceRoot,
        [Parameter(Mandatory = $true)][string]$StagingRoot,
        [Parameter(Mandatory = $true)][string]$CargoTarget,
        [Parameter(Mandatory = $true)]
        [ValidateSet("build-no-bundle", "bundle")]
        [string]$PassKind
    )

    $nodeFile = Resolve-SafeFileV1 -LiteralPath $NodePath
    $overlayFile = Resolve-SafeFileV1 -LiteralPath $Overlay
    $contextFile = Resolve-SafeFileV1 -LiteralPath $ContextPath
    $workspace = Resolve-SafeDirectoryV1 -LiteralPath $WorkspaceRoot
    $staging = Resolve-SafeDirectoryV1 -LiteralPath $StagingRoot
    $target = Resolve-SafeDirectoryV1 -LiteralPath $CargoTarget
    $tauriArguments = if ($PassKind -ceq "build-no-bundle") {
        @(
            "node_modules\@tauri-apps\cli\tauri.js",
            "build",
            "--config",
            $overlayFile,
            "--no-bundle",
            "--features",
            "custom-protocol"
        )
    }
    else {
        @(
            "node_modules\@tauri-apps\cli\tauri.js",
            "bundle",
            "--bundles",
            "nsis",
            "--config",
            $overlayFile,
            "--features",
            "custom-protocol"
        )
    }

    $previousReleaseContext = $env:MIHO_RELEASE_CONTEXT_V1
    $previousWorkspaceRoot = $env:MIHO_RELEASE_WORKSPACE_ROOT_V1
    $previousStagingRoot = $env:MIHO_RELEASE_STAGING_ROOT_V1
    $previousCargoTarget = $env:CARGO_TARGET_DIR
    $env:MIHO_RELEASE_CONTEXT_V1 = $contextFile
    $env:MIHO_RELEASE_WORKSPACE_ROOT_V1 = $workspace
    $env:MIHO_RELEASE_STAGING_ROOT_V1 = $staging
    $env:CARGO_TARGET_DIR = $target
    $tauriSucceeded = $false
    try {
        Invoke-NativeCommand `
            -FilePath $nodeFile `
            -ArgumentList $tauriArguments `
            -FailureMessage ("Tauri release {0} pass failed" -f $PassKind)
        $tauriSucceeded = $true
    }
    finally {
        $env:MIHO_RELEASE_CONTEXT_V1 = $previousReleaseContext
        $env:MIHO_RELEASE_WORKSPACE_ROOT_V1 = $previousWorkspaceRoot
        $env:MIHO_RELEASE_STAGING_ROOT_V1 = $previousStagingRoot
        $env:CARGO_TARGET_DIR = $previousCargoTarget
        if (-not $tauriSucceeded -and (Test-Path -LiteralPath $contextFile)) {
            Remove-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $contextFile) -Force -ErrorAction Stop
            if (Test-Path -LiteralPath $contextFile) { throw "Failed release context remains replayable" }
        }
    }
    if (Test-Path -LiteralPath $contextFile) {
        throw "Tauri did not consume the one-use release context"
    }
}

function Get-Sha256HexForTextV1 {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        return (($sha256.ComputeHash($utf8.GetBytes($Text)) | ForEach-Object { $_.ToString("x2") }) -join "")
    }
    finally { $sha256.Dispose() }
}

function Assert-MihoTauriFrontendDistRelativeV1 {
    param(
        [Parameter(Mandatory = $true)][string]$ConfigDirectory,
        [Parameter(Mandatory = $true)][string]$FrontendDist,
        [Parameter(Mandatory = $true)][string]$ExpectedDirectory
    )

    $configRoot = Resolve-SafeDirectoryV1 -LiteralPath $ConfigDirectory
    $expected = Resolve-SafeDirectoryV1 -LiteralPath $ExpectedDirectory
    $absoluteUri = $null
    if ([string]::IsNullOrWhiteSpace($FrontendDist) -or
        [System.IO.Path]::IsPathRooted($FrontendDist) -or
        $FrontendDist.Contains("\") -or
        $FrontendDist.StartsWith("/", [System.StringComparison]::Ordinal) -or
        [System.Uri]::TryCreate($FrontendDist, [System.UriKind]::Absolute, [ref]$absoluteUri)) {
        throw "Tauri frontendDist must be a non-URL relative directory path"
    }

    $nativeRelative = $FrontendDist.Replace("/", [string][System.IO.Path]::DirectorySeparatorChar)
    $roundTripPath = [System.IO.Path]::GetFullPath((Join-Path $configRoot $nativeRelative))
    $roundTrip = Resolve-SafeDirectoryV1 -LiteralPath $roundTripPath
    if (-not [string]::Equals(
            $roundTrip,
            $expected,
            [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Tauri frontendDist does not resolve to immutable frontend staging"
    }
    return $FrontendDist
}

function Get-MihoTauriFrontendDistRelativeV1 {
    param(
        [Parameter(Mandatory = $true)][string]$ConfigDirectory,
        [Parameter(Mandatory = $true)][string]$FrontendDirectory
    )

    $configRoot = Resolve-SafeDirectoryV1 -LiteralPath $ConfigDirectory
    $frontendRoot = Resolve-SafeDirectoryV1 -LiteralPath $FrontendDirectory
    $configVolume = [System.IO.Path]::GetPathRoot($configRoot)
    $frontendVolume = [System.IO.Path]::GetPathRoot($frontendRoot)
    if ([string]::IsNullOrWhiteSpace($configVolume) -or
        -not [string]::Equals(
            $configVolume,
            $frontendVolume,
            [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Tauri config and immutable frontend staging must share a filesystem volume"
    }

    $separators = [char[]]@(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $configSegments = @($configRoot.Substring($configVolume.Length).Split(
            $separators,
            [System.StringSplitOptions]::RemoveEmptyEntries
        ))
    $frontendSegments = @($frontendRoot.Substring($frontendVolume.Length).Split(
            $separators,
            [System.StringSplitOptions]::RemoveEmptyEntries
        ))
    $commonCount = 0
    while ($commonCount -lt $configSegments.Count -and
        $commonCount -lt $frontendSegments.Count -and
        [string]::Equals(
            [string]$configSegments[$commonCount],
            [string]$frontendSegments[$commonCount],
            [System.StringComparison]::OrdinalIgnoreCase)) {
        $commonCount += 1
    }

    $relativeSegments = @()
    for ($index = $commonCount; $index -lt $configSegments.Count; $index += 1) {
        $relativeSegments += ".."
    }
    for ($index = $commonCount; $index -lt $frontendSegments.Count; $index += 1) {
        $relativeSegments += [string]$frontendSegments[$index]
    }
    $relative = if ($relativeSegments.Count -eq 0) {
        "."
    }
    else {
        [string]::Join("/", [string[]]$relativeSegments)
    }
    return Assert-MihoTauriFrontendDistRelativeV1 `
        -ConfigDirectory $configRoot `
        -FrontendDist $relative `
        -ExpectedDirectory $frontendRoot
}

function New-MihoImmutableReleaseStagingV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$SourceRoot,
        [Parameter(Mandatory = $true)][string]$DesktopRoot,
        [Parameter(Mandatory = $true)][string]$ProductVersion,
        [Parameter(Mandatory = $true)][string]$HostTriple,
        [Parameter(Mandatory = $true)][string]$ReleaseCli,
        [Parameter(Mandatory = $true)][string]$OwnershipDesktopExecutable,
        [string]$StagingNonce = ""
    )

    $workspace = Resolve-SafeDirectoryV1 -LiteralPath $Root
    $sourceWorkspace = Resolve-SafeDirectoryV1 -LiteralPath $SourceRoot
    $desktopDirectory = Resolve-SafeDirectoryV1 -LiteralPath $DesktopRoot
    $stagingParent = Ensure-SafeDirectoryV1 -LiteralPath (Join-Path $workspace "target\release\release-staging")
    $nonce = if ([string]::IsNullOrEmpty($StagingNonce)) {
        [guid]::NewGuid().ToString("N")
    }
    else {
        if ($StagingNonce -cnotmatch '^[0-9a-f]{32}$') {
            throw "Explicit release staging nonce is invalid"
        }
        $StagingNonce
    }
    $stagingRoot = Assert-PathBelow -LiteralPath (Join-Path $stagingParent "release-$nonce") -Parent $stagingParent
    if (Test-Path -LiteralPath $stagingRoot) {
        throw "Immutable release staging path already exists"
    }
    New-Item -ItemType Directory -Path $stagingRoot -ErrorAction Stop | Out-Null
    $stagingRoot = Resolve-SafeDirectoryV1 -LiteralPath $stagingRoot

    $resources = Join-Path $stagingRoot "resources"
    $packaging = Join-Path $stagingRoot "packaging"
    $sidecars = Join-Path $stagingRoot "sidecars"
    foreach ($directory in @($resources, $packaging, $sidecars)) {
        New-Item -ItemType Directory -Path $directory -ErrorAction Stop | Out-Null
        $null = Resolve-SafeDirectoryV1 -LiteralPath $directory
    }

    Copy-MihoSafeTreeV1 -Source (Join-Path $sourceWorkspace "configs") -Destination (Join-Path $resources "configs")
    $installerResources = Join-Path $resources "installer"
    New-Item -ItemType Directory -Path $installerResources -ErrorAction Stop | Out-Null
    foreach ($name in @(
        "task_scheduler_v1.ps1",
        "install_daily_update_task.ps1",
        "uninstall_daily_update_task.ps1",
        "installer_transaction_v1.ps1"
    )) {
        $source = Resolve-SafeFileV1 -LiteralPath (Join-Path $sourceWorkspace "scripts\$name")
        Copy-Item -LiteralPath $source -Destination (Join-Path $installerResources $name) -ErrorAction Stop
    }
    $portableResources = Join-Path $resources "portable"
    New-Item -ItemType Directory -Path $portableResources -ErrorAction Stop | Out-Null
    $portableWrapper = Resolve-SafeFileV1 -LiteralPath (Join-Path $sourceWorkspace "scripts\portable_daily_update_task.ps1")
    Copy-Item -LiteralPath $portableWrapper -Destination (Join-Path $portableResources "portable_daily_update_task.ps1") -ErrorAction Stop
    foreach ($mapping in @(
        [pscustomobject]@{ Source = Join-Path $desktopDirectory "src-tauri\installer.nsi"; Name = "installer.nsi" },
        [pscustomobject]@{ Source = Join-Path $desktopDirectory "src-tauri\nsis\installer-hooks.nsh"; Name = "installer-hooks.nsh" },
        [pscustomobject]@{ Source = Join-Path $sourceWorkspace "scripts\verify_tauri_release_context.ps1"; Name = "verify_tauri_release_context.ps1" }
    )) {
        $source = Resolve-SafeFileV1 -LiteralPath $mapping.Source
        Copy-Item -LiteralPath $source -Destination (Join-Path $packaging $mapping.Name) -ErrorAction Stop
    }
    $stagedInstaller = Resolve-SafeFileV1 -LiteralPath (Join-Path $packaging "installer.nsi")
    $installerBytes = [System.IO.File]::ReadAllBytes($stagedInstaller)
    $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
    $installerText = $strictUtf8.GetString($installerBytes)
    $verifyPlaceholder = "__MIHO_RELEASE_VERIFY_NONCE__"
    if (($installerText.Length - $installerText.Replace($verifyPlaceholder, "").Length) / $verifyPlaceholder.Length -ne 1) {
        throw "NSIS verification nonce placeholder is missing or duplicated"
    }
    Write-Utf8NoBom -LiteralPath $stagedInstaller -Text $installerText.Replace($verifyPlaceholder, $nonce)
    Copy-MihoSafeTreeV1 -Source (Join-Path $desktopDirectory "dist") -Destination (Join-Path $stagingRoot "frontend-dist")
    Copy-MihoSafeTreeV1 -Source (Join-Path $desktopDirectory "src-tauri\isolation") -Destination (Join-Path $stagingRoot "isolation")
    $tauriConfigDirectory = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $desktopDirectory "src-tauri")
    $frontendDirectory = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $stagingRoot "frontend-dist")
    $frontendDist = Get-MihoTauriFrontendDistRelativeV1 `
        -ConfigDirectory $tauriConfigDirectory `
        -FrontendDirectory $frontendDirectory

    $releaseCliFile = Resolve-SafeFileV1 -LiteralPath $ReleaseCli
    $sidecar = Join-Path $sidecars "miho-$HostTriple.exe"
    Copy-Item -LiteralPath $releaseCliFile -Destination $sidecar -ErrorAction Stop
    $sidecar = Resolve-SafeFileV1 -LiteralPath $sidecar
    if ((Get-Sha256Hex -LiteralPath $releaseCliFile) -cne (Get-Sha256Hex -LiteralPath $sidecar)) {
        throw "Immutable release sidecar hash does not match the release CLI"
    }

    $ownershipManifest = New-MihoStaticOwnershipManifestV1 `
        -ProductVersion $ProductVersion `
        -HostTriple $HostTriple `
        -StagingRoot $stagingRoot `
        -MainExecutable $OwnershipDesktopExecutable `
        -Sidecar $sidecar `
        -OutputPath (Join-Path $resources "miho-static-ownership-v1.json")

    $resourceMap = [ordered]@{}
    $resourceMap[(Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $resources "configs"))] = "defaults/configs"
    foreach ($name in @(
        "task_scheduler_v1.ps1",
        "install_daily_update_task.ps1",
        "uninstall_daily_update_task.ps1",
        "installer_transaction_v1.ps1"
    )) {
        $resourceMap[(Resolve-SafeFileV1 -LiteralPath (Join-Path $installerResources $name))] = "installer/$name"
    }
    $resourceMap[(Resolve-SafeFileV1 -LiteralPath $ownershipManifest)] = "miho-static-ownership-v1.json"
    $sidecarBase = $sidecar.Substring(0, $sidecar.Length - ("-$HostTriple.exe").Length)
    $verifier = Resolve-SafeFileV1 -LiteralPath (Join-Path $packaging "verify_tauri_release_context.ps1")
    $verifierInvocation = "& '" + $verifier.Replace("'", "''") + "'"
    $encodedVerifierInvocation = [System.Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($verifierInvocation))
    $overlay = [pscustomobject][ordered]@{
        build = [pscustomobject][ordered]@{
            beforeBuildCommand = "powershell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $encodedVerifierInvocation"
            beforeBundleCommand = "powershell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $encodedVerifierInvocation"
            frontendDist = $frontendDist
        }
        app = [pscustomobject][ordered]@{
            security = [pscustomobject][ordered]@{
                pattern = [pscustomobject][ordered]@{
                    use = "isolation"
                    options = [pscustomobject][ordered]@{
                        dir = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $stagingRoot "isolation")
                    }
                }
            }
        }
        bundle = [pscustomobject][ordered]@{
            active = $true
            targets = @("nsis")
            externalBin = @($sidecarBase)
            resources = $resourceMap
            windows = [pscustomobject][ordered]@{
                nsis = [pscustomobject][ordered]@{
                    installMode = "currentUser"
                    template = Resolve-SafeFileV1 -LiteralPath (Join-Path $packaging "installer.nsi")
                    installerHooks = Resolve-SafeFileV1 -LiteralPath (Join-Path $packaging "installer-hooks.nsh")
                }
            }
        }
    }
    $overlayPath = Join-Path $stagingRoot "tauri.release.staged.conf.json"
    Write-Utf8NoBom -LiteralPath $overlayPath -Text (($overlay | ConvertTo-Json -Depth 12 -Compress) + "`n")
    $overlayPath = Resolve-SafeFileV1 -LiteralPath $overlayPath
    $serializedOverlay = Read-MihoStrictJsonFileV1 -LiteralPath $overlayPath
    if ($serializedOverlay.build.PSObject.Properties["frontendDist"].Value -isnot [string] -or
        [string]$serializedOverlay.build.frontendDist -cne $frontendDist) {
        throw "Tauri frontendDist changed during release overlay serialization"
    }
    $null = Assert-MihoTauriFrontendDistRelativeV1 `
        -ConfigDirectory $tauriConfigDirectory `
        -FrontendDist ([string]$serializedOverlay.build.frontendDist) `
        -ExpectedDirectory $frontendDirectory
    $tree = Get-MihoTreeDigestV1 -LiteralPath $stagingRoot
    return [pscustomobject][ordered]@{
        Nonce = $nonce
        Root = $stagingRoot
        Overlay = $overlayPath
        Sidecar = $sidecar
        OwnershipManifest = $ownershipManifest
        TreeSha256 = $tree.digest
        FileCount = $tree.file_count
    }
}

function Write-MihoReleaseArtifactsManifestV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$ProductVersion,
        [Parameter(Mandatory = $true)][string]$HostTriple,
        [Parameter(Mandatory = $true)]$Portable,
        [Parameter(Mandatory = $true)][string]$InstalledPayloadManifest,
        [Parameter(Mandatory = $true)][bool]$NoBundleMode,
        [AllowNull()][string]$NsisInstaller,
        [Parameter(Mandatory = $true)]$GitProvenance,
        [Parameter(Mandatory = $true)]$WorkspaceInputs,
        [Parameter(Mandatory = $true)]$BuildWorkspaceInputs,
        [Parameter(Mandatory = $true)]$StagingEvidence,
        [Parameter(Mandatory = $true)]$ToolchainEvidence,
        [Parameter(Mandatory = $true)]$Publication
    )

    $nsisRecords = @()
    if (-not $NoBundleMode) {
        if ([string]::IsNullOrWhiteSpace($NsisInstaller)) { throw "Bundled release is missing its immutable NSIS installer" }
        $matching = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $NsisInstaller) -Force -ErrorAction Stop
        if ($matching.Extension -cne ".exe" -or $matching.Name -notlike "*$ProductVersion*") {
            throw "Immutable NSIS installer identity is invalid"
        }
        $nsisRecords = @($matching | ForEach-Object {
            [pscustomobject][ordered]@{
                file_name = $_.Name
                size = [int64]$_.Length
                sha256 = Get-Sha256Hex -LiteralPath $_.FullName
                authenticode_status = Get-AuthenticodeStatusV1 -LiteralPath $_.FullName
            }
        })
    }
    elseif (-not [string]::IsNullOrWhiteSpace($NsisInstaller)) {
        throw "No-bundle verification unexpectedly supplied an NSIS installer"
    }
    $payloadManifest = Resolve-SafeFileV1 -LiteralPath $Portable.PayloadManifest
    $installedPayloadManifest = Resolve-SafeFileV1 -LiteralPath $InstalledPayloadManifest
    $installedPayloadObject = Read-MihoStrictJsonFileV1 -LiteralPath $installedPayloadManifest
    $containerMappingState = if ($NoBundleMode) {
        "not-applicable-no-bundle"
    }
    elseif ([string]$installedPayloadObject.container_verification.status -ceq "verified") {
        "verified-from-container"
    }
    else {
        "pending-extraction-or-isolated-install-verification"
    }
    $archive = Resolve-SafeFileV1 -LiteralPath $Portable.Archive
    $manifest = [pscustomobject][ordered]@{
        schema_version = "miho-release-artifacts-v1"
        publication = [pscustomobject][ordered]@{
            state = [string]$Publication.state
            reason = [string]$Publication.reason
        }
        product_version = $ProductVersion
        target_triple = $HostTriple
        build_mode = $(if ($NoBundleMode) { "no-bundle" } else { "nsis-and-portable" })
        source = [pscustomobject][ordered]@{
            commit = [string]$GitProvenance.source_commit
            tree_state = [string]$GitProvenance.source_tree_state
            status_sha256 = [string]$GitProvenance.source_status_sha256
            status_entry_count = [int]$GitProvenance.source_status_entry_count
        }
        inputs = [pscustomobject][ordered]@{
            workspace_sha256 = [string]$WorkspaceInputs.digest
            workspace_file_count = [int]$WorkspaceInputs.file_count
            build_workspace_sha256 = [string]$BuildWorkspaceInputs.digest
            build_workspace_file_count = [int]$BuildWorkspaceInputs.file_count
            staging_sha256 = [string]$StagingEvidence.digest
            staging_file_count = [int]$StagingEvidence.file_count
        }
        toolchain = [pscustomobject][ordered]@{
            dependency_graph_state = [string]$ToolchainEvidence.dependency_graph_state
            pnpm_install_mode = [string]$ToolchainEvidence.pnpm_install_mode
            package_json_sha256 = [string]$ToolchainEvidence.package_json_sha256
            cargo_lock_sha256 = [string]$ToolchainEvidence.cargo_lock_sha256
            pnpm_lock_sha256 = [string]$ToolchainEvidence.pnpm_lock_sha256
            installed_pnpm_lock_sha256 = [string]$ToolchainEvidence.installed_pnpm_lock_sha256
            dependency_tree_sha256 = [string]$ToolchainEvidence.dependency_tree_sha256
            dependency_tree_entry_count = [int]$ToolchainEvidence.dependency_tree_entry_count
            dependency_tree_file_count = [int]$ToolchainEvidence.dependency_tree_file_count
            package_manager = [string]$ToolchainEvidence.package_manager
            node_engine = [string]$ToolchainEvidence.node_engine
            pnpm_engine = [string]$ToolchainEvidence.pnpm_engine
            node_version = [string]$ToolchainEvidence.node_version
            pnpm_version = [string]$ToolchainEvidence.pnpm_version
            node_executable_sha256 = [string]$ToolchainEvidence.node_executable_sha256
            pnpm_launcher_sha256 = [string]$ToolchainEvidence.pnpm_launcher_sha256
            typescript_entrypoint_sha256 = [string]$ToolchainEvidence.typescript_entrypoint_sha256
            vite_entrypoint_sha256 = [string]$ToolchainEvidence.vite_entrypoint_sha256
            tauri_entrypoint_sha256 = [string]$ToolchainEvidence.tauri_entrypoint_sha256
            rustc_release = [string]$ToolchainEvidence.rustc_release
            rustc_host = [string]$ToolchainEvidence.rustc_host
            rustc_vv_sha256 = [string]$ToolchainEvidence.rustc_vv_sha256
            cargo_version = [string]$ToolchainEvidence.cargo_version
        }
        portable = [pscustomobject][ordered]@{
            payload_id = $Portable.PayloadId
            archive_file_name = [System.IO.Path]::GetFileName($archive)
            archive_size = [int64](Get-Item -LiteralPath $archive -Force).Length
            archive_sha256 = Get-Sha256Hex -LiteralPath $archive
            payload_manifest_file_name = [System.IO.Path]::GetFileName($payloadManifest)
            payload_manifest_size = [int64](Get-Item -LiteralPath $payloadManifest -Force).Length
            payload_manifest_sha256 = Get-Sha256Hex -LiteralPath $payloadManifest
        }
        static_installed_payload = [pscustomobject][ordered]@{
            file_name = [System.IO.Path]::GetFileName($installedPayloadManifest)
            size = [int64](Get-Item -LiteralPath $installedPayloadManifest -Force).Length
            sha256 = Get-Sha256Hex -LiteralPath $installedPayloadManifest
            container_mapping_verification = $containerMappingState
        }
        nsis = $nsisRecords
        signing = [pscustomobject][ordered]@{
            artifact_state = "unsigned-or-unverified"
            order = "Final signing, when available, must happen before this manifest is regenerated and release archives are published."
            guarantee = "SHA-256 records final bytes observed by this build; non-Valid or unavailable Authenticode status is not a trust claim."
        }
    }
    $bundleRoot = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $Root "target\release\bundle")
    $output = Join-Path $bundleRoot (".miho-release-artifacts-v1.{0}.pending.json" -f [guid]::NewGuid().ToString("N"))
    if (Test-Path -LiteralPath $output) {
        throw "Random release manifest pending path already exists"
    }
    try {
        Write-Utf8NoBom -LiteralPath $output -Text (($manifest | ConvertTo-Json -Depth 8 -Compress) + "`n")
        return Resolve-SafeFileV1 -LiteralPath $output
    }
    catch {
        if (Test-Path -LiteralPath $output) {
            Remove-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $output) -Force -ErrorAction SilentlyContinue
        }
        throw
    }
}

function Get-MihoActiveReleaseAnchorStateV1 {
    param([Parameter(Mandatory = $true)][string]$Root)

    $bundleRootPath = Join-Path $Root "target\release\bundle"
    if (-not (Test-Path -LiteralPath $bundleRootPath)) {
        return [pscustomobject][ordered]@{ exists = $false; size = [int64]0; sha256 = "" }
    }
    $bundleRoot = Resolve-SafeDirectoryV1 -LiteralPath $bundleRootPath
    $activePath = Join-Path $bundleRoot "miho-release-artifacts-v1.json"
    if (-not (Test-Path -LiteralPath $activePath)) {
        return [pscustomobject][ordered]@{ exists = $false; size = [int64]0; sha256 = "" }
    }
    $active = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $activePath) -Force -ErrorAction Stop
    return [pscustomobject][ordered]@{
        exists = $true
        size = [int64]$active.Length
        sha256 = Get-Sha256Hex -LiteralPath $active.FullName
    }
}

function Publish-MihoReleaseArtifactsManifestV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$PendingManifest,
        [Parameter(Mandatory = $true)][ValidateSet("active", "verification-only")][string]$PublicationState,
        [Parameter(Mandatory = $true)]$ExpectedActiveAnchor
    )

    $bundleRoot = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $Root "target\release\bundle")
    $pending = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $PendingManifest) -Force -ErrorAction Stop
    $expectedPrefix = $bundleRoot.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    if (-not $pending.FullName.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or
        $pending.FullName.Substring($expectedPrefix.Length).Contains([System.IO.Path]::DirectorySeparatorChar) -or
        $pending.Name -cnotmatch '^\.miho-release-artifacts-v1\.([0-9a-f]{32})\.pending\.json$') {
        throw "Release manifest pending path is invalid"
    }
    $nonce = [string]$Matches[1]
    $pendingSize = [int64]$pending.Length
    $pendingHash = Get-Sha256Hex -LiteralPath $pending.FullName

    if ($PublicationState -ceq "active") {
        $destination = Join-Path $bundleRoot "miho-release-artifacts-v1.json"
        $current = Get-MihoActiveReleaseAnchorStateV1 -Root $Root
        if ([bool]$current.exists -ne [bool]$ExpectedActiveAnchor.exists -or
            ([bool]$current.exists -and (
                [int64]$current.size -ne [int64]$ExpectedActiveAnchor.size -or
                [string]$current.sha256 -cne [string]$ExpectedActiveAnchor.sha256
            ))) {
            throw "Active release manifest changed during the release transaction"
        }
        if ([bool]$current.exists) {
            $superseded = Join-Path $bundleRoot (".miho-release-artifacts-v1.{0}.superseded.json" -f [guid]::NewGuid().ToString("N"))
            if (Test-Path -LiteralPath $superseded) { throw "Random superseded-anchor path already exists" }
            [System.IO.File]::Replace($pending.FullName, $destination, $superseded, $true)
        }
        else {
            [System.IO.File]::Move($pending.FullName, $destination)
        }
    }
    else {
        $destination = Join-Path $bundleRoot "miho-release-verification-v1.$nonce.json"
        if (Test-Path -LiteralPath $destination) {
            throw "Release verification manifest destination already exists"
        }
        [System.IO.File]::Move($pending.FullName, $destination)
    }

    if (Test-Path -LiteralPath $pending.FullName) {
        throw "Published release manifest still has a pending alias"
    }
    $published = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $destination) -Force -ErrorAction Stop
    if ([int64]$published.Length -ne $pendingSize -or (Get-Sha256Hex -LiteralPath $published.FullName) -cne $pendingHash) {
        throw "Published release manifest bytes changed during atomic publication"
    }
    return [pscustomobject][ordered]@{
        Path = $published.FullName
        Size = $pendingSize
        Sha256 = $pendingHash
        State = $PublicationState
    }
}

function Publish-MihoReleaseArtifactsAfterCleanupV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$PendingManifest,
        [Parameter(Mandatory = $true)][ValidateSet("active", "verification-only")][string]$PublicationState,
        [Parameter(Mandatory = $true)]$ExpectedActiveAnchor,
        [AllowNull()][AllowEmptyString()][string]$CalibrationPayloadRoot
    )

    # All fallible scratch mutation must finish before the active anchor can
    # change. Any prepublication failure removes the ephemeral pending file
    # while leaving the previously observed active manifest untouched.
    try {
        if (-not [string]::IsNullOrEmpty($CalibrationPayloadRoot) -and
            (Test-Path -LiteralPath $CalibrationPayloadRoot)) {
            Remove-MihoSafeTreeV1 -LiteralPath $CalibrationPayloadRoot
        }
        Clear-MihoReleaseScratchV1 -Root $Root
        $published = Publish-MihoReleaseArtifactsManifestV1 `
            -Root $Root `
            -PendingManifest $PendingManifest `
            -PublicationState $PublicationState `
            -ExpectedActiveAnchor $ExpectedActiveAnchor
        return [pscustomobject][ordered]@{
            Manifest = $published
            ScratchCleaned = $true
        }
    }
    catch {
        $publicationError = $_
        if (Test-Path -LiteralPath $PendingManifest) {
            Remove-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $PendingManifest) -Force -ErrorAction Stop
        }
        throw $publicationError
    }
}

function Assert-MihoReleaseArtifactsManifestV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$BuildWorkspaceRoot,
        [Parameter(Mandatory = $true)][string]$ToolchainRoot,
        [Parameter(Mandatory = $true)][string]$ProductVersion,
        [Parameter(Mandatory = $true)][string]$HostTriple,
        [Parameter(Mandatory = $true)]$Portable,
        [Parameter(Mandatory = $true)][string]$InstalledPayloadManifest,
        [Parameter(Mandatory = $true)][bool]$NoBundleMode,
        [bool]$ProjectGatesApproved = $false,
        [AllowNull()][string]$NsisInstaller,
        [Parameter(Mandatory = $true)][string]$StagingRoot,
        [Parameter(Mandatory = $true)][string]$NodePath,
        [Parameter(Mandatory = $true)][string]$Manifest
    )

    $bundleRootForManifest = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $Root "target\release\bundle")
    $manifestFile = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $Manifest) -Force -ErrorAction Stop
    if (-not [string]::Equals((Split-Path -Parent $manifestFile.FullName), $bundleRootForManifest, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Release artifacts manifest is outside the canonical bundle directory"
    }
    $rootManifest = Read-MihoStrictJsonFileV1 -LiteralPath $manifestFile.FullName
    Assert-MihoExactObjectPropertiesV1 -Object $rootManifest -Names @(
        "schema_version", "publication", "product_version", "target_triple", "build_mode",
        "source", "inputs", "toolchain",
        "portable", "static_installed_payload", "nsis", "signing"
    )
    foreach ($field in @("schema_version", "product_version", "target_triple", "build_mode")) {
        Assert-MihoJsonValueTypeV1 -Value $rootManifest.$field -Kind string -Label $field
    }
    Assert-MihoJsonValueTypeV1 -Value $rootManifest.publication -Kind object -Label "publication"
    Assert-MihoJsonValueTypeV1 -Value $rootManifest.source -Kind object -Label "source"
    Assert-MihoJsonValueTypeV1 -Value $rootManifest.inputs -Kind object -Label "inputs"
    Assert-MihoJsonValueTypeV1 -Value $rootManifest.toolchain -Kind object -Label "toolchain"
    Assert-MihoJsonValueTypeV1 -Value $rootManifest.portable -Kind object -Label "portable"
    Assert-MihoJsonValueTypeV1 -Value $rootManifest.static_installed_payload -Kind object -Label "static_installed_payload"
    Assert-MihoJsonPropertyTypeV1 -Object $rootManifest -Name "nsis" -Kind array -Label "nsis"
    Assert-MihoJsonValueTypeV1 -Value $rootManifest.signing -Kind object -Label "signing"
    if ([string]$rootManifest.schema_version -cne "miho-release-artifacts-v1" -or
        [string]$rootManifest.product_version -cne $ProductVersion -or
        [string]$rootManifest.target_triple -cne $HostTriple -or
        [string]$rootManifest.build_mode -cne $(if ($NoBundleMode) { "no-bundle" } else { "nsis-and-portable" })) {
        throw "Final release artifacts identity is invalid"
    }

    $liveProvenance = Get-MihoGitProvenanceV1 -Root $Root
    $liveWorkspaceInputs = Get-MihoWorkspaceReleaseInputsDigestV1 -Root $Root
    $liveBuildWorkspaceInputs = Get-MihoWorkspaceReleaseInputsDigestV1 -Root $BuildWorkspaceRoot
    $liveStaging = Get-MihoTreeDigestV1 -LiteralPath $StagingRoot
    $liveToolchain = Get-MihoReleaseToolchainEvidenceV1 -Root $ToolchainRoot -NodePath $NodePath
    $expectedPublication = Get-MihoReleasePublicationDecisionV1 `
        -SourceTreeState ([string]$liveProvenance.source_tree_state) `
        -NoBundleMode $NoBundleMode `
        -ProjectGatesApproved $ProjectGatesApproved

    Assert-MihoExactObjectPropertiesV1 -Object $rootManifest.publication -Names @("state", "reason")
    foreach ($field in @("state", "reason")) {
        Assert-MihoJsonValueTypeV1 -Value $rootManifest.publication.$field -Kind string -Label "publication.$field"
    }
    if ([string]$rootManifest.publication.state -cne [string]$expectedPublication.state -or
        [string]$rootManifest.publication.reason -cne [string]$expectedPublication.reason) {
        throw "Release publication eligibility is stale or over-claims an active release"
    }

    Assert-MihoExactObjectPropertiesV1 -Object $rootManifest.source -Names @(
        "commit", "tree_state", "status_sha256", "status_entry_count"
    )
    foreach ($field in @("commit", "tree_state", "status_sha256")) {
        Assert-MihoJsonValueTypeV1 -Value $rootManifest.source.$field -Kind string -Label "source.$field"
    }
    Assert-MihoJsonValueTypeV1 -Value $rootManifest.source.status_entry_count -Kind integer -Label "source.status_entry_count"
    if ([string]$rootManifest.source.commit -cnotmatch '^[0-9a-f]{40}$' -or
        [string]$rootManifest.source.status_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        [int64]$rootManifest.source.status_entry_count -lt 0 -or
        [string]$rootManifest.source.commit -cne [string]$liveProvenance.source_commit -or
        [string]$rootManifest.source.tree_state -cne [string]$liveProvenance.source_tree_state -or
        [string]$rootManifest.source.status_sha256 -cne [string]$liveProvenance.source_status_sha256 -or
        [int64]$rootManifest.source.status_entry_count -ne [int64]$liveProvenance.source_status_entry_count) {
        throw "Release source provenance is stale"
    }

    Assert-MihoExactObjectPropertiesV1 -Object $rootManifest.inputs -Names @(
        "workspace_sha256", "workspace_file_count", "build_workspace_sha256",
        "build_workspace_file_count", "staging_sha256", "staging_file_count"
    )
    foreach ($field in @("workspace_sha256", "build_workspace_sha256", "staging_sha256")) {
        Assert-MihoJsonValueTypeV1 -Value $rootManifest.inputs.$field -Kind string -Label "inputs.$field"
    }
    foreach ($field in @("workspace_file_count", "build_workspace_file_count", "staging_file_count")) {
        Assert-MihoJsonValueTypeV1 -Value $rootManifest.inputs.$field -Kind integer -Label "inputs.$field"
    }
    if ([string]$rootManifest.inputs.workspace_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        [string]$rootManifest.inputs.build_workspace_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        [string]$rootManifest.inputs.staging_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        [int64]$rootManifest.inputs.workspace_file_count -lt 1 -or
        [int64]$rootManifest.inputs.build_workspace_file_count -lt 1 -or
        [int64]$rootManifest.inputs.staging_file_count -lt 1 -or
        [string]$rootManifest.inputs.workspace_sha256 -cne [string]$liveWorkspaceInputs.digest -or
        [int64]$rootManifest.inputs.workspace_file_count -ne [int64]$liveWorkspaceInputs.file_count -or
        [string]$rootManifest.inputs.build_workspace_sha256 -cne [string]$liveBuildWorkspaceInputs.digest -or
        [int64]$rootManifest.inputs.build_workspace_file_count -ne [int64]$liveBuildWorkspaceInputs.file_count -or
        [string]$liveWorkspaceInputs.digest -cne [string]$liveBuildWorkspaceInputs.digest -or
        [int64]$liveWorkspaceInputs.file_count -ne [int64]$liveBuildWorkspaceInputs.file_count -or
        [string]$rootManifest.inputs.staging_sha256 -cne [string]$liveStaging.digest -or
        [int64]$rootManifest.inputs.staging_file_count -ne [int64]$liveStaging.file_count) {
        throw "Release input evidence is stale"
    }

    $toolchainStringFields = @(
        "dependency_graph_state", "pnpm_install_mode", "package_json_sha256", "cargo_lock_sha256", "pnpm_lock_sha256",
        "installed_pnpm_lock_sha256", "dependency_tree_sha256", "package_manager", "node_engine", "pnpm_engine", "node_version",
        "pnpm_version", "node_executable_sha256", "pnpm_launcher_sha256", "typescript_entrypoint_sha256",
        "vite_entrypoint_sha256", "tauri_entrypoint_sha256", "rustc_release", "rustc_host",
        "rustc_vv_sha256", "cargo_version"
    )
    $toolchainIntegerFields = @("dependency_tree_entry_count", "dependency_tree_file_count")
    Assert-MihoExactObjectPropertiesV1 -Object $rootManifest.toolchain -Names @($toolchainStringFields + $toolchainIntegerFields)
    foreach ($field in $toolchainStringFields) {
        Assert-MihoJsonValueTypeV1 -Value $rootManifest.toolchain.$field -Kind string -Label "toolchain.$field"
        if ([string]$rootManifest.toolchain.$field -cne [string]$liveToolchain.$field) {
            throw "Release toolchain evidence is stale"
        }
    }
    foreach ($field in $toolchainIntegerFields) {
        Assert-MihoJsonValueTypeV1 -Value $rootManifest.toolchain.$field -Kind integer -Label "toolchain.$field"
        if ([int64]$rootManifest.toolchain.$field -ne [int64]$liveToolchain.$field -or
            [int64]$rootManifest.toolchain.$field -lt 1) {
            throw "Release dependency-tree count evidence is stale"
        }
    }
    foreach ($field in @(
        "package_json_sha256", "cargo_lock_sha256", "pnpm_lock_sha256", "installed_pnpm_lock_sha256", "dependency_tree_sha256",
        "node_executable_sha256", "pnpm_launcher_sha256", "typescript_entrypoint_sha256",
        "vite_entrypoint_sha256", "tauri_entrypoint_sha256", "rustc_vv_sha256"
    )) {
        if ([string]$rootManifest.toolchain.$field -cnotmatch '^[0-9a-f]{64}$') {
            throw "Release toolchain hash evidence is invalid"
        }
    }
    if ([string]$rootManifest.toolchain.dependency_graph_state -cne "frozen-lock-matches-isolated-full-dependency-tree-hash-bound" -or
        [string]$rootManifest.toolchain.pnpm_install_mode -cne "isolated-empty-tree-frozen-prefer-offline-force-verified-copy" -or
        [string]$rootManifest.toolchain.pnpm_lock_sha256 -cne [string]$rootManifest.toolchain.installed_pnpm_lock_sha256) {
        throw "Release dependency graph is not frozen"
    }

    Assert-MihoExactObjectPropertiesV1 -Object $rootManifest.portable -Names @(
        "payload_id", "archive_file_name", "archive_size", "archive_sha256",
        "payload_manifest_file_name", "payload_manifest_size", "payload_manifest_sha256"
    )
    foreach ($field in @("payload_id", "archive_file_name", "archive_sha256", "payload_manifest_file_name", "payload_manifest_sha256")) {
        Assert-MihoJsonValueTypeV1 -Value $rootManifest.portable.$field -Kind string -Label "portable.$field"
    }
    foreach ($field in @("archive_size", "payload_manifest_size")) {
        Assert-MihoJsonValueTypeV1 -Value $rootManifest.portable.$field -Kind integer -Label "portable.$field"
    }
    $archive = Resolve-SafeFileV1 -LiteralPath $Portable.Archive
    $payloadManifest = Resolve-SafeFileV1 -LiteralPath $Portable.PayloadManifest
    $portableDirectory = Resolve-SafeDirectoryV1 -LiteralPath ([string]$Portable.Directory)
    $portableRoot = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $bundleRootForManifest "portable")
    if (-not [string]::Equals((Split-Path -Parent $portableDirectory), $portableRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not [string]::Equals((Split-Path -Parent $archive), $portableRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not [string]::Equals((Split-Path -Parent $payloadManifest), $portableDirectory, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Release portable artifacts are outside the immutable canonical directory"
    }
    $portableValidation = Assert-MihoPortablePayloadManifestV1 `
        -Directory ([string]$Portable.Directory) `
        -Manifest $payloadManifest `
        -ProductVersion $ProductVersion `
        -HostTriple $HostTriple
    $expectedPayloadId = [string]$portableValidation.PayloadId
    $expectedPortableBaseName = "miho-endgame-$ProductVersion-$HostTriple-portable-$expectedPayloadId"
    if ([string]$Portable.PayloadId -cne $expectedPayloadId -or
        [System.IO.Path]::GetFileName(([string]$Portable.Directory).TrimEnd("\", "/")) -cne $expectedPortableBaseName -or
        [System.IO.Path]::GetFileName($archive) -cne "$expectedPortableBaseName.zip" -or
        [string]$rootManifest.portable.payload_id -cne $expectedPayloadId -or
        [string]$rootManifest.portable.archive_file_name -cne [System.IO.Path]::GetFileName($archive) -or
        [int64]$rootManifest.portable.archive_size -ne [int64](Get-Item -LiteralPath $archive -Force).Length -or
        [string]$rootManifest.portable.archive_sha256 -cne (Get-Sha256Hex -LiteralPath $archive) -or
        [string]$rootManifest.portable.payload_manifest_file_name -cne [System.IO.Path]::GetFileName($payloadManifest) -or
        [int64]$rootManifest.portable.payload_manifest_size -ne [int64](Get-Item -LiteralPath $payloadManifest -Force).Length -or
        [string]$rootManifest.portable.payload_manifest_sha256 -cne (Get-Sha256Hex -LiteralPath $payloadManifest)) {
        throw "Final release portable references are stale"
    }
    Assert-MihoZipMatchesDirectoryV1 -Archive $archive -Directory $Portable.Directory

    Assert-MihoExactObjectPropertiesV1 -Object $rootManifest.static_installed_payload -Names @(
        "file_name", "size", "sha256", "container_mapping_verification"
    )
    foreach ($field in @("file_name", "sha256", "container_mapping_verification")) {
        Assert-MihoJsonValueTypeV1 -Value $rootManifest.static_installed_payload.$field -Kind string -Label "static_installed_payload.$field"
    }
    Assert-MihoJsonValueTypeV1 -Value $rootManifest.static_installed_payload.size -Kind integer -Label "static_installed_payload.size"
    $installed = Resolve-SafeFileV1 -LiteralPath $InstalledPayloadManifest
    $installedHash = Get-Sha256Hex -LiteralPath $installed
    if (-not [string]::Equals((Split-Path -Parent $installed), $bundleRootForManifest, [System.StringComparison]::OrdinalIgnoreCase) -or
        [System.IO.Path]::GetFileName($installed) -cne "miho-static-installed-payload-v1.$installedHash.json") {
        throw "Installed-payload manifest is not content-addressed in the canonical bundle directory"
    }
    if ([string]$rootManifest.static_installed_payload.file_name -cne [System.IO.Path]::GetFileName($installed) -or
        [int64]$rootManifest.static_installed_payload.size -ne [int64](Get-Item -LiteralPath $installed -Force).Length -or
        [string]$rootManifest.static_installed_payload.sha256 -cne $installedHash) {
        throw "Final release installed-payload manifest reference is stale"
    }
    $installedValidation = Assert-MihoStaticInstalledPayloadManifestV1 `
        -Manifest $installed `
        -PortableDirectory ([string]$Portable.Directory) `
        -StagingRoot $StagingRoot `
        -ProductVersion $ProductVersion `
        -HostTriple $HostTriple
    $installedObject = $installedValidation.Manifest
    $installedFileCount = [int]$installedValidation.FileCount

    $nsisRecords = @($rootManifest.nsis)
    if ($NoBundleMode) {
        if (-not [string]::IsNullOrWhiteSpace($NsisInstaller)) {
            throw "No-bundle release supplied an NSIS artifact"
        }
        if ($nsisRecords.Count -ne 0 -or [string]$rootManifest.static_installed_payload.container_mapping_verification -cne "not-applicable-no-bundle") {
            throw "No-bundle release contains an NSIS trust claim"
        }
        if ([string]$installedObject.container_verification.status -cne "not-applicable-no-bundle" -or
            [string]$installedObject.container_verification.method -cne "none" -or
            [int64]$installedObject.container_verification.nsis_size -ne 0 -or
            -not [string]::IsNullOrEmpty([string]$installedObject.container_verification.nsis_sha256) -or
            [int64]$installedObject.container_verification.files_verified -ne 0) {
            throw "No-bundle installed-payload manifest contains a container trust claim"
        }
    }
    else {
        if ([string]::IsNullOrWhiteSpace($NsisInstaller) -or $nsisRecords.Count -ne 1) {
            throw "Final release NSIS file set is invalid"
        }
        $installer = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $NsisInstaller) -Force -ErrorAction Stop
        $canonicalNsisRoot = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $Root "target\release\bundle\nsis")
        $canonicalPrefix = $canonicalNsisRoot.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
        if (-not $installer.FullName.StartsWith($canonicalPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or
            $installer.FullName.Substring($canonicalPrefix.Length).Contains([System.IO.Path]::DirectorySeparatorChar)) {
            throw "Final release NSIS artifact is outside the immutable canonical directory"
        }
        Assert-MihoExactObjectPropertiesV1 -Object $nsisRecords[0] -Names @("file_name", "size", "sha256", "authenticode_status")
        foreach ($field in @("file_name", "sha256", "authenticode_status")) {
            Assert-MihoJsonValueTypeV1 -Value $nsisRecords[0].$field -Kind string -Label "nsis.$field"
        }
        Assert-MihoJsonValueTypeV1 -Value $nsisRecords[0].size -Kind integer -Label "nsis.size"
        if ([string]$nsisRecords[0].file_name -cne $installer.Name -or
            [int64]$nsisRecords[0].size -ne [int64]$installer.Length -or
            [string]$nsisRecords[0].sha256 -cne (Get-Sha256Hex -LiteralPath $installer.FullName) -or
            [string]$nsisRecords[0].authenticode_status -cne (Get-AuthenticodeStatusV1 -LiteralPath $installer.FullName) -or
            [string]$rootManifest.static_installed_payload.container_mapping_verification -cne "verified-from-container" -or
            [string]$installedObject.container_verification.status -cne "verified" -or
            [string]$installedObject.container_verification.method -cne "nsis-build-only-extraction" -or
            [int64]$installedObject.container_verification.nsis_size -ne [int64]$installer.Length -or
            [string]$installedObject.container_verification.nsis_sha256 -cne (Get-Sha256Hex -LiteralPath $installer.FullName) -or
            [int64]$installedObject.container_verification.files_verified -ne $installedFileCount) {
            throw "Final release NSIS reference or container verification is stale"
        }
    }
    Assert-MihoExactObjectPropertiesV1 -Object $rootManifest.signing -Names @(
        "artifact_state", "order", "guarantee"
    )
    foreach ($field in @("artifact_state", "order", "guarantee")) {
        Assert-MihoJsonValueTypeV1 -Value $rootManifest.signing.$field -Kind string -Label "signing.$field"
    }
    if ([string]$rootManifest.signing.artifact_state -cne "unsigned-or-unverified" -or
        [string]$rootManifest.signing.order -cne "Final signing, when available, must happen before this manifest is regenerated and release archives are published." -or
        [string]$rootManifest.signing.guarantee -cne "SHA-256 records final bytes observed by this build; non-Valid or unavailable Authenticode status is not a trust claim.") {
        throw "Final release signing boundary is invalid"
    }
    return $true
}

function New-MihoPortableBundle {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$ProductVersion,
        [Parameter(Mandatory = $true)][string]$HostTriple,
        [Parameter(Mandatory = $true)][string]$StagingRoot,
        [Parameter(Mandatory = $true)][string]$MainExecutable,
        [Parameter(Mandatory = $true)][string]$ReleaseCli
    )

    $version = $ProductVersion
    if ($version -notmatch '^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$') {
        throw "Tauri product version is not a supported release version"
    }
    $mainExecutable = Resolve-SafeFileV1 -LiteralPath $MainExecutable
    $releaseCliFile = Resolve-SafeFileV1 -LiteralPath $ReleaseCli
    $immutableStaging = Resolve-SafeDirectoryV1 -LiteralPath $StagingRoot

    $bundleRoot = Ensure-SafeDirectoryV1 -LiteralPath (Join-Path $Root "target\release\bundle")
    $portableParent = Ensure-SafeDirectoryV1 -LiteralPath (Join-Path $bundleRoot "portable")
    $stagingDirectory = Assert-PathBelow -LiteralPath (Join-Path $portableParent (".miho-portable-{0}.staging" -f [guid]::NewGuid().ToString("N"))) -Parent $portableParent

    New-Item -ItemType Directory -Path $stagingDirectory -ErrorAction Stop | Out-Null
    $temporaryZip = $null
    try {
        Copy-Item -LiteralPath $mainExecutable -Destination (Join-Path $stagingDirectory "miho-desktop.exe") -ErrorAction Stop
        Copy-Item -LiteralPath $releaseCliFile -Destination (Join-Path $stagingDirectory "miho.exe") -ErrorAction Stop
        Write-Utf8NoBom -LiteralPath (Join-Path $stagingDirectory "miho-portable-v1.json") -Text '{"schema_version":"miho-portable-v1","workspace":"data"}'
        Write-Utf8NoBom -LiteralPath (Join-Path $stagingDirectory "README-portable.txt") -Text @"
Miho Endgame portable contract

- Keep miho-desktop.exe, miho.exe, miho-portable-v1.json, miho-static-ownership-v1.json, defaults, automation, and this file together.
- Mutable workspace, Box, outputs, settings, and WebView2 storage live only below data/. Do not replace or delete data during an application upgrade.
- Moving the whole directory is supported only when no scheduled automation is bound. If automation was installed, uninstall it before the move and reinstall it afterward so its absolute workspace/action paths are rebound.
- MIHO_DATA_ROOT is an explicit installed-mode override. When it is set, portable marker semantics are disabled and the absolute override is used.
- Scheduled-task installation is opt-in through automation/portable_daily_update_task.ps1. Its persistent portable owner instance is read only from data/.miho/portable-identity-v1.json and must match before rebind or uninstall can change it; a foreign instance is always preserved.
- Release manifests record exact SHA-256 and observed Authenticode status. An unsigned build is not a trust claim.
"@

        $defaults = Join-Path $stagingDirectory "defaults"
        New-Item -ItemType Directory -Path $defaults -ErrorAction Stop | Out-Null
        Copy-MihoSafeTreeV1 -Source (Join-Path $immutableStaging "resources\configs") -Destination (Join-Path $defaults "configs")
        $ownershipManifest = Resolve-SafeFileV1 -LiteralPath (Join-Path $immutableStaging "resources\miho-static-ownership-v1.json")
        Copy-Item -LiteralPath $ownershipManifest -Destination (Join-Path $stagingDirectory "miho-static-ownership-v1.json") -ErrorAction Stop

        $automation = Join-Path $stagingDirectory "automation"
        New-Item -ItemType Directory -Path $automation -ErrorAction Stop | Out-Null
        foreach ($name in @("task_scheduler_v1.ps1", "install_daily_update_task.ps1", "uninstall_daily_update_task.ps1")) {
            $sourceScript = Resolve-SafeFileV1 -LiteralPath (Join-Path $immutableStaging "resources\installer\$name")
            Copy-Item -LiteralPath $sourceScript -Destination (Join-Path $automation $name) -ErrorAction Stop
        }
        $portableWrapper = Resolve-SafeFileV1 -LiteralPath (Join-Path $immutableStaging "resources\portable\portable_daily_update_task.ps1")
        Copy-Item -LiteralPath $portableWrapper -Destination (Join-Path $automation "portable_daily_update_task.ps1") -ErrorAction Stop

        $payloadFiles = @(Sort-MihoObjectsByStringPropertyOrdinalV1 `
            -Values @(Get-MihoSafeFilesV1 -LiteralPath $stagingDirectory) `
            -Property "FullName")
        foreach ($file in $payloadFiles) {
            $lowerName = $file.Name.ToLowerInvariant()
            if ($lowerName -match '^python(?:\d+(?:\.\d+)*)?\.exe$' -or
                $lowerName -match '^python.*\.dll$' -or
                $lowerName.EndsWith(".py") -or
                $lowerName.EndsWith(".pyc")) {
                throw "Portable bundle unexpectedly contains a Python runtime or source payload"
            }
        }

        $rootPrefix = [System.IO.Path]::GetFullPath($stagingDirectory).TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
        $fileRecords = @(
            foreach ($file in $payloadFiles) {
                $relative = $file.FullName.Substring($rootPrefix.Length).Replace("\", "/")
                [pscustomobject][ordered]@{
                    path = $relative
                    size = [int64]$file.Length
                    sha256 = Get-Sha256Hex -LiteralPath $file.FullName
                }
            }
        )
        $signatureRecords = @(
            foreach ($relative in @("miho-desktop.exe", "miho.exe")) {
                [pscustomobject][ordered]@{
                    path = $relative
                    authenticode_status = Get-AuthenticodeStatusV1 -LiteralPath (Join-Path $stagingDirectory $relative)
                }
            }
        )
        $manifest = [pscustomobject][ordered]@{
            schema_version = "miho-release-files-v1"
            product_version = $version
            target_triple = $HostTriple
            files = $fileRecords
            signature_boundary = [pscustomobject][ordered]@{
                guarantee = "This manifest records payload size and SHA-256 only; it does not claim Authenticode trust."
                executables = $signatureRecords
                nsis_container = "The NSIS container and external miho.exe require release-pipeline signing outside this repository unless their status is Valid."
            }
        }
        Write-Utf8NoBom -LiteralPath (Join-Path $stagingDirectory "miho-release-files-v1.json") -Text (($manifest | ConvertTo-Json -Depth 8 -Compress) + "`n")
        $manifestPath = Resolve-SafeFileV1 -LiteralPath (Join-Path $stagingDirectory "miho-release-files-v1.json")
        $payloadId = (Get-Sha256Hex -LiteralPath $manifestPath).Substring(0, 16)
        $bundleName = "miho-endgame-$version-$HostTriple-portable-$payloadId"
        $bundleDirectory = Assert-PathBelow -LiteralPath (Join-Path $portableParent $bundleName) -Parent $portableParent
        $zipPath = Assert-PathBelow -LiteralPath (Join-Path $portableParent "$bundleName.zip") -Parent $portableParent
        $temporaryZip = Assert-PathBelow -LiteralPath (Join-Path $portableParent (".$bundleName.$([guid]::NewGuid().ToString('N')).zip.tmp")) -Parent $portableParent

        $null = New-MihoDeterministicZipV1 -Directory $stagingDirectory -OutputPath $temporaryZip

        if (Test-Path -LiteralPath $bundleDirectory) {
            $existingDirectory = Resolve-SafeDirectoryV1 -LiteralPath $bundleDirectory
            $stagingPrefix = [System.IO.Path]::GetFullPath($stagingDirectory).TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
            $existingPrefix = [System.IO.Path]::GetFullPath($existingDirectory).TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
            $stagedFiles = @(Get-MihoSafeFilesV1 -LiteralPath $stagingDirectory)
            $existingFiles = @(Get-MihoSafeFilesV1 -LiteralPath $existingDirectory)
            $stagedRelative = @(Sort-MihoStringsOrdinalV1 -Values @(
                $stagedFiles | ForEach-Object { $_.FullName.Substring($stagingPrefix.Length).Replace("\", "/") }
            ))
            $existingRelative = @(Sort-MihoStringsOrdinalV1 -Values @(
                $existingFiles | ForEach-Object { $_.FullName.Substring($existingPrefix.Length).Replace("\", "/") }
            ))
            if ($stagedRelative.Count -ne $existingRelative.Count -or
                [string]::Join("`n", $stagedRelative) -cne [string]::Join("`n", $existingRelative)) {
                throw "Content-addressed portable payload file set has drifted; preserving it unchanged"
            }
            foreach ($stagedFile in $stagedFiles) {
                $relative = $stagedFile.FullName.Substring($stagingPrefix.Length)
                $existingFile = Resolve-SafeFileV1 -LiteralPath (Join-Path $existingDirectory $relative)
                if ($stagedFile.Length -ne (Get-Item -LiteralPath $existingFile -Force).Length -or
                    (Get-Sha256Hex -LiteralPath $stagedFile.FullName) -cne (Get-Sha256Hex -LiteralPath $existingFile)) {
                    throw "Content-addressed portable payload has drifted; preserving it unchanged"
                }
            }
        }
        else {
            Move-Item -LiteralPath $stagingDirectory -Destination $bundleDirectory -ErrorAction Stop
            $null = Resolve-SafeDirectoryV1 -LiteralPath $bundleDirectory
        }

        if (Test-Path -LiteralPath $zipPath) {
            $existingZip = Resolve-SafeFileV1 -LiteralPath $zipPath
            Assert-MihoZipMatchesDirectoryV1 -Archive $existingZip -Directory $bundleDirectory
            $newZip = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $temporaryZip) -Force -ErrorAction Stop
            $existingZipItem = Get-Item -LiteralPath $existingZip -Force -ErrorAction Stop
            if ([int64]$existingZipItem.Length -ne [int64]$newZip.Length -or
                (Get-Sha256Hex -LiteralPath $existingZipItem.FullName) -cne (Get-Sha256Hex -LiteralPath $newZip.FullName)) {
                throw "Content-addressed portable ZIP bytes have drifted; preserving the existing archive"
            }
            Remove-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $temporaryZip) -Force -ErrorAction Stop
            $zipFile = $existingZip
        }
        else {
            Move-Item -LiteralPath $temporaryZip -Destination $zipPath -ErrorAction Stop
            $zipFile = Resolve-SafeFileV1 -LiteralPath $zipPath
            Assert-MihoZipMatchesDirectoryV1 -Archive $zipFile -Directory $bundleDirectory
        }
        return [pscustomobject][ordered]@{
            Directory = [System.IO.Path]::GetFullPath($bundleDirectory)
            Archive = $zipFile
            ArchiveSha256 = Get-Sha256Hex -LiteralPath $zipFile
            PayloadManifest = Join-Path ([System.IO.Path]::GetFullPath($bundleDirectory)) "miho-release-files-v1.json"
            PayloadId = $payloadId
        }
    }
    finally {
        if ($null -ne $temporaryZip -and (Test-Path -LiteralPath $temporaryZip)) {
            $temporaryZip = Assert-PathBelow -LiteralPath $temporaryZip -Parent $portableParent
            Remove-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $temporaryZip) -Force -ErrorAction Stop
        }
        if (Test-Path -LiteralPath $stagingDirectory) {
            $null = Assert-PathBelow -LiteralPath $stagingDirectory -Parent $portableParent
            Remove-MihoSafeTreeV1 -LiteralPath $stagingDirectory
        }
    }
}

function Test-MihoCanonicalUuidTextV1 {
    param([Parameter(Mandatory = $true)][string]$Value)

    if ($Value -cnotmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$') {
        return $false
    }
    try {
        return ([guid]::Parse($Value)).ToString() -ceq $Value
    }
    catch {
        return $false
    }
}

function Get-MihoInstalledAutomationOwnerInstanceIdV1 {
    param([string]$RegistrySubKey = "Software\com.miho.endgame")

    if ($RegistrySubKey -cne "Software\com.miho.endgame" -and
        $RegistrySubKey -cnotmatch '^Software\\com\.miho\.endgame\\tests\\[0-9a-f]{32}$') {
        throw "Installed GUI verification registry scope is invalid"
    }
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($RegistrySubKey, $false)
    if ($null -eq $key) { return $null }
    try {
        $valueName = "AutomationOwnerInstanceIdV1"
        if (-not (@($key.GetValueNames()) -ccontains $valueName)) { return $null }
        if ($key.GetValueKind($valueName) -ne [Microsoft.Win32.RegistryValueKind]::String) {
            throw "Installed automation owner registry value has the wrong type"
        }
        $value = $key.GetValue(
            $valueName,
            $null,
            [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames
        )
        if ($value -isnot [string] -or -not (Test-MihoCanonicalUuidTextV1 -Value ([string]$value))) {
            throw "Installed automation owner registry value is invalid"
        }
        return [string]$value
    }
    finally {
        $key.Dispose()
    }
}

function Resolve-MihoPackagedGuiVerificationModeV1 {
    param(
        [AllowNull()][AllowEmptyString()][string]$InstalledOwnerInstanceId,
        [Parameter(Mandatory = $true)][bool]$RequireInstalledMode
    )

    if ([string]::IsNullOrEmpty($InstalledOwnerInstanceId)) {
        if ($RequireInstalledMode) {
            throw "Active publication requires a real installed owner for the packaged GUI gate"
        }
        return "Portable"
    }
    if (-not (Test-MihoCanonicalUuidTextV1 -Value $InstalledOwnerInstanceId)) {
        throw "Packaged GUI verification owner identity is invalid"
    }
    return "Installed"
}

function Get-MihoGuiStateTreeEvidenceV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $rootDirectory = Resolve-SafeDirectoryV1 -LiteralPath $LiteralPath
    $prefix = $rootDirectory.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    $records = New-Object 'System.Collections.Generic.List[string]'
    $stack = New-Object 'System.Collections.Generic.Stack[string]'
    $stack.Push($rootDirectory)
    $fileCount = 0
    $directoryCount = 1
    $totalBytes = [int64]0
    while ($stack.Count -gt 0) {
        $directory = $stack.Pop()
        foreach ($entry in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
            if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Installed GUI state tree contains a reparse point"
            }
            $relative = $entry.FullName.Substring($prefix.Length).Replace("\", "/")
            if ($entry.PSIsContainer) {
                $records.Add("D:$($relative.Length):$relative")
                $directoryCount += 1
                $stack.Push((Resolve-SafeDirectoryV1 -LiteralPath $entry.FullName))
            }
            else {
                $file = Resolve-SafeFileV1 -LiteralPath $entry.FullName
                $hash = Get-Sha256Hex -LiteralPath $file
                $records.Add("F:$($relative.Length):${relative}:$([int64]$entry.Length):$hash")
                $fileCount += 1
                $totalBytes += [int64]$entry.Length
            }
        }
    }
    $records.Sort([System.StringComparer]::Ordinal)
    return [pscustomobject][ordered]@{
        path = $rootDirectory
        digest = Get-Sha256HexForTextV1 -Text ([string]::Join("`n", @($records)))
        file_count = $fileCount
        directory_count = $directoryCount
        total_bytes = $totalBytes
    }
}

function Get-MihoOptionalGuiStateTreeEvidenceV1 {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $full = Assert-NoReparseChainV1 -LiteralPath $LiteralPath
    if (-not (Test-Path -LiteralPath $full)) {
        return [pscustomobject][ordered]@{
            path = [System.IO.Path]::GetFullPath($full)
            exists = $false
            digest = ""
            file_count = 0
            directory_count = 0
            total_bytes = [int64]0
        }
    }
    $tree = Get-MihoGuiStateTreeEvidenceV1 -LiteralPath $full
    return [pscustomobject][ordered]@{
        path = [string]$tree.path
        exists = $true
        digest = [string]$tree.digest
        file_count = [int]$tree.file_count
        directory_count = [int]$tree.directory_count
        total_bytes = [int64]$tree.total_bytes
    }
}

function Get-MihoInstalledGuiExternalStateV1 {
    param([Parameter(Mandatory = $true)][string]$ExpectedOwnerInstanceId)

    $owner = Get-MihoInstalledAutomationOwnerInstanceIdV1
    if ([string]$owner -cne $ExpectedOwnerInstanceId) {
        throw "Installed automation owner changed before GUI verification"
    }
    $roamingRoot = [Environment]::GetFolderPath([Environment+SpecialFolder]::ApplicationData)
    $localRoot = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
    if ([string]::IsNullOrWhiteSpace($roamingRoot) -or [string]::IsNullOrWhiteSpace($localRoot)) {
        throw "Installed GUI verification could not resolve AppData"
    }
    $appData = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $roamingRoot "com.miho.endgame")
    $settingsPath = Join-Path $appData "desktop-settings-v1.json"
    if (Test-Path -LiteralPath $settingsPath) {
        $settings = Read-MihoStrictJsonFileV1 -LiteralPath (Resolve-SafeFileV1 -LiteralPath $settingsPath)
        Assert-MihoExactObjectPropertiesV1 -Object $settings -Names @(
            "schema_version", "selected_workspace", "revision"
        )
        Assert-MihoJsonValueTypeV1 -Value $settings.schema_version -Kind string -Label "desktop_settings.schema_version"
        Assert-MihoJsonValueTypeV1 -Value $settings.selected_workspace -Kind string -Label "desktop_settings.selected_workspace"
        Assert-MihoJsonValueTypeV1 -Value $settings.revision -Kind integer -Label "desktop_settings.revision"
        if ([string]$settings.schema_version -cne "miho-desktop-settings-v1" -or [int64]$settings.revision -le 0) {
            throw "Installed desktop settings are invalid"
        }
        $workspace = Resolve-SafeDirectoryV1 -LiteralPath ([string]$settings.selected_workspace)
    }
    else {
        $workspace = $appData
    }

    $automationRoot = Resolve-SafeDirectoryV1 -LiteralPath (Join-Path $localRoot "com.miho.endgame.automation")
    $authorityPath = Resolve-SafeFileV1 -LiteralPath (Join-Path $automationRoot "automation-authority-v1.json")
    $authority = Read-MihoStrictJsonFileV1 -LiteralPath $authorityPath
    Assert-MihoExactObjectPropertiesV1 -Object $authority -Names @(
        "schema", "owner_kind", "owner_instance_id", "owner_epoch", "owner_sid",
        "task_name", "task_path", "automation_root"
    )
    foreach ($field in @(
        "schema", "owner_kind", "owner_instance_id", "owner_epoch", "owner_sid",
        "task_name", "task_path", "automation_root"
    )) {
        Assert-MihoJsonValueTypeV1 -Value $authority.$field -Kind string -Label "automation_authority.$field"
    }
    if ([string]$authority.schema -cne "miho-automation-authority-v1" -or
        [string]$authority.owner_kind -cne "installed" -or
        [string]$authority.owner_instance_id -cne $ExpectedOwnerInstanceId -or
        -not (Test-MihoCanonicalUuidTextV1 -Value ([string]$authority.owner_epoch)) -or
        [string]$authority.owner_sid -cnotmatch '^S-1-' -or
        [string]$authority.task_name -cnotmatch '^MihoEndgameDailyUpdate-[0-9a-f]{16}$' -or
        [string]$authority.task_path -cne "\" -or
        -not [string]::Equals(
            [System.IO.Path]::GetFullPath([string]$authority.automation_root).TrimEnd("\", "/"),
            $automationRoot.TrimEnd("\", "/"),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw "Installed automation authority is invalid before GUI verification"
    }

    $service = $null
    $folder = $null
    $task = $null
    try {
        $service = New-Object -ComObject "Schedule.Service"
        $service.Connect()
        $folder = $service.GetFolder([string]$authority.task_path)
        $task = $folder.GetTask([string]$authority.task_name)
        $taskXml = [string]$task.Xml
        $taskSddl = [string]$task.GetSecurityDescriptor(7)
        if ([string]::IsNullOrWhiteSpace($taskXml) -or [string]::IsNullOrWhiteSpace($taskSddl)) {
            throw "Installed scheduled task evidence is incomplete"
        }
        $taskEvidence = [pscustomobject][ordered]@{
            name = [string]$authority.task_name
            path = [string]$authority.task_path
            xml_sha256 = Get-Sha256HexForTextV1 -Text $taskXml
            sddl_sha256 = Get-Sha256HexForTextV1 -Text $taskSddl
            enabled = [bool]$task.Enabled
            state = [int]$task.State
            last_task_result = [int]$task.LastTaskResult
            last_run_utc_ticks = [int64]([datetime]$task.LastRunTime).ToUniversalTime().Ticks
        }
    }
    finally {
        foreach ($comObject in @($task, $folder, $service)) {
            if ($null -ne $comObject) {
                try { $null = [Runtime.InteropServices.Marshal]::FinalReleaseComObject($comObject) }
                catch {}
            }
        }
    }

    $appDataTree = Get-MihoGuiStateTreeEvidenceV1 -LiteralPath $appData
    $workspaceTree = if ([string]::Equals($workspace, $appData, [System.StringComparison]::OrdinalIgnoreCase)) {
        $appDataTree
    }
    else {
        Get-MihoGuiStateTreeEvidenceV1 -LiteralPath $workspace
    }
    return [pscustomobject][ordered]@{
        owner_instance_id = $owner
        authority_sha256 = Get-Sha256Hex -LiteralPath $authorityPath
        task = $taskEvidence
        automation = Get-MihoGuiStateTreeEvidenceV1 -LiteralPath $automationRoot
        app_data = $appDataTree
        selected_workspace = $workspaceTree
        default_webview = Get-MihoOptionalGuiStateTreeEvidenceV1 `
            -LiteralPath (Join-Path $localRoot "com.miho.endgame")
    }
}

function Assert-MihoInstalledGuiExternalStateUnchangedV1 {
    param(
        [Parameter(Mandatory = $true)]$Before,
        [Parameter(Mandatory = $true)]$After
    )

    $beforeStable = [pscustomobject][ordered]@{
        owner_instance_id = [string]$Before.owner_instance_id
        authority_sha256 = [string]$Before.authority_sha256
        task = $Before.task
        automation = $Before.automation
        app_data = $Before.app_data
        selected_workspace = $Before.selected_workspace
    }
    $afterStable = [pscustomobject][ordered]@{
        owner_instance_id = [string]$After.owner_instance_id
        authority_sha256 = [string]$After.authority_sha256
        task = $After.task
        automation = $After.automation
        app_data = $After.app_data
        selected_workspace = $After.selected_workspace
    }
    $beforeJson = $beforeStable | ConvertTo-Json -Depth 10 -Compress
    $afterJson = $afterStable | ConvertTo-Json -Depth 10 -Compress
    if ($beforeJson -cne $afterJson) {
        throw "Installed GUI verification changed owner, task, automation, workspace, or roaming AppData state"
    }
    $beforeWebView = $Before.default_webview
    $afterWebView = $After.default_webview
    if ([string]$beforeWebView.path -cne [string]$afterWebView.path -or
        -not [bool]$afterWebView.exists -or
        [Math]::Abs([int64]$afterWebView.total_bytes - [int64]$beforeWebView.total_bytes) -gt 134217728 -or
        [Math]::Abs([int]$afterWebView.file_count - [int]$beforeWebView.file_count) -gt 4096 -or
        [Math]::Abs([int]$afterWebView.directory_count - [int]$beforeWebView.directory_count) -gt 1024) {
        throw "Installed GUI verification produced an unbounded default WebView cache change"
    }
}

function New-MihoInstalledGuiSmokeLayoutV1 {
    param(
        [Parameter(Mandatory = $true)][string]$StagingRoot,
        [Parameter(Mandatory = $true)][string]$PortableDirectory,
        [Parameter(Mandatory = $true)][string]$InstalledPayloadManifest,
        [Parameter(Mandatory = $true)][string]$ProductVersion,
        [Parameter(Mandatory = $true)][string]$HostTriple,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    $staging = Resolve-SafeDirectoryV1 -LiteralPath $StagingRoot
    $portable = Resolve-SafeDirectoryV1 -LiteralPath $PortableDirectory
    $manifestPath = Resolve-SafeFileV1 -LiteralPath $InstalledPayloadManifest
    $validation = Assert-MihoStaticInstalledPayloadManifestV1 `
        -Manifest $manifestPath `
        -PortableDirectory $portable `
        -StagingRoot $staging `
        -ProductVersion $ProductVersion `
        -HostTriple $HostTriple
    $expected = @(Get-MihoExpectedStaticInstalledFilesV1 `
        -PortableDirectory $portable `
        -StagingRoot $staging)
    if ($expected.Count -ne [int]$validation.FileCount -or (Test-Path -LiteralPath $Destination)) {
        throw "Installed GUI smoke layout destination or file set is invalid"
    }
    New-Item -ItemType Directory -Path $Destination -ErrorAction Stop | Out-Null
    $destinationRoot = Resolve-SafeDirectoryV1 -LiteralPath $Destination
    foreach ($record in $expected) {
        $relative = [string]$record.InstallPath
        Assert-MihoReleaseRelativePathV1 -Path $relative -Label "installed_gui_smoke.install_path"
        $target = Assert-PathBelow -LiteralPath (Join-Path $destinationRoot $relative) -Parent $destinationRoot
        $targetParent = Split-Path -Parent $target
        if (-not (Test-Path -LiteralPath $targetParent)) {
            New-Item -ItemType Directory -Path $targetParent -Force -ErrorAction Stop | Out-Null
        }
        $null = Resolve-SafeDirectoryV1 -LiteralPath $targetParent
        $source = Resolve-SafeFileV1 -LiteralPath ([string]$record.Source)
        Copy-Item -LiteralPath $source -Destination $target -ErrorAction Stop
        $copied = Resolve-SafeFileV1 -LiteralPath $target
        if ([int64](Get-Item -LiteralPath $copied -Force).Length -ne [int64](Get-Item -LiteralPath $source -Force).Length -or
            (Get-Sha256Hex -LiteralPath $copied) -cne (Get-Sha256Hex -LiteralPath $source)) {
            throw "Installed GUI smoke layout copy drifted"
        }
    }
    $actual = @(Get-MihoSafeFilesV1 -LiteralPath $destinationRoot)
    if ($actual.Count -ne $expected.Count -or
        (Test-Path -LiteralPath (Join-Path $destinationRoot "miho-portable-v1.json"))) {
        throw "Installed GUI smoke layout contains a missing, extra, or portable file"
    }
    $manifest = $validation.Manifest
    foreach ($record in @($manifest.files)) {
        $path = Resolve-SafeFileV1 -LiteralPath (Join-Path $destinationRoot ([string]$record.install_path))
        if ([int64](Get-Item -LiteralPath $path -Force).Length -ne [int64]$record.size -or
            (Get-Sha256Hex -LiteralPath $path) -cne [string]$record.sha256) {
            throw "Installed GUI smoke layout differs from the installed payload manifest"
        }
    }
    return Resolve-SafeFileV1 -LiteralPath (Join-Path $destinationRoot "miho-desktop.exe")
}

function Invoke-MihoPackagedGuiRenderVerificationV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$BuildWorkspaceRoot,
        [Parameter(Mandatory = $true)][string]$ReleaseStagingRoot,
        [Parameter(Mandatory = $true)][string]$PortableDirectory,
        [Parameter(Mandatory = $true)][string]$InstalledPayloadManifest,
        [Parameter(Mandatory = $true)][string]$ProductVersion,
        [Parameter(Mandatory = $true)][string]$HostTriple,
        [Parameter(Mandatory = $true)][bool]$RequireInstalledMode
    )

    $workspace = Resolve-SafeDirectoryV1 -LiteralPath $Root
    $buildWorkspace = Resolve-SafeDirectoryV1 -LiteralPath $BuildWorkspaceRoot
    $releaseStaging = Resolve-SafeDirectoryV1 -LiteralPath $ReleaseStagingRoot
    $smokeParent = Resolve-SafeDirectoryV1 -LiteralPath (Split-Path -Parent $releaseStaging)
    $portable = Resolve-SafeDirectoryV1 -LiteralPath $PortableDirectory
    $probeScript = Resolve-SafeFileV1 -LiteralPath (Join-Path $buildWorkspace "scripts\verify_gui_render_v1.ps1")
    $smokeRoot = Assert-PathBelow `
        -LiteralPath (Join-Path $smokeParent ("gui-render-" + [guid]::NewGuid().ToString("N"))) `
        -Parent $smokeParent
    if (Test-Path -LiteralPath $smokeRoot) {
        throw "GUI render smoke root already exists"
    }
    try {
        $installedOwner = Get-MihoInstalledAutomationOwnerInstanceIdV1
        $verificationMode = Resolve-MihoPackagedGuiVerificationModeV1 `
            -InstalledOwnerInstanceId $installedOwner `
            -RequireInstalledMode $RequireInstalledMode
        $externalStateBefore = $null
        if ($verificationMode -ceq "Installed") {
            $smokeExecutable = New-MihoInstalledGuiSmokeLayoutV1 `
                -StagingRoot $releaseStaging `
                -PortableDirectory $portable `
                -InstalledPayloadManifest $InstalledPayloadManifest `
                -ProductVersion $ProductVersion `
                -HostTriple $HostTriple `
                -Destination $smokeRoot
            $externalStateBefore = Get-MihoInstalledGuiExternalStateV1 `
                -ExpectedOwnerInstanceId $installedOwner
        }
        else {
            Copy-MihoSafeTreeV1 -Source $portable -Destination $smokeRoot
            $smokeExecutable = Resolve-SafeFileV1 -LiteralPath (Join-Path $smokeRoot "miho-desktop.exe")
        }
        $probeFailure = $null
        $stateFailure = $null
        $rawReceipt = @()
        try {
            $rawReceipt = @(& $probeScript `
                -Executable $smokeExecutable `
                -Mode $verificationMode `
                -TimeoutSeconds 30)
        }
        catch {
            $probeFailure = $_
        }
        if ($verificationMode -ceq "Installed") {
            try {
                $externalStateAfter = Get-MihoInstalledGuiExternalStateV1 `
                    -ExpectedOwnerInstanceId $installedOwner
                Assert-MihoInstalledGuiExternalStateUnchangedV1 `
                    -Before $externalStateBefore `
                    -After $externalStateAfter
            }
            catch {
                $stateFailure = $_
            }
        }
        if ($null -ne $stateFailure) {
            $probeMessage = if ($null -eq $probeFailure) { "none" } else { $probeFailure.Exception.Message }
            throw "GUI render failure=$probeMessage; external state failure=$($stateFailure.Exception.Message)"
        }
        if ($null -ne $probeFailure) { throw $probeFailure }
        $receiptText = [string]::Join("`n", @($rawReceipt | ForEach-Object { [string]$_ }))
        $receipt = $receiptText | ConvertFrom-Json -ErrorAction Stop
        $isInstalledVerification = $verificationMode -ceq "Installed"
        $receipt | Add-Member `
            -NotePropertyName "installed_owner_task_workspace_unchanged" `
            -NotePropertyValue $isInstalledVerification `
            -Force
        $receipt | Add-Member `
            -NotePropertyName "installed_default_webview_before_sha256" `
            -NotePropertyValue $(if ($isInstalledVerification) { [string]$externalStateBefore.default_webview.digest } else { "" }) `
            -Force
        $receipt | Add-Member `
            -NotePropertyName "installed_default_webview_after_sha256" `
            -NotePropertyValue $(if ($isInstalledVerification) { [string]$externalStateAfter.default_webview.digest } else { "" }) `
            -Force
        $receipt | Add-Member `
            -NotePropertyName "installed_default_webview_byte_delta" `
            -NotePropertyValue $(if ($isInstalledVerification) {
                [int64]$externalStateAfter.default_webview.total_bytes - [int64]$externalStateBefore.default_webview.total_bytes
            } else { [int64]0 }) `
            -Force
        $continuousAudit = $receipt.PSObject.Properties["continuous_process_event_audit"]
        $pythonObserved = $receipt.PSObject.Properties["python_identity_observed"]
        $webViewIsolated = $receipt.PSObject.Properties["webview_data_isolated"]
        $webViewScope = $receipt.PSObject.Properties["webview_data_scope"]
        $webViewUserDataBound = $receipt.PSObject.Properties["webview_user_data_directory_bound"]
        $expectedWebViewIsolation = $verificationMode -ceq "Portable"
        $expectedWebViewScope = if ($expectedWebViewIsolation) {
            "portable-layout"
        }
        else {
            "default-installed-cache"
        }
        if ([string]$receipt.schema_version -cne "miho-gui-render-verification-v1" -or
            [string]$receipt.mode -cne $verificationMode.ToLowerInvariant() -or
            [string]$receipt.executable_sha256 -cne (Get-Sha256Hex -LiteralPath $smokeExecutable) -or
            [string]$receipt.executable_sha256 -cne (Get-Sha256Hex -LiteralPath (Join-Path $portable "miho-desktop.exe")) -or
            [string]$receipt.url -cne "https://tauri.localhost/#miho-app-ready-v1" -or
            [string]$receipt.render_sentinel -cne "data-miho-app-ready=v1" -or
            [string]$receipt.dom_ready_state -cne "complete" -or
            [string]$receipt.dom_brand -cne "MIHO ENDGAME" -or
            [int]$receipt.dom_app_child_count -lt 2 -or
            -not [bool]$receipt.tauri_internals -or
            -not [bool]$receipt.error_page_rejected -or
            [int]$receipt.minimum_alive_seconds -lt 5 -or
            -not [bool]$receipt.normal_exit -or
            [int]$receipt.exit_code -ne 0 -or
            -not [bool]$receipt.captured_descendants_cleaned -or
            -not [bool]$receipt.debug_port_closed -or
            -not [bool]$receipt.stdout_empty -or
            -not [bool]$receipt.stderr_empty -or
            [string]$receipt.process_observation -cne "bound-snapshot-sampling-200ms" -or
            $null -eq $continuousAudit -or $continuousAudit.Value -isnot [bool] -or
            [bool]$continuousAudit.Value -or
            $null -eq $pythonObserved -or $pythonObserved.Value -isnot [bool] -or
            [bool]$pythonObserved.Value -or
            $null -eq $webViewIsolated -or $webViewIsolated.Value -isnot [bool] -or
            [bool]$webViewIsolated.Value -ne $expectedWebViewIsolation -or
            $null -eq $webViewScope -or $webViewScope.Value -isnot [string] -or
            [string]$webViewScope.Value -cne $expectedWebViewScope -or
            $null -eq $webViewUserDataBound -or $webViewUserDataBound.Value -isnot [bool] -or
            -not [bool]$webViewUserDataBound.Value -or
            $receipt.PSObject.Properties["installed_owner_task_workspace_unchanged"].Value -isnot [bool] -or
            [bool]$receipt.installed_owner_task_workspace_unchanged -ne $isInstalledVerification -or
            $receipt.PSObject.Properties["installed_default_webview_before_sha256"].Value -isnot [string] -or
            $receipt.PSObject.Properties["installed_default_webview_after_sha256"].Value -isnot [string] -or
            $receipt.PSObject.Properties["installed_default_webview_byte_delta"].Value -isnot [int64]) {
            throw "Packaged GUI render verification receipt is invalid"
        }
        return $receipt
    }
    finally {
        if (Test-Path -LiteralPath $smokeRoot) {
            Remove-MihoReleaseScratchTreeV1 -LiteralPath $smokeRoot -Parent $smokeParent
        }
    }
}

if ($env:MIHO_RELEASE_CONTRACT_TEST_DEFINE_ONLY_V1 -ceq "1") {
    return
}

if ($NoBundle -and -not $Release) {
    throw "-NoBundle is valid only with -Release"
}
$releaseLease = $null
$locationPushed = $false
$buildRoot = $root
$buildDesktop = $desktop
$toolchainRoot = $root
$calibrationPayloadRoot = $null
$releaseScratchCleaned = $false
$publishedManifest = $null
$leaseReleaseWarning = $null
try {
    if ($Release) {
        # Creating/opening the filesystem lease is deliberately the first
        # release-specific workspace mutation and it remains held to exit.
        $releaseLease = Enter-MihoReleaseBuildLeaseV1 -Root $root
        # A killed prior build must not leave another multi-gigabyte dependency
        # and Cargo tree. The lease proves no live build owns these scratch
        # roots; content-addressed bundle artifacts are deliberately excluded.
        Clear-MihoReleaseScratchV1 -Root $root
    }
    $workspaceInputs = $null
    $buildWorkspaceInputs = $null
    $productVersion = $null
    if ($Release) {
        $initialActiveAnchor = Get-MihoActiveReleaseAnchorStateV1 -Root $root
        # Freeze the original Git/source state before creating the unique
        # release workspace. The existing root node_modules tree is never a
        # release input and is deliberately left untouched.
        $gitProvenance = Get-MihoGitProvenanceV1 -Root $root
        $workspaceInputs = Get-MihoWorkspaceReleaseInputsDigestV1 -Root $root
        $publication = Get-MihoReleasePublicationDecisionV1 `
            -SourceTreeState ([string]$gitProvenance.source_tree_state) `
            -NoBundleMode ([bool]$NoBundle) `
            -ProjectGatesApproved $projectGatesApprovedMode
        $null = Get-MihoPackageManagerPolicyV1 -Root $root -NodePath $node
        Assert-MihoTauriCustomProtocolFeatureV1 -Root $root
        Clear-MihoStaleReleaseContextsV1 -Root $root
        $isolatedWorkspace = New-MihoIsolatedReleaseWorkspaceV1 `
            -Root $root `
            -ExpectedInputs $workspaceInputs
        $buildRoot = [string]$isolatedWorkspace.Root
        $buildDesktop = [string]$isolatedWorkspace.Desktop
        $buildWorkspaceInputs = $isolatedWorkspace.Inputs
        $toolchainRoot = $buildRoot
        $null = Get-MihoPackageManagerPolicyV1 -Root $buildRoot -NodePath $node
        Assert-MihoTauriCustomProtocolFeatureV1 -Root $buildRoot
        Invoke-MihoFrozenPnpmInstallV1 -Root $buildRoot
        $toolchainEvidence = Get-MihoReleaseToolchainEvidenceV1 -Root $toolchainRoot -NodePath $node
        $baseConfigPath = Resolve-SafeFileV1 -LiteralPath (Join-Path $buildRoot "crates\miho-desktop\src-tauri\tauri.conf.json")
        $productVersion = [string]((Get-Content -LiteralPath $baseConfigPath -Raw | ConvertFrom-Json -ErrorAction Stop).version)
        if ($productVersion -notmatch '^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$') {
            throw "Tauri product version is not a supported release version"
        }
        $null = Assert-MihoFrozenReleaseStateV1 `
            -Root $root `
            -BuildWorkspaceRoot $buildRoot `
            -ToolchainRoot $toolchainRoot `
            -NodePath $node `
            -ExpectedGitProvenance $gitProvenance `
            -ExpectedWorkspaceInputs $workspaceInputs `
            -ExpectedBuildWorkspaceInputs $buildWorkspaceInputs `
            -ExpectedToolchainEvidence $toolchainEvidence
    }
    Push-Location $buildDesktop
    $locationPushed = $true
    if (-not $Release -and -not (Test-Path "node_modules")) { throw "Run pnpm install once before building." }
    Invoke-NativeCommand -FilePath $node -ArgumentList @("node_modules\typescript\bin\tsc") -FailureMessage "TypeScript compilation failed"
    Invoke-NativeCommand -FilePath $node -ArgumentList @("node_modules\vite\bin\vite.js", "build") -FailureMessage "Vite build failed"
    if ($Release) {
        # Vite's bundled config loader creates node_modules/.vite-temp and
        # removes its generated file while leaving the empty directory. Do
        # not ignore that path in the frozen graph: accept only the exact
        # successful empty-scratch lifecycle, then restore the installed
        # dependency tree before re-reading its hash.
        Remove-MihoEmptyViteConfigScratchV1 -Root $buildRoot
        $null = Assert-MihoFrozenReleaseStateV1 `
            -Root $root `
            -BuildWorkspaceRoot $buildRoot `
            -ToolchainRoot $toolchainRoot `
            -NodePath $node `
            -ExpectedGitProvenance $gitProvenance `
            -ExpectedWorkspaceInputs $workspaceInputs `
            -ExpectedBuildWorkspaceInputs $buildWorkspaceInputs `
            -ExpectedToolchainEvidence $toolchainEvidence
        $hostTriple = [string]$toolchainEvidence.rustc_host
        if ($hostTriple -notmatch 'windows') {
            throw "The current release packaging contract supports Windows hosts only"
        }
        $tauriTarget = Join-Path $buildRoot "target"
        if (Test-Path -LiteralPath $tauriTarget) {
            throw "Isolated release target unexpectedly exists before native compilation"
        }
        $previousCargoTarget = $env:CARGO_TARGET_DIR
        $env:CARGO_TARGET_DIR = $tauriTarget
        try {
            Invoke-NativeCommand -FilePath "cargo" -ArgumentList @("build", "--locked", "--release", "-p", "miho-cli") -FailureMessage "Native CLI release build failed"
            Invoke-NativeCommand -FilePath "cargo" -ArgumentList @("build", "--locked", "--release", "-p", "miho-desktop", "--features", "custom-protocol") -FailureMessage "Native desktop ownership prebuild failed"
        }
        finally {
            $env:CARGO_TARGET_DIR = $previousCargoTarget
        }
        $tauriTarget = Resolve-SafeDirectoryV1 -LiteralPath $tauriTarget
        $releaseCli = Resolve-SafeFileV1 -LiteralPath (Join-Path $tauriTarget "release\miho.exe")
        $prebuiltDesktop = Resolve-SafeFileV1 -LiteralPath (Join-Path $tauriTarget "release\miho-desktop.exe")
        $null = Assert-MihoFrozenReleaseStateV1 `
            -Root $root `
            -BuildWorkspaceRoot $buildRoot `
            -ToolchainRoot $toolchainRoot `
            -NodePath $node `
            -ExpectedGitProvenance $gitProvenance `
            -ExpectedWorkspaceInputs $workspaceInputs `
            -ExpectedBuildWorkspaceInputs $buildWorkspaceInputs `
            -ExpectedToolchainEvidence $toolchainEvidence
        $staging = New-MihoImmutableReleaseStagingV1 `
            -Root $root `
            -SourceRoot $buildRoot `
            -DesktopRoot $buildDesktop `
            -ProductVersion $productVersion `
            -HostTriple $hostTriple `
            -ReleaseCli $releaseCli `
            -OwnershipDesktopExecutable $prebuiltDesktop
        $stagingEvidence = [pscustomobject][ordered]@{
            digest = [string]$staging.TreeSha256
            file_count = [int]$staging.FileCount
        }
        Clear-MihoStaleReleaseContextsV1 -Root $buildRoot
        $contextPath = New-MihoReleaseContextV1 `
            -Root $buildRoot `
            -StagingRoot $staging.Root `
            -StagedOverlay $staging.Overlay `
            -WorkspaceInputsSha256 $buildWorkspaceInputs.digest `
            -StagingTreeSha256 $staging.TreeSha256 `
            -ReleaseCli $releaseCli `
            -Sidecar $staging.Sidecar
        $preCliHash = Get-Sha256Hex -LiteralPath $releaseCli
        $preSidecarHash = Get-Sha256Hex -LiteralPath $staging.Sidecar
        $null = Assert-MihoFrozenReleaseStateV1 `
            -Root $root `
            -BuildWorkspaceRoot $buildRoot `
            -ToolchainRoot $toolchainRoot `
            -NodePath $node `
            -ExpectedGitProvenance $gitProvenance `
            -ExpectedWorkspaceInputs $workspaceInputs `
            -ExpectedBuildWorkspaceInputs $buildWorkspaceInputs `
            -ExpectedToolchainEvidence $toolchainEvidence `
            -StagingRoot $staging.Root `
            -ExpectedStagingEvidence $stagingEvidence
        Invoke-MihoTauriReleasePassV1 `
            -NodePath $node `
            -Overlay $staging.Overlay `
            -ContextPath $contextPath `
            -WorkspaceRoot $buildRoot `
            -StagingRoot $staging.Root `
            -CargoTarget $tauriTarget `
            -PassKind "build-no-bundle"
        $mainExecutable = Resolve-SafeFileV1 -LiteralPath (Join-Path $tauriTarget "release\miho-desktop.exe")
        $mainItem = Get-Item -LiteralPath $mainExecutable -Force -ErrorAction Stop
        $builtDesktopSize = [int64]$mainItem.Length
        $builtDesktopSha256 = Get-Sha256Hex -LiteralPath $mainExecutable
        $releaseCli = Resolve-SafeFileV1 -LiteralPath $releaseCli
        $sidecar = Resolve-SafeFileV1 -LiteralPath $staging.Sidecar
        $stagingAfterTauri = Get-MihoTreeDigestV1 -LiteralPath $staging.Root
        if ($stagingAfterTauri.digest -cne $staging.TreeSha256 -or
            $stagingAfterTauri.file_count -ne $staging.FileCount -or
            (Get-Sha256Hex -LiteralPath $releaseCli) -cne $preCliHash -or
            (Get-Sha256Hex -LiteralPath $sidecar) -cne $preSidecarHash) {
            throw "Release inputs changed after the hash-bound context was verified"
        }
        $null = Assert-MihoFrozenReleaseStateV1 `
            -Root $root `
            -BuildWorkspaceRoot $buildRoot `
            -ToolchainRoot $toolchainRoot `
            -NodePath $node `
            -ExpectedGitProvenance $gitProvenance `
            -ExpectedWorkspaceInputs $workspaceInputs `
            -ExpectedBuildWorkspaceInputs $buildWorkspaceInputs `
            -ExpectedToolchainEvidence $toolchainEvidence `
            -StagingRoot $staging.Root `
            -ExpectedStagingEvidence $stagingEvidence

        $provisionalStagingRoot = [string]$staging.Root
        $provisionalStagingNonce = [string]$staging.Nonce
        if ($NoBundle) {
            # Tauri's build script may relink after merging the generated
            # overlay even without bundling. Re-materialize ownership from the
            # actual no-bundle executable; no container is produced here.
            Remove-MihoSafeTreeV1 -LiteralPath $provisionalStagingRoot
            if (Test-Path -LiteralPath $provisionalStagingRoot) {
                throw "Provisional no-bundle staging could not be removed"
            }
            $staging = New-MihoImmutableReleaseStagingV1 `
                -Root $root `
                -SourceRoot $buildRoot `
                -DesktopRoot $buildDesktop `
                -ProductVersion $productVersion `
                -HostTriple $hostTriple `
                -ReleaseCli $releaseCli `
                -OwnershipDesktopExecutable $mainExecutable `
                -StagingNonce $provisionalStagingNonce
            if (-not [string]::Equals(
                    [string]$staging.Root,
                    $provisionalStagingRoot,
                    [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "No-bundle staging did not retain the compiler identity"
            }
            $stagingEvidence = [pscustomobject][ordered]@{
                digest = [string]$staging.TreeSha256
                file_count = [int]$staging.FileCount
            }
            $sidecar = Resolve-SafeFileV1 -LiteralPath $staging.Sidecar
            $preSidecarHash = Get-Sha256Hex -LiteralPath $sidecar
            $finalDesktopSize = $builtDesktopSize
            $finalDesktopSha256 = $builtDesktopSha256
            $null = Assert-MihoFrozenReleaseStateV1 `
                -Root $root `
                -BuildWorkspaceRoot $buildRoot `
                -ToolchainRoot $toolchainRoot `
                -NodePath $node `
                -ExpectedGitProvenance $gitProvenance `
                -ExpectedWorkspaceInputs $workspaceInputs `
                -ExpectedBuildWorkspaceInputs $buildWorkspaceInputs `
                -ExpectedToolchainEvidence $toolchainEvidence `
                -StagingRoot $staging.Root `
                -ExpectedStagingEvidence $stagingEvidence
        }
        else {
            # Bundle separately from build. The first bundle establishes
            # Tauri's deterministic bundle-type PE patch without invoking
            # Cargo again; its installer is calibration-only and is deleted.
            $contextPath = New-MihoReleaseContextV1 `
                -Root $buildRoot `
                -StagingRoot $staging.Root `
                -StagedOverlay $staging.Overlay `
                -WorkspaceInputsSha256 $buildWorkspaceInputs.digest `
                -StagingTreeSha256 $staging.TreeSha256 `
                -ReleaseCli $releaseCli `
                -Sidecar $staging.Sidecar
            Invoke-MihoTauriReleasePassV1 `
                -NodePath $node `
                -Overlay $staging.Overlay `
                -ContextPath $contextPath `
                -WorkspaceRoot $buildRoot `
                -StagingRoot $staging.Root `
                -CargoTarget $tauriTarget `
                -PassKind "bundle"
            $mainExecutable = Resolve-SafeFileV1 -LiteralPath (Join-Path $tauriTarget "release\miho-desktop.exe")
            $mainItem = Get-Item -LiteralPath $mainExecutable -Force -ErrorAction Stop
            $calibratedDesktopSize = [int64]$mainItem.Length
            $calibratedDesktopSha256 = Get-Sha256Hex -LiteralPath $mainExecutable
            $stagingAfterCalibration = Get-MihoTreeDigestV1 -LiteralPath $staging.Root
            if ($stagingAfterCalibration.digest -cne $staging.TreeSha256 -or
                $stagingAfterCalibration.file_count -ne $staging.FileCount -or
                (Get-Sha256Hex -LiteralPath $releaseCli) -cne $preCliHash -or
                (Get-Sha256Hex -LiteralPath $sidecar) -cne $preSidecarHash) {
                throw "Calibration bundle changed hash-bound release inputs"
            }
            $null = Assert-MihoFrozenReleaseStateV1 `
                -Root $root `
                -BuildWorkspaceRoot $buildRoot `
                -ToolchainRoot $toolchainRoot `
                -NodePath $node `
                -ExpectedGitProvenance $gitProvenance `
                -ExpectedWorkspaceInputs $workspaceInputs `
                -ExpectedBuildWorkspaceInputs $buildWorkspaceInputs `
                -ExpectedToolchainEvidence $toolchainEvidence `
                -StagingRoot $staging.Root `
                -ExpectedStagingEvidence $stagingEvidence
            $sourceDesktopAfterCalibration = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $mainExecutable) -Force -ErrorAction Stop
            if ([int64]$sourceDesktopAfterCalibration.Length -ne $builtDesktopSize -or
                (Get-Sha256Hex -LiteralPath $sourceDesktopAfterCalibration.FullName) -cne $builtDesktopSha256) {
                throw "Tauri bundle mutated the source desktop executable instead of a container copy"
            }
            $calibrationInstaller = Resolve-MihoGeneratedNsisInstallerV1 `
                -TauriTarget $tauriTarget `
                -ProductVersion $productVersion
            $calibrationPayloadRoot = Expand-MihoStaticPayloadFromNsisV1 `
                -Root $root `
                -VerificationNonce $staging.Nonce `
                -NsisInstaller $calibrationInstaller
            $calibrationPrefix = $calibrationPayloadRoot.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
            $calibrationFiles = @(Get-MihoSafeFilesV1 -LiteralPath $calibrationPayloadRoot)
            $calibrationByPath = @{}
            foreach ($file in $calibrationFiles) {
                $relative = $file.FullName.Substring($calibrationPrefix.Length).Replace("\", "/")
                if ($calibrationByPath.ContainsKey($relative)) {
                    throw "Calibration NSIS payload contains a duplicate path"
                }
                $calibrationByPath[$relative] = $file
            }
            $calibrationExpected = @(Get-MihoInstalledStaticSourceRecordsV1 `
                -StagingRoot $staging.Root `
                -MainExecutable $mainExecutable `
                -Sidecar $sidecar `
                -IncludeOwnershipManifest)
            if ($calibrationByPath.Count -ne $calibrationExpected.Count) {
                throw "Calibration NSIS payload has an unexpected static file count"
            }
            foreach ($record in $calibrationExpected) {
                $relative = [string]$record.InstallPath
                if (-not $calibrationByPath.ContainsKey($relative)) {
                    throw "Calibration NSIS payload omits static path: $relative"
                }
                if ($relative -cne "miho-desktop.exe") {
                    $expectedSource = Resolve-SafeFileV1 -LiteralPath ([string]$record.Source)
                    $actualSource = $calibrationByPath[$relative]
                    if ([int64]$actualSource.Length -ne [int64](Get-Item -LiteralPath $expectedSource -Force).Length -or
                        (Get-Sha256Hex -LiteralPath $actualSource.FullName) -cne (Get-Sha256Hex -LiteralPath $expectedSource)) {
                        throw "Calibration NSIS payload changed non-main static bytes: $relative"
                    }
                }
            }
            $calibrationPatchedMain = Resolve-SafeFileV1 -LiteralPath (Join-Path $calibrationPayloadRoot "miho-desktop.exe")
            $calibratedDesktopItem = Get-Item -LiteralPath $calibrationPatchedMain -Force -ErrorAction Stop
            $calibratedDesktopSize = [int64]$calibratedDesktopItem.Length
            $calibratedDesktopSha256 = Get-Sha256Hex -LiteralPath $calibrationPatchedMain
            $calibrationBundleRoot = Join-Path $tauriTarget "release\bundle"
            if (Test-Path -LiteralPath $calibrationBundleRoot) {
                $calibrationBundleRoot = Assert-PathBelow `
                    -LiteralPath $calibrationBundleRoot `
                    -Parent (Join-Path $tauriTarget "release")
                Remove-MihoSafeTreeV1 -LiteralPath $calibrationBundleRoot
            }
            if (Test-Path -LiteralPath $calibrationBundleRoot) {
                throw "Calibration NSIS bundle could not be discarded"
            }

            # Keep the Tauri compiler configuration path and verification
            # nonce stable across the calibration/final passes. The complete
            # provisional tree is removed first, then re-materialized at the
            # same identity with only the ownership manifest derived from the
            # calibrated PE bytes. The final tree is frozen from that point.
            Remove-MihoSafeTreeV1 -LiteralPath $provisionalStagingRoot
            if (Test-Path -LiteralPath $provisionalStagingRoot) {
                throw "Provisional release staging could not be removed"
            }

            $staging = New-MihoImmutableReleaseStagingV1 `
                -Root $root `
                -SourceRoot $buildRoot `
                -DesktopRoot $buildDesktop `
                -ProductVersion $productVersion `
                -HostTriple $hostTriple `
                -ReleaseCli $releaseCli `
                -OwnershipDesktopExecutable $calibrationPatchedMain `
                -StagingNonce $provisionalStagingNonce
            if (-not [string]::Equals(
                    [string]$staging.Root,
                    $provisionalStagingRoot,
                    [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Final release staging did not retain the calibrated compiler identity"
            }
            $stagingEvidence = [pscustomobject][ordered]@{
                digest = [string]$staging.TreeSha256
                file_count = [int]$staging.FileCount
            }
            $contextPath = New-MihoReleaseContextV1 `
                -Root $buildRoot `
                -StagingRoot $staging.Root `
                -StagedOverlay $staging.Overlay `
                -WorkspaceInputsSha256 $buildWorkspaceInputs.digest `
                -StagingTreeSha256 $staging.TreeSha256 `
                -ReleaseCli $releaseCli `
                -Sidecar $staging.Sidecar
            $preSidecarHash = Get-Sha256Hex -LiteralPath $staging.Sidecar
            $null = Assert-MihoFrozenReleaseStateV1 `
                -Root $root `
                -BuildWorkspaceRoot $buildRoot `
                -ToolchainRoot $toolchainRoot `
                -NodePath $node `
                -ExpectedGitProvenance $gitProvenance `
                -ExpectedWorkspaceInputs $workspaceInputs `
                -ExpectedBuildWorkspaceInputs $buildWorkspaceInputs `
                -ExpectedToolchainEvidence $toolchainEvidence `
                -StagingRoot $staging.Root `
                -ExpectedStagingEvidence $stagingEvidence
            Invoke-MihoTauriReleasePassV1 `
                -NodePath $node `
                -Overlay $staging.Overlay `
                -ContextPath $contextPath `
                -WorkspaceRoot $buildRoot `
                -StagingRoot $staging.Root `
                -CargoTarget $tauriTarget `
                -PassKind "bundle"
            $sourceDesktopAfterFinalBundle = Get-Item `
                -LiteralPath (Resolve-SafeFileV1 -LiteralPath (Join-Path $tauriTarget "release\miho-desktop.exe")) `
                -Force `
                -ErrorAction Stop
            if ([int64]$sourceDesktopAfterFinalBundle.Length -ne $builtDesktopSize -or
                (Get-Sha256Hex -LiteralPath $sourceDesktopAfterFinalBundle.FullName) -cne $builtDesktopSha256) {
                throw "Final Tauri bundle mutated the source desktop executable"
            }
            $mainExecutable = $calibrationPatchedMain
            $finalDesktopSize = $calibratedDesktopSize
            $finalDesktopSha256 = $calibratedDesktopSha256
            $sidecar = Resolve-SafeFileV1 -LiteralPath $staging.Sidecar
            $stagingAfterTauri = Get-MihoTreeDigestV1 -LiteralPath $staging.Root
            if ($stagingAfterTauri.digest -cne $staging.TreeSha256 -or
                $stagingAfterTauri.file_count -ne $staging.FileCount -or
                (Get-Sha256Hex -LiteralPath $releaseCli) -cne $preCliHash -or
                (Get-Sha256Hex -LiteralPath $sidecar) -cne $preSidecarHash) {
                throw "Final release inputs changed after the hash-bound context was verified"
            }
            $null = Assert-MihoFrozenReleaseStateV1 `
                -Root $root `
                -BuildWorkspaceRoot $buildRoot `
                -ToolchainRoot $toolchainRoot `
                -NodePath $node `
                -ExpectedGitProvenance $gitProvenance `
                -ExpectedWorkspaceInputs $workspaceInputs `
                -ExpectedBuildWorkspaceInputs $buildWorkspaceInputs `
                -ExpectedToolchainEvidence $toolchainEvidence `
                -StagingRoot $staging.Root `
                -ExpectedStagingEvidence $stagingEvidence
        }
        $bundleRoot = Ensure-SafeDirectoryV1 -LiteralPath (Join-Path $root "target\release\bundle")
        $nsisInstaller = $null
        if (-not $NoBundle) {
            $nsisInstaller = Publish-MihoImmutableNsisArtifactV1 `
                -Root $root `
                -TauriTarget $tauriTarget `
                -ProductVersion $productVersion
        }
        $installedManifestPending = New-MihoStaticInstalledPayloadManifestV1 `
            -ProductVersion $productVersion `
            -HostTriple $hostTriple `
            -StagingRoot $staging.Root `
            -Sidecar $sidecar `
            -MainExecutable $mainExecutable `
            -OutputPath (Join-Path $bundleRoot (".miho-static-installed-payload-v1.{0}.pending.json" -f [guid]::NewGuid().ToString("N"))) `
            -NoBundleMode ([bool]$NoBundle)
        $installedManifest = $null
        try {
            if (-not $NoBundle) {
                $installedManifestPending = Confirm-MihoStaticInstalledPayloadFromNsisV1 `
                    -Root $root `
                    -VerificationNonce $staging.Nonce `
                    -NsisInstaller $nsisInstaller `
                    -InstalledPayloadManifest $installedManifestPending
            }
            $installedManifest = Publish-MihoImmutableStaticManifestV1 `
                -Root $root `
                -PendingManifest $installedManifestPending
        }
        finally {
            if ($null -eq $installedManifest -and (Test-Path -LiteralPath $installedManifestPending)) {
                Remove-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $installedManifestPending) -Force -ErrorAction Stop
            }
        }
        $portableResult = New-MihoPortableBundle `
            -Root $root `
            -ProductVersion $productVersion `
            -HostTriple $hostTriple `
            -StagingRoot $staging.Root `
            -MainExecutable $mainExecutable `
            -ReleaseCli $sidecar
        $guiRenderVerification = Invoke-MihoPackagedGuiRenderVerificationV1 `
            -Root $root `
            -BuildWorkspaceRoot $buildRoot `
            -ReleaseStagingRoot $staging.Root `
            -PortableDirectory $portableResult.Directory `
            -InstalledPayloadManifest $installedManifest `
            -ProductVersion $productVersion `
            -HostTriple $hostTriple `
            -RequireInstalledMode $projectGatesApprovedMode
        Write-Output ("gui-render-verification: " + ($guiRenderVerification | ConvertTo-Json -Depth 4 -Compress))
        $stagingBeforeArtifacts = Get-MihoTreeDigestV1 -LiteralPath $staging.Root
        $desktopBeforeArtifacts = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $mainExecutable) -Force
        if ($stagingBeforeArtifacts.digest -cne $staging.TreeSha256 -or
            $stagingBeforeArtifacts.file_count -ne $staging.FileCount -or
            [int64]$desktopBeforeArtifacts.Length -ne $finalDesktopSize -or
            (Get-Sha256Hex -LiteralPath $desktopBeforeArtifacts.FullName) -cne $finalDesktopSha256 -or
            (Get-Sha256Hex -LiteralPath $releaseCli) -cne $preCliHash -or
            (Get-Sha256Hex -LiteralPath $sidecar) -cne $preSidecarHash) {
            throw "Release inputs changed while generating external payloads"
        }
        $null = Assert-MihoFrozenReleaseStateV1 `
            -Root $root `
            -BuildWorkspaceRoot $buildRoot `
            -ToolchainRoot $toolchainRoot `
            -NodePath $node `
            -ExpectedGitProvenance $gitProvenance `
            -ExpectedWorkspaceInputs $workspaceInputs `
            -ExpectedBuildWorkspaceInputs $buildWorkspaceInputs `
            -ExpectedToolchainEvidence $toolchainEvidence `
            -StagingRoot $staging.Root `
            -ExpectedStagingEvidence $stagingEvidence

        $pendingManifest = Write-MihoReleaseArtifactsManifestV1 `
            -Root $root `
            -ProductVersion $productVersion `
            -HostTriple $hostTriple `
            -Portable $portableResult `
            -InstalledPayloadManifest $installedManifest `
            -NoBundleMode ([bool]$NoBundle) `
            -NsisInstaller $nsisInstaller `
            -GitProvenance $gitProvenance `
            -WorkspaceInputs $workspaceInputs `
            -BuildWorkspaceInputs $buildWorkspaceInputs `
            -StagingEvidence $stagingEvidence `
            -ToolchainEvidence $toolchainEvidence `
            -Publication $publication
        try {
            $null = Assert-MihoReleaseArtifactsManifestV1 `
                -Root $root `
                -BuildWorkspaceRoot $buildRoot `
                -ToolchainRoot $toolchainRoot `
                -ProductVersion $productVersion `
                -HostTriple $hostTriple `
                -Portable $portableResult `
                -InstalledPayloadManifest $installedManifest `
                -NoBundleMode ([bool]$NoBundle) `
                -ProjectGatesApproved $projectGatesApprovedMode `
                -NsisInstaller $nsisInstaller `
                -StagingRoot $staging.Root `
                -NodePath $node `
                -Manifest $pendingManifest

            $null = Assert-MihoFrozenReleaseStateV1 `
                -Root $root `
                -BuildWorkspaceRoot $buildRoot `
                -ToolchainRoot $toolchainRoot `
                -NodePath $node `
                -ExpectedGitProvenance $gitProvenance `
                -ExpectedWorkspaceInputs $workspaceInputs `
                -ExpectedBuildWorkspaceInputs $buildWorkspaceInputs `
                -ExpectedToolchainEvidence $toolchainEvidence `
                -StagingRoot $staging.Root `
                -ExpectedStagingEvidence $stagingEvidence
            $desktopFinal = Get-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $mainExecutable) -Force
            if ([int64]$desktopFinal.Length -ne $finalDesktopSize -or
                (Get-Sha256Hex -LiteralPath $desktopFinal.FullName) -cne $finalDesktopSha256 -or
                (Get-Sha256Hex -LiteralPath (Resolve-SafeFileV1 -LiteralPath $releaseCli)) -cne $preCliHash -or
                (Get-Sha256Hex -LiteralPath (Resolve-SafeFileV1 -LiteralPath $sidecar)) -cne $preSidecarHash) {
                throw "Release executable inputs changed during final artifacts verification"
            }

            # This second full assertion is the final output read from build
            # scratch. Leave the isolated cwd and complete every fallible
            # cleanup before publication changes the active anchor.
            $null = Assert-MihoReleaseArtifactsManifestV1 `
                -Root $root `
                -BuildWorkspaceRoot $buildRoot `
                -ToolchainRoot $toolchainRoot `
                -ProductVersion $productVersion `
                -HostTriple $hostTriple `
                -Portable $portableResult `
                -InstalledPayloadManifest $installedManifest `
                -NoBundleMode ([bool]$NoBundle) `
                -ProjectGatesApproved $projectGatesApprovedMode `
                -NsisInstaller $nsisInstaller `
                -StagingRoot $staging.Root `
                -NodePath $node `
                -Manifest $pendingManifest
            if ($locationPushed) {
                Pop-Location
                $locationPushed = $false
            }
            $publicationResult = Publish-MihoReleaseArtifactsAfterCleanupV1 `
                -Root $root `
                -PendingManifest $pendingManifest `
                -PublicationState ([string]$publication.state) `
                -ExpectedActiveAnchor $initialActiveAnchor `
                -CalibrationPayloadRoot $calibrationPayloadRoot
            $publishedManifest = $publicationResult.Manifest
            $releaseScratchCleaned = [bool]$publicationResult.ScratchCleaned
            $calibrationPayloadRoot = $null
        }
        finally {
            if ($null -eq $publishedManifest -and (Test-Path -LiteralPath $pendingManifest)) {
                Remove-Item -LiteralPath (Resolve-SafeFileV1 -LiteralPath $pendingManifest) -Force -ErrorAction Stop
            }
        }
        Write-Output "Immutable release staging digest: $($staging.TreeSha256) ($($staging.FileCount) files; scratch is removed before exit)"
        Write-Output "Static installed payload manifest: $installedManifest"
        Write-Output "Portable directory: $($portableResult.Directory)"
        Write-Output "Portable archive: $($portableResult.Archive)"
        Write-Output "Release artifacts manifest: $($publishedManifest.Path)"
        Write-Output "Release publication state: $($publishedManifest.State)"
    } else {
        Invoke-NativeCommand -FilePath "cargo" -ArgumentList @("test", "--workspace") -FailureMessage "Rust workspace tests failed"
    }
}
finally {
    try {
        if ($locationPushed) { Pop-Location }
        if ($null -ne $calibrationPayloadRoot -and (Test-Path -LiteralPath $calibrationPayloadRoot)) {
            Remove-MihoSafeTreeV1 -LiteralPath $calibrationPayloadRoot
        }
        if ($Release -and $null -ne $releaseLease -and -not $releaseScratchCleaned) {
            Clear-MihoReleaseScratchV1 -Root $root
            $releaseScratchCleaned = $true
        }
    }
    finally {
        if ($null -ne $releaseLease) {
            try { Exit-MihoReleaseBuildLeaseV1 -Lease $releaseLease }
            catch {
                if ($null -eq $publishedManifest) { throw }
                # Publication already passed its final byte/hash read. Process
                # teardown releases any surviving OS handle; do not turn a
                # successful active publication into an ambiguous failed run.
                $leaseReleaseWarning = [string]$_.Exception.Message
            }
        }
    }
}
if (-not [string]::IsNullOrEmpty($leaseReleaseWarning)) {
    Write-Warning "Release artifacts were published, but explicit lease disposal reported: $leaseReleaseWarning"
}
if ($releaseScratchCleaned) { Write-Output "Release scratch cleanup: complete" }

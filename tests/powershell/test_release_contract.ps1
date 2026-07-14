$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$buildScript = Join-Path $root "scripts\build_rust_app.ps1"
$previousDefineOnly = $env:MIHO_RELEASE_CONTRACT_TEST_DEFINE_ONLY_V1
$env:MIHO_RELEASE_CONTRACT_TEST_DEFINE_ONLY_V1 = "1"
try {
    . $buildScript
}
finally {
    $env:MIHO_RELEASE_CONTRACT_TEST_DEFINE_ONLY_V1 = $previousDefineOnly
}

$ordinalStringProbe = @(Sort-MihoStringsOrdinalV1 -Values @("miho.exe", "miho-desktop.exe"))
$ordinalObjectProbe = @(Sort-MihoObjectsByStringPropertyOrdinalV1 -Values @(
    [pscustomobject]@{ path = "miho.exe" },
    [pscustomobject]@{ path = "miho-desktop.exe" }
) -Property "path")
if ([string]::Join("|", $ordinalStringProbe) -cne "miho-desktop.exe|miho.exe" -or
    [string]::Join("|", @($ordinalObjectProbe | ForEach-Object { $_.path })) -cne "miho-desktop.exe|miho.exe") {
    throw "Release ordering is not ordinal and shell-independent"
}

function Assert-ThrowsV1 {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Action,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $threw = $false
    try { & $Action }
    catch { $threw = $true }
    if (-not $threw) { throw "Expected failure: $Label" }
}

function Invoke-TestGitV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& git -C $Root @Arguments 2>&1)
        $exitCode = [int]$LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) {
        throw "Fixture git command failed: $($output -join ' ')"
    }
    return @($output)
}

function New-MihoReleaseAssertionFixtureV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Parent,
        [Parameter(Mandatory = $true)][string]$Name,
        [switch]$SpoofPortableManifest,
        [switch]$SpoofInstalledManifest
    )

    $productVersion = "1.2.3"
    $hostTriple = "x86_64-pc-windows-msvc"
    $fixtureRoot = Join-Path $Parent $Name
    $immutableStaging = Join-Path $fixtureRoot "immutable-staging"
    foreach ($directory in @(
        (Join-Path $fixtureRoot "configs"),
        (Join-Path $fixtureRoot "scripts"),
        (Join-Path $fixtureRoot "crates\fixture"),
        (Join-Path $fixtureRoot "crates\miho-desktop\node_modules\typescript\bin"),
        (Join-Path $fixtureRoot "crates\miho-desktop\node_modules\vite\bin"),
        (Join-Path $fixtureRoot "crates\miho-desktop\node_modules\@tauri-apps\cli"),
        (Join-Path $fixtureRoot "node_modules\.pnpm"),
        (Join-Path $immutableStaging "resources\configs"),
        (Join-Path $immutableStaging "resources\installer"),
        (Join-Path $immutableStaging "resources\portable")
    )) {
        New-Item -ItemType Directory -Path $directory -Force -ErrorAction Stop | Out-Null
    }
    $fixturePackage = [pscustomobject][ordered]@{
        name = "miho-release-contract-fixture"
        private = $true
        packageManager = "pnpm@11.7.0"
        engines = [pscustomobject][ordered]@{
            node = ">=20.19.0 <25"
            pnpm = "11.7.0"
        }
    }
    Write-Utf8NoBom -LiteralPath (Join-Path $fixtureRoot "package.json") -Text (($fixturePackage | ConvertTo-Json -Depth 4) + "`n")
    Write-Utf8NoBom -LiteralPath (Join-Path $fixtureRoot "Cargo.toml") -Text "[workspace]`nmembers = []`n"
    Write-Utf8NoBom -LiteralPath (Join-Path $fixtureRoot "Cargo.lock") -Text "# fixture Cargo.lock`nversion = 4`n"
    Write-Utf8NoBom -LiteralPath (Join-Path $fixtureRoot "pnpm-workspace.yaml") -Text "packages: []`n"
    Copy-Item -LiteralPath (Join-Path $root "pnpm-lock.yaml") -Destination (Join-Path $fixtureRoot "pnpm-lock.yaml") -ErrorAction Stop
    Copy-Item -LiteralPath (Join-Path $root "pnpm-lock.yaml") -Destination (Join-Path $fixtureRoot "node_modules\.pnpm\lock.yaml") -ErrorAction Stop
    Copy-Item -LiteralPath (Join-Path $root "crates\miho-desktop\node_modules\typescript\bin\tsc") -Destination (Join-Path $fixtureRoot "crates\miho-desktop\node_modules\typescript\bin\tsc") -ErrorAction Stop
    Copy-Item -LiteralPath (Join-Path $root "crates\miho-desktop\node_modules\vite\bin\vite.js") -Destination (Join-Path $fixtureRoot "crates\miho-desktop\node_modules\vite\bin\vite.js") -ErrorAction Stop
    Copy-Item -LiteralPath (Join-Path $root "crates\miho-desktop\node_modules\@tauri-apps\cli\tauri.js") -Destination (Join-Path $fixtureRoot "crates\miho-desktop\node_modules\@tauri-apps\cli\tauri.js") -ErrorAction Stop
    Write-Utf8NoBom -LiteralPath (Join-Path $fixtureRoot "configs\fixture.json") -Text '{"fixture":true}'
    Write-Utf8NoBom -LiteralPath (Join-Path $fixtureRoot "scripts\fixture.ps1") -Text "# release fixture`n"
    Write-Utf8NoBom -LiteralPath (Join-Path $fixtureRoot "crates\fixture\source.txt") -Text "release fixture source`n"
    Write-Utf8NoBom -LiteralPath (Join-Path $immutableStaging "resources\configs\settings.json") -Text '{"fixture":true}'
    foreach ($scriptName in @(
        "task_scheduler_v1.ps1",
        "install_daily_update_task.ps1",
        "uninstall_daily_update_task.ps1",
        "installer_transaction_v1.ps1"
    )) {
        Write-Utf8NoBom -LiteralPath (Join-Path $immutableStaging "resources\installer\$scriptName") -Text "# $scriptName fixture"
    }
    Write-Utf8NoBom -LiteralPath (Join-Path $immutableStaging "resources\portable\portable_daily_update_task.ps1") -Text "# portable fixture"
    Write-Utf8NoBom -LiteralPath (Join-Path $fixtureRoot ".gitignore") -Text "target/`nnode_modules/`n"
    $bundleRoot = Join-Path $fixtureRoot "target\release\bundle"
    $portableParent = Join-Path $bundleRoot "portable"
    New-Item -ItemType Directory -Path $portableParent -Force -ErrorAction Stop | Out-Null
    $staging = Join-Path $portableParent ".fixture-staging"
    foreach ($directory in @(
        $staging,
        (Join-Path $staging "defaults\configs"),
        (Join-Path $staging "automation")
    )) {
        New-Item -ItemType Directory -Path $directory -Force -ErrorAction Stop | Out-Null
    }
    Write-Utf8NoBom -LiteralPath (Join-Path $staging "miho-desktop.exe") -Text "desktop-fixture"
    Write-Utf8NoBom -LiteralPath (Join-Path $staging "miho.exe") -Text "cli-fixture"
    Write-Utf8NoBom -LiteralPath (Join-Path $staging "miho-portable-v1.json") -Text '{"schema_version":"miho-portable-v1","workspace":"data"}'
    Write-Utf8NoBom -LiteralPath (Join-Path $staging "README-portable.txt") -Text "portable fixture"
    Write-Utf8NoBom -LiteralPath (Join-Path $staging "defaults\configs\settings.json") -Text '{"fixture":true}'
    foreach ($scriptName in @(
        "task_scheduler_v1.ps1",
        "install_daily_update_task.ps1",
        "uninstall_daily_update_task.ps1",
        "portable_daily_update_task.ps1"
    )) {
        Write-Utf8NoBom -LiteralPath (Join-Path $staging "automation\$scriptName") -Text "# $scriptName fixture"
    }
    $ownershipManifest = New-MihoStaticOwnershipManifestV1 `
        -ProductVersion $productVersion `
        -HostTriple $hostTriple `
        -StagingRoot $immutableStaging `
        -MainExecutable (Join-Path $staging "miho-desktop.exe") `
        -Sidecar (Join-Path $staging "miho.exe") `
        -OutputPath (Join-Path $immutableStaging "resources\miho-static-ownership-v1.json")
    Copy-Item -LiteralPath $ownershipManifest -Destination (Join-Path $staging "miho-static-ownership-v1.json") -ErrorAction Stop

    $payloadManifestPath = Join-Path $staging "miho-release-files-v1.json"
    if ($SpoofPortableManifest) {
        Write-Utf8NoBom -LiteralPath $payloadManifestPath -Text '{}'
    }
    else {
        $prefix = [System.IO.Path]::GetFullPath($staging).TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
        $fileRecords = @(
            Sort-MihoObjectsByStringPropertyOrdinalV1 `
                -Values @(Get-MihoSafeFilesV1 -LiteralPath $staging) `
                -Property "FullName" | ForEach-Object {
                [pscustomobject][ordered]@{
                    path = $_.FullName.Substring($prefix.Length).Replace("\", "/")
                    size = [int64]$_.Length
                    sha256 = Get-Sha256Hex -LiteralPath $_.FullName
                }
            }
        )
        $payloadManifest = [pscustomobject][ordered]@{
            schema_version = "miho-release-files-v1"
            product_version = $productVersion
            target_triple = $hostTriple
            files = $fileRecords
            signature_boundary = [pscustomobject][ordered]@{
                guarantee = "This manifest records payload size and SHA-256 only; it does not claim Authenticode trust."
                executables = @(
                    [pscustomobject][ordered]@{
                        path = "miho-desktop.exe"
                        authenticode_status = Get-AuthenticodeStatusV1 -LiteralPath (Join-Path $staging "miho-desktop.exe")
                    },
                    [pscustomobject][ordered]@{
                        path = "miho.exe"
                        authenticode_status = Get-AuthenticodeStatusV1 -LiteralPath (Join-Path $staging "miho.exe")
                    }
                )
                nsis_container = "The NSIS container and external miho.exe require release-pipeline signing outside this repository unless their status is Valid."
            }
        }
        Write-Utf8NoBom -LiteralPath $payloadManifestPath -Text (($payloadManifest | ConvertTo-Json -Depth 8) + "`n")
    }

    $derivedPayloadId = (Get-Sha256Hex -LiteralPath $payloadManifestPath).Substring(0, 16)
    $bundleName = "miho-endgame-$productVersion-$hostTriple-portable-$derivedPayloadId"
    $portableDirectory = Join-Path $portableParent $bundleName
    Move-Item -LiteralPath $staging -Destination $portableDirectory -ErrorAction Stop
    $payloadManifestPath = Join-Path $portableDirectory "miho-release-files-v1.json"
    $archive = Join-Path $portableParent "$bundleName.zip"
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $portableDirectory,
        $archive,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $false
    )
    $portablePayloadId = if ($SpoofPortableManifest) { "FORGED-NOT-DERIVED" } else { $derivedPayloadId }
    $portable = [pscustomobject][ordered]@{
        Directory = $portableDirectory
        Archive = $archive
        PayloadManifest = $payloadManifestPath
        PayloadId = $portablePayloadId
    }

    $installedManifestPath = Join-Path $bundleRoot "miho-static-installed-payload-v1.json"
    if ($SpoofInstalledManifest) {
        $installedFiles = @()
        $ownership = [pscustomobject][ordered]@{ wrong = $true }
        $signatureBoundary = [pscustomobject][ordered]@{ wrong = $true }
    }
    else {
        $mapping = @(
            [pscustomobject]@{ install_path = "miho-desktop.exe"; source = Join-Path $portableDirectory "miho-desktop.exe" },
            [pscustomobject]@{ install_path = "miho.exe"; source = Join-Path $portableDirectory "miho.exe" },
            [pscustomobject]@{ install_path = "defaults/configs/settings.json"; source = Join-Path $portableDirectory "defaults\configs\settings.json" },
            [pscustomobject]@{ install_path = "miho-static-ownership-v1.json"; source = Join-Path $portableDirectory "miho-static-ownership-v1.json" },
            [pscustomobject]@{ install_path = "installer/installer_transaction_v1.ps1"; source = Join-Path $immutableStaging "resources\installer\installer_transaction_v1.ps1" },
            [pscustomobject]@{ install_path = "installer/task_scheduler_v1.ps1"; source = Join-Path $portableDirectory "automation\task_scheduler_v1.ps1" },
            [pscustomobject]@{ install_path = "installer/install_daily_update_task.ps1"; source = Join-Path $portableDirectory "automation\install_daily_update_task.ps1" },
            [pscustomobject]@{ install_path = "installer/uninstall_daily_update_task.ps1"; source = Join-Path $portableDirectory "automation\uninstall_daily_update_task.ps1" }
        )
        $installedFiles = @(
            Sort-MihoObjectsByStringPropertyOrdinalV1 `
                -Values @($mapping) `
                -Property "install_path" | ForEach-Object {
                $item = Get-Item -LiteralPath $_.source -Force -ErrorAction Stop
                [pscustomobject][ordered]@{
                    install_path = $_.install_path
                    size = [int64]$item.Length
                    sha256 = Get-Sha256Hex -LiteralPath $item.FullName
                }
            }
        )
        $ownership = [pscustomobject][ordered]@{
            mutable_workspace_excluded = $true
            automation_owner_instance_required = $true
            guarantee = "This external manifest covers only static bundled payload bytes. Dynamic uninstall.exe, registry values, shortcuts, workspace, Box, reports, browser state, and automation owned by another instance are outside this file list."
        }
        $signatureBoundary = [pscustomobject][ordered]@{
            guarantee = "Observed status is evidence only. Any status other than Valid is not an Authenticode trust claim."
            executables = @(
                [pscustomobject][ordered]@{
                    install_path = "miho-desktop.exe"
                    authenticode_status = Get-AuthenticodeStatusV1 -LiteralPath (Join-Path $portableDirectory "miho-desktop.exe")
                },
                [pscustomobject][ordered]@{
                    install_path = "miho.exe"
                    authenticode_status = Get-AuthenticodeStatusV1 -LiteralPath (Join-Path $portableDirectory "miho.exe")
                }
            )
        }
    }
    $installedManifest = [pscustomobject][ordered]@{
        schema_version = "miho-static-installed-payload-v1"
        product_version = $productVersion
        target_triple = $hostTriple
        files = $installedFiles
        ownership = $ownership
        container_verification = [pscustomobject][ordered]@{
            status = "not-applicable-no-bundle"
            method = "none"
            nsis_size = [int64]0
            nsis_sha256 = ""
            files_verified = 0
        }
        signature_boundary = $signatureBoundary
    }
    Write-Utf8NoBom -LiteralPath $installedManifestPath -Text (($installedManifest | ConvertTo-Json -Depth 10) + "`n")
    $installedContentHash = Get-Sha256Hex -LiteralPath $installedManifestPath
    $immutableInstalledManifestPath = Join-Path $bundleRoot "miho-static-installed-payload-v1.$installedContentHash.json"
    Move-Item -LiteralPath $installedManifestPath -Destination $immutableInstalledManifestPath -ErrorAction Stop
    $installedManifestPath = $immutableInstalledManifestPath

    $null = Invoke-TestGitV1 -Root $fixtureRoot -Arguments @("init", "-q")
    $null = Invoke-TestGitV1 -Root $fixtureRoot -Arguments @("config", "user.name", "Miho Release Contract")
    $null = Invoke-TestGitV1 -Root $fixtureRoot -Arguments @("config", "user.email", "release-contract@example.invalid")
    $null = Invoke-TestGitV1 -Root $fixtureRoot -Arguments @("config", "commit.gpgsign", "false")
    $null = Invoke-TestGitV1 -Root $fixtureRoot -Arguments @("add", "--all")
    $null = Invoke-TestGitV1 -Root $fixtureRoot -Arguments @("commit", "-q", "--no-gpg-sign", "-m", "fixture")

    $gitProvenance = Get-MihoGitProvenanceV1 -Root $fixtureRoot
    $workspaceInputs = Get-MihoWorkspaceReleaseInputsDigestV1 -Root $fixtureRoot
    $stagingEvidence = Get-MihoTreeDigestV1 -LiteralPath $immutableStaging
    $toolchainEvidence = Get-MihoReleaseToolchainEvidenceV1 -Root $fixtureRoot -NodePath $node
    $publication = Get-MihoReleasePublicationDecisionV1 `
        -SourceTreeState ([string]$gitProvenance.source_tree_state) `
        -NoBundleMode $true
    $rootManifestPath = Write-MihoReleaseArtifactsManifestV1 `
        -Root $fixtureRoot `
        -ProductVersion $productVersion `
        -HostTriple $hostTriple `
        -Portable $portable `
        -InstalledPayloadManifest $installedManifestPath `
        -NoBundleMode $true `
        -GitProvenance $gitProvenance `
        -WorkspaceInputs $workspaceInputs `
        -BuildWorkspaceInputs $workspaceInputs `
        -StagingEvidence $stagingEvidence `
        -ToolchainEvidence $toolchainEvidence `
        -Publication $publication
    return [pscustomobject][ordered]@{
        Root = $fixtureRoot
        ProductVersion = $productVersion
        HostTriple = $hostTriple
        Portable = $portable
        InstalledPayloadManifest = $installedManifestPath
        StagingRoot = $immutableStaging
        BuildWorkspaceRoot = $fixtureRoot
        ToolchainRoot = $fixtureRoot
        GitProvenance = $gitProvenance
        WorkspaceInputs = $workspaceInputs
        StagingEvidence = $stagingEvidence
        ToolchainEvidence = $toolchainEvidence
        Publication = $publication
        Manifest = $rootManifestPath
    }
}

function Assert-MihoReleaseFixtureV1 {
    param(
        [Parameter(Mandatory = $true)]$Fixture,
        [string]$Manifest
    )

    if ([string]::IsNullOrWhiteSpace($Manifest)) { $Manifest = [string]$Fixture.Manifest }
    return Assert-MihoReleaseArtifactsManifestV1 `
        -Root $Fixture.Root `
        -BuildWorkspaceRoot $Fixture.BuildWorkspaceRoot `
        -ToolchainRoot $Fixture.ToolchainRoot `
        -ProductVersion $Fixture.ProductVersion `
        -HostTriple $Fixture.HostTriple `
        -Portable $Fixture.Portable `
        -InstalledPayloadManifest $Fixture.InstalledPayloadManifest `
        -NoBundleMode $true `
        -StagingRoot $Fixture.StagingRoot `
        -NodePath $node `
        -Manifest $Manifest
}

$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("miho-release-contract-{0}-{1}" -f $PID, [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temporary -ErrorAction Stop | Out-Null
try {
    $scratchFixture = Join-Path $temporary "scratch-cleanup"
    $scratchBundle = Join-Path $scratchFixture "target\release\bundle"
    $scratchWorkspace = Join-Path $scratchFixture "target\release\release-workspace\stale-build"
    $scratchStaging = Join-Path $scratchFixture "target\release\release-staging\stale-stage"
    foreach ($directory in @($scratchBundle, $scratchWorkspace, $scratchStaging)) {
        New-Item -ItemType Directory -Path $directory -Force -ErrorAction Stop | Out-Null
    }
    Write-Utf8NoBom -LiteralPath (Join-Path $scratchBundle "keep.txt") -Text "content-addressed artifact"
    Write-Utf8NoBom -LiteralPath (Join-Path $scratchWorkspace "cargo.bin") -Text "regenerable"
    Write-Utf8NoBom -LiteralPath (Join-Path $scratchStaging "payload.bin") -Text "regenerable"
    Clear-MihoReleaseScratchV1 -Root $scratchFixture
    if ((Test-Path -LiteralPath (Join-Path $scratchFixture "target\release\release-workspace")) -or
        (Test-Path -LiteralPath (Join-Path $scratchFixture "target\release\release-staging")) -or
        (Get-Content -Raw -LiteralPath (Join-Path $scratchBundle "keep.txt")) -cne "content-addressed artifact") {
        throw "Release scratch cleanup removed durable artifacts or retained regenerable trees"
    }

    $scratchExternal = Join-Path $temporary "scratch-cleanup-canary"
    $scratchParent = Join-Path $scratchFixture "target\release\release-workspace"
    New-Item -ItemType Directory -Path $scratchExternal -Force -ErrorAction Stop | Out-Null
    Write-Utf8NoBom -LiteralPath (Join-Path $scratchExternal "canary.txt") -Text "preserve"
    New-Item -ItemType Directory -Path $scratchParent -Force -ErrorAction Stop | Out-Null
    $scratchLink = Join-Path $scratchParent "unsafe-link"
    New-Item -ItemType Junction -Path $scratchLink -Target $scratchExternal -ErrorAction Stop | Out-Null
    Clear-MihoReleaseScratchV1 -Root $scratchFixture
    if ((Test-Path -LiteralPath $scratchLink) -or
        (Test-Path -LiteralPath $scratchParent) -or
        (Get-Content -Raw -LiteralPath (Join-Path $scratchExternal "canary.txt")) -cne "preserve") {
        throw "Release scratch reparse cleanup followed its link or retained the link object"
    }

    $prepublicationFixture = Join-Path $temporary "prepublication-cleanup"
    $prepublicationBundle = Join-Path $prepublicationFixture "target\release\bundle"
    $prepublicationScratch = Join-Path $prepublicationFixture "target\release\release-workspace"
    New-Item -ItemType Directory -Path $prepublicationBundle -Force -ErrorAction Stop | Out-Null
    New-Item -ItemType Directory -Path $prepublicationScratch -Force -ErrorAction Stop | Out-Null
    $activeManifest = Join-Path $prepublicationBundle "miho-release-artifacts-v1.json"
    Write-Utf8NoBom -LiteralPath $activeManifest -Text "old-active-anchor"
    $expectedAnchor = Get-MihoActiveReleaseAnchorStateV1 -Root $prepublicationFixture
    $pendingManifest = Join-Path $prepublicationBundle (".miho-release-artifacts-v1.{0}.pending.json" -f [guid]::NewGuid().ToString("N"))
    Write-Utf8NoBom -LiteralPath $pendingManifest -Text "new-active-anchor"
    $cleanupPoison = Join-Path $prepublicationScratch "unexpected-file.txt"
    Write-Utf8NoBom -LiteralPath $cleanupPoison -Text "must block publication"
    Assert-ThrowsV1 -Label "prepublication cleanup failure keeps active anchor" -Action {
        $null = Publish-MihoReleaseArtifactsAfterCleanupV1 `
            -Root $prepublicationFixture `
            -PendingManifest $pendingManifest `
            -PublicationState "active" `
            -ExpectedActiveAnchor $expectedAnchor `
            -CalibrationPayloadRoot ""
    }
    if ((Get-Content -Raw -LiteralPath $activeManifest) -cne "old-active-anchor" -or
        (Test-Path -LiteralPath $pendingManifest)) {
        throw "Failed prepublication cleanup changed the active anchor or retained an ephemeral pending manifest"
    }
    Remove-Item -LiteralPath $cleanupPoison -Force -ErrorAction Stop
    Write-Utf8NoBom -LiteralPath $pendingManifest -Text "new-active-anchor"
    $publicationResult = Publish-MihoReleaseArtifactsAfterCleanupV1 `
        -Root $prepublicationFixture `
        -PendingManifest $pendingManifest `
        -PublicationState "active" `
        -ExpectedActiveAnchor $expectedAnchor `
        -CalibrationPayloadRoot ""
    if ((Get-Content -Raw -LiteralPath $activeManifest) -cne "new-active-anchor" -or
        (Test-Path -LiteralPath $pendingManifest) -or
        (Test-Path -LiteralPath $prepublicationScratch) -or
        -not [bool]$publicationResult.ScratchCleaned) {
        throw "Successful prepublication cleanup did not precede the active anchor replacement"
    }

    $valid = Join-Path $temporary "valid.json"
    Write-Utf8NoBom -LiteralPath $valid -Text '{"schema_version":"test","nested":{"value":1},"files":[{"path":"a"}]}'
    $object = Read-MihoStrictJsonFileV1 -LiteralPath $valid
    Assert-MihoExactObjectPropertiesV1 -Object $object -Names @("schema_version", "nested", "files")
    Assert-MihoExactObjectPropertiesV1 -Object $object.nested -Names @("value")

    $duplicateTop = Join-Path $temporary "duplicate-top.json"
    Write-Utf8NoBom -LiteralPath $duplicateTop -Text '{"schema_version":"a","schema_version":"b"}'
    Assert-ThrowsV1 -Label "duplicate top-level key" -Action {
        $null = Read-MihoStrictJsonFileV1 -LiteralPath $duplicateTop
    }

    $duplicateNested = Join-Path $temporary "duplicate-nested.json"
    Write-Utf8NoBom -LiteralPath $duplicateNested -Text '{"files":[{"path":"a","path":"b"}]}'
    Assert-ThrowsV1 -Label "duplicate nested key" -Action {
        $null = Read-MihoStrictJsonFileV1 -LiteralPath $duplicateNested
    }

    $escapedDuplicate = Join-Path $temporary "duplicate-escaped.json"
    Write-Utf8NoBom -LiteralPath $escapedDuplicate -Text '{"path":"a","\u0070ath":"b"}'
    Assert-ThrowsV1 -Label "escaped duplicate key" -Action {
        $null = Read-MihoStrictJsonFileV1 -LiteralPath $escapedDuplicate
    }

    $wrongCase = Join-Path $temporary "wrong-case.json"
    Write-Utf8NoBom -LiteralPath $wrongCase -Text '{"Schema_version":"test"}'
    $wrongCaseObject = Read-MihoStrictJsonFileV1 -LiteralPath $wrongCase
    Assert-ThrowsV1 -Label "ordinal property case" -Action {
        Assert-MihoExactObjectPropertiesV1 -Object $wrongCaseObject -Names @("schema_version")
    }

    $wrongTypes = Join-Path $temporary "wrong-types.json"
    Write-Utf8NoBom -LiteralPath $wrongTypes -Text '{"archive_size":"123","files_verified":"7","flag":"true","files":{}}'
    $wrongTypeObject = Read-MihoStrictJsonFileV1 -LiteralPath $wrongTypes
    Assert-ThrowsV1 -Label "numeric string is not integer" -Action {
        Assert-MihoJsonValueTypeV1 -Value $wrongTypeObject.archive_size -Kind integer -Label "archive_size"
    }
    Assert-ThrowsV1 -Label "count string is not integer" -Action {
        Assert-MihoJsonValueTypeV1 -Value $wrongTypeObject.files_verified -Kind integer -Label "files_verified"
    }
    Assert-ThrowsV1 -Label "boolean string is not boolean" -Action {
        Assert-MihoJsonValueTypeV1 -Value $wrongTypeObject.flag -Kind boolean -Label "flag"
    }
    Assert-ThrowsV1 -Label "object is not array" -Action {
        Assert-MihoJsonPropertyTypeV1 -Object $wrongTypeObject -Name files -Kind array -Label "files"
    }

    $validTypes = Join-Path $temporary "valid-types.json"
    Write-Utf8NoBom -LiteralPath $validTypes -Text '{"archive_size":123,"flag":true,"files":[]}'
    $validTypeObject = Read-MihoStrictJsonFileV1 -LiteralPath $validTypes
    Assert-MihoJsonValueTypeV1 -Value $validTypeObject.archive_size -Kind integer -Label "archive_size"
    Assert-MihoJsonValueTypeV1 -Value $validTypeObject.flag -Kind boolean -Label "flag"
    Assert-MihoJsonPropertyTypeV1 -Object $validTypeObject -Name files -Kind array -Label "files"
    $dirtyBundledDecision = Get-MihoReleasePublicationDecisionV1 -SourceTreeState "dirty" -NoBundleMode $false
    if ($dirtyBundledDecision.state -cne "verification-only" -or $dirtyBundledDecision.reason -cne "dirty-source-tree") {
        throw "Dirty full-bundle source was incorrectly eligible for active publication"
    }
    $cleanBundledUnapproved = Get-MihoReleasePublicationDecisionV1 -SourceTreeState "clean" -NoBundleMode $false
    if ($cleanBundledUnapproved.state -cne "verification-only" -or
        $cleanBundledUnapproved.reason -cne "project-gates-not-approved") {
        throw "Clean full-bundle source was active without explicit project-gate approval"
    }
    $cleanBundledApproved = Get-MihoReleasePublicationDecisionV1 `
        -SourceTreeState "clean" `
        -NoBundleMode $false `
        -ProjectGatesApproved $true
    if ($cleanBundledApproved.state -cne "active" -or
        $cleanBundledApproved.reason -cne "project-gates-approved-clean-source-and-full-bundle") {
        throw "Explicit project-gate approval did not produce the exact active decision"
    }
    Assert-ThrowsV1 -Label "dirty project-gate approval" -Action {
        $null = Get-MihoReleasePublicationDecisionV1 `
            -SourceTreeState "dirty" `
            -NoBundleMode $false `
            -ProjectGatesApproved $true
    }
    Assert-ThrowsV1 -Label "no-bundle project-gate approval" -Action {
        $null = Get-MihoReleasePublicationDecisionV1 `
            -SourceTreeState "clean" `
            -NoBundleMode $true `
            -ProjectGatesApproved $true
    }

    $tauriPassFixture = Join-Path $temporary "tauri-pass-fixture"
    $tauriPassStaging = Join-Path $tauriPassFixture "staging"
    $tauriPassTarget = Join-Path $tauriPassFixture "target"
    foreach ($directory in @($tauriPassFixture, $tauriPassStaging, $tauriPassTarget)) {
        if (-not (Test-Path -LiteralPath $directory)) {
            New-Item -ItemType Directory -Path $directory -ErrorAction Stop | Out-Null
        }
    }
    $tauriPassOverlay = Join-Path $tauriPassStaging "overlay.json"
    $tauriPassContext = Join-Path $tauriPassFixture "context.json"
    $tauriPassNode = Join-Path $tauriPassFixture "consume-context.cmd"
    Write-Utf8NoBom -LiteralPath $tauriPassOverlay -Text '{}'
    Write-Utf8NoBom -LiteralPath $tauriPassContext -Text '{}'
    Write-Utf8NoBom -LiteralPath $tauriPassNode -Text @'
@echo off
if "%MIHO_RELEASE_CONTEXT_V1%"=="" exit /b 91
del /f /q "%MIHO_RELEASE_CONTEXT_V1%" >nul 2>nul
if exist "%MIHO_RELEASE_CONTEXT_V1%" exit /b 92
exit /b 0
'@
    $previousPassContext = $env:MIHO_RELEASE_CONTEXT_V1
    $previousPassWorkspace = $env:MIHO_RELEASE_WORKSPACE_ROOT_V1
    $previousPassStaging = $env:MIHO_RELEASE_STAGING_ROOT_V1
    $previousPassCargo = $env:CARGO_TARGET_DIR
    $env:MIHO_RELEASE_CONTEXT_V1 = "outer-context-sentinel"
    $env:MIHO_RELEASE_WORKSPACE_ROOT_V1 = "outer-workspace-sentinel"
    $env:MIHO_RELEASE_STAGING_ROOT_V1 = "outer-staging-sentinel"
    $env:CARGO_TARGET_DIR = "outer-cargo-sentinel"
    try {
        Invoke-MihoTauriReleasePassV1 `
            -NodePath $tauriPassNode `
            -Overlay $tauriPassOverlay `
            -ContextPath $tauriPassContext `
            -WorkspaceRoot $tauriPassFixture `
            -StagingRoot $tauriPassStaging `
            -CargoTarget $tauriPassTarget `
            -PassKind "build-no-bundle"
        if (Test-Path -LiteralPath $tauriPassContext) {
            throw "Successful Tauri release pass retained a replayable context"
        }
        if ($env:MIHO_RELEASE_CONTEXT_V1 -cne "outer-context-sentinel" -or
            $env:MIHO_RELEASE_WORKSPACE_ROOT_V1 -cne "outer-workspace-sentinel" -or
            $env:MIHO_RELEASE_STAGING_ROOT_V1 -cne "outer-staging-sentinel" -or
            $env:CARGO_TARGET_DIR -cne "outer-cargo-sentinel") {
            throw "Tauri release pass did not restore its caller environment"
        }

        $failingPassContext = Join-Path $tauriPassFixture "failing-context.json"
        $failingPassNode = Join-Path $tauriPassFixture "fail-with-context.cmd"
        Write-Utf8NoBom -LiteralPath $failingPassContext -Text '{}'
        Write-Utf8NoBom -LiteralPath $failingPassNode -Text "@echo off`nexit /b 9`n"
        Assert-ThrowsV1 -Label "failed Tauri pass is surfaced" -Action {
            Invoke-MihoTauriReleasePassV1 `
                -NodePath $failingPassNode `
                -Overlay $tauriPassOverlay `
                -ContextPath $failingPassContext `
                -WorkspaceRoot $tauriPassFixture `
                -StagingRoot $tauriPassStaging `
                -CargoTarget $tauriPassTarget `
                -PassKind "bundle"
        }
        if (Test-Path -LiteralPath $failingPassContext) {
            throw "Failed Tauri release pass retained a replayable context"
        }
    }
    finally {
        $env:MIHO_RELEASE_CONTEXT_V1 = $previousPassContext
        $env:MIHO_RELEASE_WORKSPACE_ROOT_V1 = $previousPassWorkspace
        $env:MIHO_RELEASE_STAGING_ROOT_V1 = $previousPassStaging
        $env:CARGO_TARGET_DIR = $previousPassCargo
    }

    $leaseFixture = Join-Path $temporary "lease-fixture"
    $leaseTarget = Join-Path $leaseFixture "target"
    New-Item -ItemType Directory -Path $leaseTarget -Force -ErrorAction Stop | Out-Null
    Write-Utf8NoBom -LiteralPath (Join-Path $leaseTarget "sentinel.txt") -Text "must-not-change"
    $leaseChild = Join-Path $temporary "lease-child.ps1"
    Write-Utf8NoBom -LiteralPath $leaseChild -Text @'
$ErrorActionPreference = "Stop"
$env:MIHO_RELEASE_CONTRACT_TEST_DEFINE_ONLY_V1 = "1"
. $env:MIHO_TEST_RELEASE_BUILD_SCRIPT_V1
try {
    $lease = Enter-MihoReleaseBuildLeaseV1 -Root $env:MIHO_TEST_RELEASE_ROOT_V1
    try { exit 0 }
    finally { Exit-MihoReleaseBuildLeaseV1 -Lease $lease }
}
catch {
    if ($_.Exception.Message -ceq "Another Miho release build is active") { exit 73 }
    [Console]::Error.WriteLine($_.Exception.ToString())
    exit 74
}
'@
    $previousBuildScript = $env:MIHO_TEST_RELEASE_BUILD_SCRIPT_V1
    $previousLeaseRoot = $env:MIHO_TEST_RELEASE_ROOT_V1
    $env:MIHO_TEST_RELEASE_BUILD_SCRIPT_V1 = $buildScript
    $env:MIHO_TEST_RELEASE_ROOT_V1 = $leaseFixture
    $hostExecutable = (Get-Process -Id $PID -ErrorAction Stop).Path
    $lease = Enter-MihoReleaseBuildLeaseV1 -Root $leaseFixture
    try {
        $beforeLeaseTree = Get-MihoFileSetDigestV1 `
            -BaseRoot $leaseTarget `
            -Files @(Get-MihoSafeFilesV1 -LiteralPath $leaseTarget | Where-Object { $_.Name -cne ".miho-release-build-v1.lock" })
        $beforeLeaseWrite = (Get-Item -LiteralPath $leaseTarget -Force).LastWriteTimeUtc.Ticks
        foreach ($attempt in 1..2) {
            $start = New-Object System.Diagnostics.ProcessStartInfo
            $start.FileName = $hostExecutable
            $start.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $leaseChild.Replace('"', '\"') + '"'
            $start.UseShellExecute = $false
            $start.CreateNoWindow = $true
            $start.RedirectStandardOutput = $true
            $start.RedirectStandardError = $true
            $process = New-Object System.Diagnostics.Process
            $process.StartInfo = $start
            try {
                if (-not $process.Start()) { throw "Lease contention child did not start" }
                $childOutput = $process.StandardOutput.ReadToEnd()
                $childError = $process.StandardError.ReadToEnd()
                $process.WaitForExit()
                if ($process.ExitCode -ne 73) {
                    throw "Lease contender did not fail closed: exit=$($process.ExitCode) output=$childOutput error=$childError"
                }
            }
            finally { $process.Dispose() }
        }
        $renamedTarget = "$leaseTarget-renamed"
        $targetRenameRejected = $false
        try { [System.IO.Directory]::Move($leaseTarget, $renamedTarget) }
        catch { $targetRenameRejected = $true }
        if (-not $targetRenameRejected) {
            [System.IO.Directory]::Move($renamedTarget, $leaseTarget)
            throw "Release filesystem lease did not pin the target ancestor"
        }
        $renamedWorkspace = "$leaseFixture-renamed"
        $workspaceRenameRejected = $false
        try { [System.IO.Directory]::Move($leaseFixture, $renamedWorkspace) }
        catch { $workspaceRenameRejected = $true }
        if (-not $workspaceRenameRejected) {
            [System.IO.Directory]::Move($renamedWorkspace, $leaseFixture)
            throw "Release filesystem lease did not pin the workspace ancestor"
        }
        if (-not (Test-Path -LiteralPath $leaseTarget) -or
            (Test-Path -LiteralPath $renamedTarget) -or
            (Test-Path -LiteralPath $renamedWorkspace)) {
            throw "Rejected ancestor rename changed the lease fixture"
        }
        $afterLeaseTree = Get-MihoFileSetDigestV1 `
            -BaseRoot $leaseTarget `
            -Files @(Get-MihoSafeFilesV1 -LiteralPath $leaseTarget | Where-Object { $_.Name -cne ".miho-release-build-v1.lock" })
        $afterLeaseWrite = (Get-Item -LiteralPath $leaseTarget -Force).LastWriteTimeUtc.Ticks
        if ($beforeLeaseTree.digest -cne $afterLeaseTree.digest -or
            $beforeLeaseTree.file_count -ne $afterLeaseTree.file_count -or
            $beforeLeaseWrite -ne $afterLeaseWrite) {
            throw "Rejected release contender mutated the workspace target"
        }
    }
    finally {
        Exit-MihoReleaseBuildLeaseV1 -Lease $lease
        $env:MIHO_TEST_RELEASE_BUILD_SCRIPT_V1 = $previousBuildScript
        $env:MIHO_TEST_RELEASE_ROOT_V1 = $previousLeaseRoot
    }
    $reacquiredLease = Enter-MihoReleaseBuildLeaseV1 -Root $leaseFixture
    Exit-MihoReleaseBuildLeaseV1 -Lease $reacquiredLease

    $dependencySource = Join-Path $temporary "dependency-source"
    foreach ($directory in @(
        (Join-Path $dependencySource "configs"),
        (Join-Path $dependencySource "scripts"),
        (Join-Path $dependencySource "crates\miho-desktop"),
        (Join-Path $dependencySource "node_modules\.pnpm\picocolors@1.1.1\node_modules\picocolors")
    )) {
        New-Item -ItemType Directory -Path $directory -Force -ErrorAction Stop | Out-Null
    }
    foreach ($relative in @("package.json", "pnpm-workspace.yaml", "pnpm-lock.yaml")) {
        Copy-Item -LiteralPath (Join-Path $root $relative) -Destination (Join-Path $dependencySource $relative) -ErrorAction Stop
    }
    Copy-Item `
        -LiteralPath (Join-Path $root "crates\miho-desktop\package.json") `
        -Destination (Join-Path $dependencySource "crates\miho-desktop\package.json") `
        -ErrorAction Stop
    Write-Utf8NoBom -LiteralPath (Join-Path $dependencySource "Cargo.toml") -Text "[workspace]`nmembers = []`n"
    Write-Utf8NoBom -LiteralPath (Join-Path $dependencySource "Cargo.lock") -Text "# isolated dependency fixture`nversion = 4`n"
    Write-Utf8NoBom -LiteralPath (Join-Path $dependencySource "configs\fixture.json") -Text '{}'
    Write-Utf8NoBom -LiteralPath (Join-Path $dependencySource "scripts\fixture.ps1") -Text "# fixture`n"
    Write-Utf8NoBom -LiteralPath (Join-Path $dependencySource ".gitignore") -Text "target/`nnode_modules/`n"
    $sourcePoison = Join-Path $dependencySource "node_modules\.pnpm\picocolors@1.1.1\node_modules\picocolors\picocolors.js"
    Write-Utf8NoBom -LiteralPath $sourcePoison -Text "throw new Error('persistent source poison')"
    $sourcePoisonHash = Get-Sha256Hex -LiteralPath $sourcePoison
    $null = Invoke-TestGitV1 -Root $dependencySource -Arguments @("init", "-q")
    $null = Invoke-TestGitV1 -Root $dependencySource -Arguments @("config", "user.name", "Miho Dependency Contract")
    $null = Invoke-TestGitV1 -Root $dependencySource -Arguments @("config", "user.email", "dependency-contract@example.invalid")
    $null = Invoke-TestGitV1 -Root $dependencySource -Arguments @("config", "commit.gpgsign", "false")
    $null = Invoke-TestGitV1 -Root $dependencySource -Arguments @("add", "--all")
    $null = Invoke-TestGitV1 -Root $dependencySource -Arguments @("commit", "-q", "--no-gpg-sign", "-m", "fixture")
    $dependencyGit = Get-MihoGitProvenanceV1 -Root $dependencySource
    $dependencyInputs = Get-MihoWorkspaceReleaseInputsDigestV1 -Root $dependencySource
    $dependencyIsolated = New-MihoIsolatedReleaseWorkspaceV1 `
        -Root $dependencySource `
        -ExpectedInputs $dependencyInputs
    if (Test-Path -LiteralPath (Join-Path $dependencyIsolated.Root "node_modules")) {
        throw "Isolated release workspace copied a pre-existing dependency tree"
    }
    Invoke-MihoFrozenPnpmInstallV1 -Root $dependencyIsolated.Root
    $isolatedPicocolors = Resolve-SafeFileV1 -LiteralPath (Join-Path $dependencyIsolated.Root "node_modules\.pnpm\picocolors@1.1.1\node_modules\picocolors\picocolors.js")
    $knownPicocolorsHash = "213bb870fcaad4def0215fe34fbb0f529836cc4d2462e02f14f1a49d09781625"
    if ((Get-Sha256Hex -LiteralPath $isolatedPicocolors) -cne $knownPicocolorsHash -or
        (Get-Sha256Hex -LiteralPath $sourcePoison) -cne $sourcePoisonHash) {
        throw "Fresh isolated dependency installation retained or mutated the persistent source poison"
    }
    $dependencyToolchain = Get-MihoReleaseToolchainEvidenceV1 -Root $dependencyIsolated.Root -NodePath $node
    $viteScratch = Join-Path $dependencyIsolated.Root "crates\miho-desktop\node_modules\.vite-temp"
    New-Item -ItemType Directory -Path $viteScratch -ErrorAction Stop | Out-Null
    $viteScratchProbe = Join-Path $viteScratch "config-probe.mjs"
    Write-Utf8NoBom -LiteralPath $viteScratchProbe -Text "export default {};"
    Assert-ThrowsV1 -Label "release refuses non-empty Vite config scratch" -Action {
        Remove-MihoEmptyViteConfigScratchV1 -Root $dependencyIsolated.Root
    }
    if (-not (Test-Path -LiteralPath $viteScratchProbe -PathType Leaf)) {
        throw "Rejected Vite config scratch was mutated"
    }
    Remove-Item -LiteralPath $viteScratchProbe -Force -ErrorAction Stop
    Remove-MihoEmptyViteConfigScratchV1 -Root $dependencyIsolated.Root
    if (Test-Path -LiteralPath $viteScratch) {
        throw "Empty Vite config scratch remained in the frozen dependency graph"
    }
    $null = Assert-MihoFrozenReleaseStateV1 `
        -Root $dependencySource `
        -BuildWorkspaceRoot $dependencyIsolated.Root `
        -ToolchainRoot $dependencyIsolated.Root `
        -NodePath $node `
        -ExpectedGitProvenance $dependencyGit `
        -ExpectedWorkspaceInputs $dependencyInputs `
        -ExpectedBuildWorkspaceInputs $dependencyIsolated.Inputs `
        -ExpectedToolchainEvidence $dependencyToolchain
    $excludedDist = Join-Path $dependencyIsolated.Root "crates\miho-desktop\dist"
    New-Item -ItemType Directory -Path $excludedDist -ErrorAction Stop | Out-Null
    Write-Utf8NoBom -LiteralPath (Join-Path $excludedDist "runtime.js") -Text "export const drift = 1;"
    $inputsWithExcludedDist = Get-MihoWorkspaceReleaseInputsDigestV1 -Root $dependencyIsolated.Root
    if ([string]$inputsWithExcludedDist.digest -cne [string]$dependencyIsolated.Inputs.digest -or
        [int]$inputsWithExcludedDist.file_count -ne [int]$dependencyIsolated.Inputs.file_count) {
        throw "Dependency junction counterexample target was unexpectedly source-hash-bound"
    }
    $excludedDependencyLink = Join-Path $dependencyIsolated.Root "node_modules\runtime-probe"
    New-Item -ItemType Junction -Path $excludedDependencyLink -Target $excludedDist -ErrorAction Stop | Out-Null
    Assert-ThrowsV1 -Label "dependency graph rejects a workspace-internal link to source-excluded dist" -Action {
        $null = Get-MihoDependencyTreeDigestV1 -Root $dependencyIsolated.Root
    }
    $excludedDependencyLink = Assert-PathBelow -LiteralPath $excludedDependencyLink -Parent (Join-Path $dependencyIsolated.Root "node_modules")
    [System.IO.Directory]::Delete($excludedDependencyLink)
    if (Test-Path -LiteralPath $excludedDependencyLink) {
        throw "Rejected dependency link could not be removed"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $excludedDist "runtime.js") -PathType Leaf)) {
        throw "Removing the rejected dependency link altered its target"
    }
    $pnpmWorkspaceAlias = Join-Path $dependencyIsolated.Root "node_modules\.pnpm\node_modules\miho-desktop"
    if (-not (Test-Path -LiteralPath $pnpmWorkspaceAlias -PathType Container)) {
        throw "Fresh pnpm fixture did not create its expected self-workspace alias"
    }
    $chainedDependencyLink = Join-Path $dependencyIsolated.Root "node_modules\runtime-chain-probe"
    New-Item `
        -ItemType Junction `
        -Path $chainedDependencyLink `
        -Target (Join-Path $pnpmWorkspaceAlias "dist") `
        -ErrorAction Stop | Out-Null
    Assert-ThrowsV1 -Label "dependency graph rejects an internal target reached through the allowed workspace alias" -Action {
        $null = Get-MihoDependencyTreeDigestV1 -Root $dependencyIsolated.Root
    }
    $chainedDependencyLink = Assert-PathBelow -LiteralPath $chainedDependencyLink -Parent (Join-Path $dependencyIsolated.Root "node_modules")
    [System.IO.Directory]::Delete($chainedDependencyLink)
    if (Test-Path -LiteralPath $chainedDependencyLink) {
        throw "Rejected chained dependency link could not be removed"
    }
    Write-Utf8NoBom -LiteralPath $isolatedPicocolors -Text "throw new Error('isolated transitive drift')"
    Assert-ThrowsV1 -Label "frozen release rejects transitive dependency drift outside named entrypoints" -Action {
        $null = Assert-MihoFrozenReleaseStateV1 `
            -Root $dependencySource `
            -BuildWorkspaceRoot $dependencyIsolated.Root `
            -ToolchainRoot $dependencyIsolated.Root `
            -NodePath $node `
            -ExpectedGitProvenance $dependencyGit `
            -ExpectedWorkspaceInputs $dependencyInputs `
            -ExpectedBuildWorkspaceInputs $dependencyIsolated.Inputs `
            -ExpectedToolchainEvidence $dependencyToolchain
    }

    $validRelease = New-MihoReleaseAssertionFixtureV1 -Parent $temporary -Name "valid-release"
    $validReleaseResult = Assert-MihoReleaseArtifactsManifestV1 `
        -Root $validRelease.Root `
        -BuildWorkspaceRoot $validRelease.BuildWorkspaceRoot `
        -ToolchainRoot $validRelease.ToolchainRoot `
        -ProductVersion $validRelease.ProductVersion `
        -HostTriple $validRelease.HostTriple `
        -Portable $validRelease.Portable `
        -InstalledPayloadManifest $validRelease.InstalledPayloadManifest `
        -NoBundleMode $true `
        -StagingRoot $validRelease.StagingRoot `
        -NodePath $node `
        -Manifest $validRelease.Manifest
    if ($validReleaseResult -ne $true) { throw "Valid product release assertion did not return true" }

    $ownershipPath = Join-Path $validRelease.Portable.Directory "miho-static-ownership-v1.json"
    $ownershipExpected = @(Get-MihoExpectedStaticInstalledFilesV1 `
        -PortableDirectory $validRelease.Portable.Directory `
        -StagingRoot $validRelease.StagingRoot | Where-Object {
            [string]$_.InstallPath -cne "miho-static-ownership-v1.json"
        })
    if ((Assert-MihoStaticOwnershipManifestV1 `
            -Manifest $ownershipPath `
            -ExpectedFiles $ownershipExpected `
            -ProductVersion $validRelease.ProductVersion `
            -HostTriple $validRelease.HostTriple) -ne $true) {
        throw "Valid non-self-referential static ownership manifest was rejected"
    }
    $ownershipSpoofPath = Join-Path $temporary "spoofed-static-ownership.json"
    $ownershipSpoof = Read-MihoStrictJsonFileV1 -LiteralPath $ownershipPath
    $ownershipSpoof.ownership.manifest_self_in_files = $true
    Write-Utf8NoBom -LiteralPath $ownershipSpoofPath -Text (($ownershipSpoof | ConvertTo-Json -Depth 10) + "`n")
    Assert-ThrowsV1 -Label "static ownership rejects self-inclusion semantics spoof" -Action {
        $null = Assert-MihoStaticOwnershipManifestV1 `
            -Manifest $ownershipSpoofPath `
            -ExpectedFiles $ownershipExpected `
            -ProductVersion $validRelease.ProductVersion `
            -HostTriple $validRelease.HostTriple
    }

    if ([System.IO.Path]::GetFileName($validRelease.Manifest) -cnotmatch '^\.miho-release-artifacts-v1\.[0-9a-f]{32}\.pending\.json$') {
        throw "Release writer did not use a randomized pending manifest"
    }

    $typeSpoofPath = Join-Path (Split-Path -Parent $validRelease.Manifest) (".miho-release-artifacts-v1.{0}.pending.json" -f [guid]::NewGuid().ToString("N"))
    $typeSpoof = Read-MihoStrictJsonFileV1 -LiteralPath $validRelease.Manifest
    $typeSpoof.inputs.workspace_file_count = [string]$typeSpoof.inputs.workspace_file_count
    Write-Utf8NoBom -LiteralPath $typeSpoofPath -Text (($typeSpoof | ConvertTo-Json -Depth 12) + "`n")
    Assert-ThrowsV1 -Label "product assertion rejects root-manifest numeric type spoof" -Action {
        $null = Assert-MihoReleaseFixtureV1 -Fixture $validRelease -Manifest $typeSpoofPath
    }

    $publicationSpoofPath = Join-Path (Split-Path -Parent $validRelease.Manifest) (".miho-release-artifacts-v1.{0}.pending.json" -f [guid]::NewGuid().ToString("N"))
    $publicationSpoof = Read-MihoStrictJsonFileV1 -LiteralPath $validRelease.Manifest
    $publicationSpoof.publication.state = "active"
    $publicationSpoof.publication.reason = "project-gates-approved-clean-source-and-full-bundle"
    Write-Utf8NoBom -LiteralPath $publicationSpoofPath -Text (($publicationSpoof | ConvertTo-Json -Depth 12) + "`n")
    Assert-ThrowsV1 -Label "no-bundle manifest cannot claim active publication" -Action {
        $null = Assert-MihoReleaseFixtureV1 -Fixture $validRelease -Manifest $publicationSpoofPath
    }

    $sourceSpoofPath = Join-Path (Split-Path -Parent $validRelease.Manifest) (".miho-release-artifacts-v1.{0}.pending.json" -f [guid]::NewGuid().ToString("N"))
    $sourceSpoof = Read-MihoStrictJsonFileV1 -LiteralPath $validRelease.Manifest
    $sourceSpoof.source.commit = "0000000000000000000000000000000000000000"
    Write-Utf8NoBom -LiteralPath $sourceSpoofPath -Text (($sourceSpoof | ConvertTo-Json -Depth 12) + "`n")
    Assert-ThrowsV1 -Label "product assertion rejects stale source commit" -Action {
        $null = Assert-MihoReleaseFixtureV1 -Fixture $validRelease -Manifest $sourceSpoofPath
    }

    $installedLock = Join-Path $validRelease.Root "node_modules\.pnpm\lock.yaml"
    Write-Utf8NoBom -LiteralPath $installedLock -Text "lock drift"
    Assert-ThrowsV1 -Label "product assertion rejects virtual-store lock mismatch" -Action {
        $null = Assert-MihoReleaseFixtureV1 -Fixture $validRelease
    }
    Copy-Item -LiteralPath (Join-Path $validRelease.Root "pnpm-lock.yaml") -Destination $installedLock -Force -ErrorAction Stop

    $fixturePackagePath = Join-Path $validRelease.Root "package.json"
    $originalPackageText = [System.IO.File]::ReadAllText($fixturePackagePath)
    $wrongPnpmPackage = $originalPackageText | ConvertFrom-Json -ErrorAction Stop
    $wrongPnpmPackage.packageManager = "pnpm@11.6.0"
    $wrongPnpmPackage.engines.pnpm = "11.6.0"
    Write-Utf8NoBom -LiteralPath $fixturePackagePath -Text (($wrongPnpmPackage | ConvertTo-Json -Depth 4) + "`n")
    Assert-ThrowsV1 -Label "product assertion rejects actual pnpm version mismatch" -Action {
        $null = Assert-MihoReleaseFixtureV1 -Fixture $validRelease
    }
    Write-Utf8NoBom -LiteralPath $fixturePackagePath -Text $originalPackageText
    if ((Assert-MihoReleaseFixtureV1 -Fixture $validRelease) -ne $true) {
        throw "Release fixture did not recover after dependency-policy counterexamples"
    }

    $dirtyRelease = New-MihoReleaseAssertionFixtureV1 -Parent $temporary -Name "dirty-release"
    Write-Utf8NoBom -LiteralPath (Join-Path $dirtyRelease.Root "configs\fixture.json") -Text '{"fixture":"dirty"}'
    Write-Utf8NoBom -LiteralPath (Join-Path $dirtyRelease.Root "untracked-source.txt") -Text "untracked"
    $dirtyProvenance = Get-MihoGitProvenanceV1 -Root $dirtyRelease.Root
    if ($dirtyProvenance.source_tree_state -cne "dirty" -or $dirtyProvenance.source_status_entry_count -lt 2) {
        throw "Dirty Git fixture did not capture tracked and untracked changes"
    }
    Assert-ThrowsV1 -Label "product assertion rejects dirty tracked and untracked source drift" -Action {
        $null = Assert-MihoReleaseFixtureV1 -Fixture $dirtyRelease
    }
    $null = Invoke-TestGitV1 -Root $dirtyRelease.Root -Arguments @("add", "--all")
    $null = Invoke-TestGitV1 -Root $dirtyRelease.Root -Arguments @("commit", "-q", "--no-gpg-sign", "-m", "head-drift")
    Assert-ThrowsV1 -Label "product assertion rejects HEAD change after initial evidence" -Action {
        $null = Assert-MihoReleaseFixtureV1 -Fixture $dirtyRelease
    }

    $activePath = Join-Path (Split-Path -Parent $validRelease.Manifest) "miho-release-artifacts-v1.json"
    Write-Utf8NoBom -LiteralPath $activePath -Text "prior-active-anchor"
    $priorActiveHash = Get-Sha256Hex -LiteralPath $activePath
    $priorActive = Get-MihoActiveReleaseAnchorStateV1 -Root $validRelease.Root
    $verificationPublication = Publish-MihoReleaseArtifactsManifestV1 `
        -Root $validRelease.Root `
        -PendingManifest $validRelease.Manifest `
        -PublicationState "verification-only" `
        -ExpectedActiveAnchor $priorActive
    if ($verificationPublication.Path -notmatch 'miho-release-verification-v1\.[0-9a-f]{32}\.json$' -or
        (Get-Sha256Hex -LiteralPath $activePath) -cne $priorActiveHash) {
        throw "Verification-only publication replaced the active release anchor"
    }

    $immutableRoot = Join-Path $temporary "immutable-publish"
    $isolatedTauriTarget = Join-Path $immutableRoot "isolated-target"
    $isolatedNsisRoot = Join-Path $isolatedTauriTarget "release\bundle\nsis"
    New-Item -ItemType Directory -Path $isolatedNsisRoot -Force -ErrorAction Stop | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $immutableRoot "target\release\bundle") -Force -ErrorAction Stop | Out-Null
    $legacyActive = Join-Path $immutableRoot "target\release\bundle\miho-release-artifacts-v1.json"
    $legacyStatic = Join-Path $immutableRoot "target\release\bundle\miho-static-installed-payload-v1.json"
    $legacyNsisRoot = Join-Path $immutableRoot "target\release\bundle\nsis"
    New-Item -ItemType Directory -Path $legacyNsisRoot -Force -ErrorAction Stop | Out-Null
    $legacyNsis = Join-Path $legacyNsisRoot "legacy-1.2.3.exe"
    Write-Utf8NoBom -LiteralPath $legacyActive -Text "legacy-active"
    Write-Utf8NoBom -LiteralPath $legacyStatic -Text "legacy-static"
    Write-Utf8NoBom -LiteralPath $legacyNsis -Text "legacy-nsis"
    $legacyActiveHash = Get-Sha256Hex -LiteralPath $legacyActive
    $legacyStaticHash = Get-Sha256Hex -LiteralPath $legacyStatic
    $legacyNsisHash = Get-Sha256Hex -LiteralPath $legacyNsis
    $generatedNsis = Join-Path $isolatedNsisRoot "Miho-Endgame_1.2.3_x64-setup.exe"
    Write-Utf8NoBom -LiteralPath $generatedNsis -Text "isolated-nsis-bytes"
    $generatedNsisHash = Get-Sha256Hex -LiteralPath $generatedNsis
    $immutableNsis = Publish-MihoImmutableNsisArtifactV1 `
        -Root $immutableRoot `
        -TauriTarget $isolatedTauriTarget `
        -ProductVersion "1.2.3"
    if ((Test-Path -LiteralPath $generatedNsis) -or
        ([System.IO.Path]::GetFileName($immutableNsis) -cne "Miho-Endgame_1.2.3_x64-setup.sha256-$generatedNsisHash.exe") -or
        (Get-Sha256Hex -LiteralPath $immutableNsis) -cne $generatedNsisHash) {
        throw "NSIS artifact was not published into an immutable content-addressed path"
    }
    $staticPending = Join-Path (Join-Path $immutableRoot "target\release\bundle") (".miho-static-installed-payload-v1.{0}.pending.json" -f [guid]::NewGuid().ToString("N"))
    Write-Utf8NoBom -LiteralPath $staticPending -Text '{"fixture":"static-manifest"}'
    $staticHash = Get-Sha256Hex -LiteralPath $staticPending
    $immutableStatic = Publish-MihoImmutableStaticManifestV1 -Root $immutableRoot -PendingManifest $staticPending
    if ((Test-Path -LiteralPath $staticPending) -or
        ([System.IO.Path]::GetFileName($immutableStatic) -cne "miho-static-installed-payload-v1.$staticHash.json") -or
        (Get-Sha256Hex -LiteralPath $immutableStatic) -cne $staticHash) {
        throw "Static installed-payload manifest was not published into an immutable content-addressed path"
    }
    if ((Get-Sha256Hex -LiteralPath $legacyActive) -cne $legacyActiveHash -or
        (Get-Sha256Hex -LiteralPath $legacyStatic) -cne $legacyStaticHash -or
        (Get-Sha256Hex -LiteralPath $legacyNsis) -cne $legacyNsisHash) {
        throw "Immutable artifact publication invalidated a prior active release dependency"
    }

    $atomicRoot = Join-Path $temporary "atomic-publish"
    $atomicBundle = Join-Path $atomicRoot "target\release\bundle"
    New-Item -ItemType Directory -Path $atomicBundle -Force -ErrorAction Stop | Out-Null
    $atomicActive = Join-Path $atomicBundle "miho-release-artifacts-v1.json"
    Write-Utf8NoBom -LiteralPath $atomicActive -Text "old-active"
    $expectedAtomicActive = Get-MihoActiveReleaseAnchorStateV1 -Root $atomicRoot
    $atomicPending = Join-Path $atomicBundle (".miho-release-artifacts-v1.{0}.pending.json" -f [guid]::NewGuid().ToString("N"))
    Write-Utf8NoBom -LiteralPath $atomicPending -Text "new-active"
    $newAtomicHash = Get-Sha256Hex -LiteralPath $atomicPending
    $atomicPublication = Publish-MihoReleaseArtifactsManifestV1 `
        -Root $atomicRoot `
        -PendingManifest $atomicPending `
        -PublicationState "active" `
        -ExpectedActiveAnchor $expectedAtomicActive
    if ($atomicPublication.Path -cne $atomicActive -or (Get-Sha256Hex -LiteralPath $atomicActive) -cne $newAtomicHash) {
        throw "Atomic active publication did not replace the expected prior anchor"
    }
    $supersededAnchors = @(Get-ChildItem -LiteralPath $atomicBundle -File -Force | Where-Object {
        $_.Name -cmatch '^\.miho-release-artifacts-v1\.[0-9a-f]{32}\.superseded\.json$'
    })
    if ($supersededAnchors.Count -ne 1 -or [System.IO.File]::ReadAllText($supersededAnchors[0].FullName) -cne "old-active") {
        throw "Atomic active replacement did not preserve exactly one old-byte superseded anchor"
    }
    $expectedBeforeDrift = Get-MihoActiveReleaseAnchorStateV1 -Root $atomicRoot
    $driftPending = Join-Path $atomicBundle (".miho-release-artifacts-v1.{0}.pending.json" -f [guid]::NewGuid().ToString("N"))
    Write-Utf8NoBom -LiteralPath $driftPending -Text "must-not-publish"
    Write-Utf8NoBom -LiteralPath $atomicActive -Text "foreign-active-drift"
    $foreignActiveHash = Get-Sha256Hex -LiteralPath $atomicActive
    Assert-ThrowsV1 -Label "active publication rejects an anchor changed after initial snapshot" -Action {
        $null = Publish-MihoReleaseArtifactsManifestV1 `
            -Root $atomicRoot `
            -PendingManifest $driftPending `
            -PublicationState "active" `
            -ExpectedActiveAnchor $expectedBeforeDrift
    }
    if ((Get-Sha256Hex -LiteralPath $atomicActive) -cne $foreignActiveHash) {
        throw "Failed active publication overwrote the foreign active anchor"
    }
    Remove-Item -LiteralPath $driftPending -Force -ErrorAction Stop

    $stagingBuilderRoot = Join-Path $temporary "staging-builder-output"
    $stagingBuilderSource = Join-Path $temporary "staging-builder-source"
    $stagingBuilderDesktop = Join-Path $stagingBuilderSource "crates\miho-desktop"
    foreach ($directory in @(
        (Join-Path $stagingBuilderRoot "target\release"),
        (Join-Path $stagingBuilderSource "configs"),
        (Join-Path $stagingBuilderSource "scripts"),
        (Join-Path $stagingBuilderDesktop "dist"),
        (Join-Path $stagingBuilderDesktop "src-tauri\isolation"),
        (Join-Path $stagingBuilderDesktop "src-tauri\nsis")
    )) {
        New-Item -ItemType Directory -Path $directory -Force -ErrorAction Stop | Out-Null
    }
    Write-Utf8NoBom -LiteralPath (Join-Path $stagingBuilderSource "configs\settings.json") -Text '{"source":true}'
    foreach ($scriptName in @(
        "task_scheduler_v1.ps1",
        "install_daily_update_task.ps1",
        "uninstall_daily_update_task.ps1",
        "installer_transaction_v1.ps1",
        "portable_daily_update_task.ps1",
        "verify_tauri_release_context.ps1"
    )) {
        Write-Utf8NoBom -LiteralPath (Join-Path $stagingBuilderSource "scripts\$scriptName") -Text "# $scriptName source fixture"
    }
    Write-Utf8NoBom -LiteralPath (Join-Path $stagingBuilderDesktop "dist\index.html") -Text '<!doctype html>'
    Write-Utf8NoBom -LiteralPath (Join-Path $stagingBuilderDesktop "src-tauri\isolation\index.html") -Text '<!doctype html>'
    Write-Utf8NoBom -LiteralPath (Join-Path $stagingBuilderDesktop "src-tauri\installer.nsi") -Text '!define MIHO_NONCE "__MIHO_RELEASE_VERIFY_NONCE__"'
    Write-Utf8NoBom -LiteralPath (Join-Path $stagingBuilderDesktop "src-tauri\nsis\installer-hooks.nsh") -Text "!macro NSIS_HOOK_PREINSTALL`n!macroend`n"
    $stagingBuilderCli = Join-Path $stagingBuilderRoot "miho.exe"
    $stagingBuilderDesktopExe = Join-Path $stagingBuilderRoot "miho-desktop.exe"
    Write-Utf8NoBom -LiteralPath $stagingBuilderCli -Text "cli staging fixture"
    Write-Utf8NoBom -LiteralPath $stagingBuilderDesktopExe -Text "desktop staging fixture"
    $builtStaging = New-MihoImmutableReleaseStagingV1 `
        -Root $stagingBuilderRoot `
        -SourceRoot $stagingBuilderSource `
        -DesktopRoot $stagingBuilderDesktop `
        -ProductVersion "7.6.5" `
        -HostTriple "x86_64-pc-windows-msvc" `
        -ReleaseCli $stagingBuilderCli `
        -OwnershipDesktopExecutable $stagingBuilderDesktopExe
    $builtOverlay = Read-MihoStrictJsonFileV1 -LiteralPath $builtStaging.Overlay
    if ([string]::IsNullOrWhiteSpace([string]$builtOverlay.build.beforeBuildCommand) -or
        [string]$builtOverlay.build.beforeBuildCommand -cne [string]$builtOverlay.build.beforeBundleCommand) {
        throw "Immutable staging did not gate both Tauri build and bundle passes"
    }
    $builtResourceMappings = @($builtOverlay.bundle.resources.PSObject.Properties)
    $expectedBuiltDestinations = @(
        "defaults/configs",
        "installer/task_scheduler_v1.ps1",
        "installer/install_daily_update_task.ps1",
        "installer/uninstall_daily_update_task.ps1",
        "installer/installer_transaction_v1.ps1",
        "miho-static-ownership-v1.json"
    )
    if ($builtResourceMappings.Count -ne $expectedBuiltDestinations.Count -or
        [string]::Join("`n", @(Sort-MihoStringsOrdinalV1 -Values @($builtResourceMappings.Value))) -cne
            [string]::Join("`n", @(Sort-MihoStringsOrdinalV1 -Values @($expectedBuiltDestinations))) -or
        -not (Test-Path -LiteralPath (Join-Path $builtStaging.Root "resources\portable\portable_daily_update_task.ps1")) -or
        -not (Test-Path -LiteralPath $builtStaging.OwnershipManifest)) {
        throw "Immutable staging did not separate exact installed and portable resources"
    }
    $builtOwnershipSources = @(Get-MihoInstalledStaticSourceRecordsV1 `
        -StagingRoot $builtStaging.Root `
        -MainExecutable $stagingBuilderDesktopExe `
        -Sidecar $builtStaging.Sidecar)
    if ((Assert-MihoStaticOwnershipManifestV1 `
            -Manifest $builtStaging.OwnershipManifest `
            -ExpectedFiles $builtOwnershipSources `
            -ProductVersion "7.6.5" `
            -HostTriple "x86_64-pc-windows-msvc") -ne $true) {
        throw "Immutable staging ownership producer was not self-consistent"
    }
    $provisionalStagingRoot = [string]$builtStaging.Root
    $provisionalStagingNonce = [string]$builtStaging.Nonce
    $provisionalOverlaySha256 = Get-Sha256Hex -LiteralPath $builtStaging.Overlay
    $provisionalOwnershipSha256 = Get-Sha256Hex -LiteralPath $builtStaging.OwnershipManifest
    Write-Utf8NoBom -LiteralPath $stagingBuilderDesktopExe -Text "desktop staging fixture after bundle patch"
    Remove-MihoSafeTreeV1 -LiteralPath $provisionalStagingRoot
    $builtStaging = New-MihoImmutableReleaseStagingV1 `
        -Root $stagingBuilderRoot `
        -SourceRoot $stagingBuilderSource `
        -DesktopRoot $stagingBuilderDesktop `
        -ProductVersion "7.6.5" `
        -HostTriple "x86_64-pc-windows-msvc" `
        -ReleaseCli $stagingBuilderCli `
        -OwnershipDesktopExecutable $stagingBuilderDesktopExe `
        -StagingNonce $provisionalStagingNonce
    if (-not [string]::Equals(
            [string]$builtStaging.Root,
            $provisionalStagingRoot,
            [System.StringComparison]::OrdinalIgnoreCase) -or
        (Get-Sha256Hex -LiteralPath $builtStaging.Overlay) -cne $provisionalOverlaySha256 -or
        (Get-Sha256Hex -LiteralPath $builtStaging.OwnershipManifest) -ceq $provisionalOwnershipSha256) {
        throw "Bundle-patched ownership staging did not preserve the compiler identity"
    }
    $reboundOwnershipSources = @(Get-MihoInstalledStaticSourceRecordsV1 `
        -StagingRoot $builtStaging.Root `
        -MainExecutable $stagingBuilderDesktopExe `
        -Sidecar $builtStaging.Sidecar)
    if ((Assert-MihoStaticOwnershipManifestV1 `
            -Manifest $builtStaging.OwnershipManifest `
            -ExpectedFiles $reboundOwnershipSources `
            -ProductVersion "7.6.5" `
            -HostTriple "x86_64-pc-windows-msvc") -ne $true) {
        throw "Re-materialized staging did not bind the bundle-patched desktop bytes"
    }

    $isolatedPortableRoot = Join-Path $temporary "isolated-portable"
    foreach ($directory in @(
        (Join-Path $isolatedPortableRoot "target\release"),
        (Join-Path $isolatedPortableRoot "staging\resources\configs"),
        (Join-Path $isolatedPortableRoot "staging\resources\installer"),
        (Join-Path $isolatedPortableRoot "staging\resources\portable")
    )) {
        New-Item -ItemType Directory -Path $directory -Force -ErrorAction Stop | Out-Null
    }
    $isolatedDesktop = Join-Path $isolatedPortableRoot "isolated-miho-desktop.exe"
    $isolatedCli = Join-Path $isolatedPortableRoot "isolated-miho.exe"
    Write-Utf8NoBom -LiteralPath $isolatedDesktop -Text "isolated-desktop-bytes"
    Write-Utf8NoBom -LiteralPath $isolatedCli -Text "isolated-cli-bytes"
    Write-Utf8NoBom -LiteralPath (Join-Path $isolatedPortableRoot "target\release\miho-desktop.exe") -Text "stale-root-target-bytes"
    Write-Utf8NoBom -LiteralPath (Join-Path $isolatedPortableRoot "staging\resources\configs\settings.json") -Text '{}'
    foreach ($scriptName in @(
        "task_scheduler_v1.ps1",
        "install_daily_update_task.ps1",
        "uninstall_daily_update_task.ps1",
        "installer_transaction_v1.ps1"
    )) {
        Write-Utf8NoBom -LiteralPath (Join-Path $isolatedPortableRoot "staging\resources\installer\$scriptName") -Text "# fixture"
    }
    Write-Utf8NoBom -LiteralPath (Join-Path $isolatedPortableRoot "staging\resources\portable\portable_daily_update_task.ps1") -Text "# portable fixture"
    $null = New-MihoStaticOwnershipManifestV1 `
        -ProductVersion "9.8.7" `
        -HostTriple "x86_64-pc-windows-msvc" `
        -StagingRoot (Join-Path $isolatedPortableRoot "staging") `
        -MainExecutable $isolatedDesktop `
        -Sidecar $isolatedCli `
        -OutputPath (Join-Path $isolatedPortableRoot "staging\resources\miho-static-ownership-v1.json")
    $isolatedPortable = New-MihoPortableBundle `
        -Root $isolatedPortableRoot `
        -ProductVersion "9.8.7" `
        -HostTriple "x86_64-pc-windows-msvc" `
        -StagingRoot (Join-Path $isolatedPortableRoot "staging") `
        -MainExecutable $isolatedDesktop `
        -ReleaseCli $isolatedCli
    if ((Get-Sha256Hex -LiteralPath (Join-Path $isolatedPortable.Directory "miho-desktop.exe")) -cne (Get-Sha256Hex -LiteralPath $isolatedDesktop)) {
        throw "Portable bundle used a stale root target instead of the isolated executable"
    }
    $isolatedInstalled = New-MihoStaticInstalledPayloadManifestV1 `
        -ProductVersion "9.8.7" `
        -HostTriple "x86_64-pc-windows-msvc" `
        -StagingRoot (Join-Path $isolatedPortableRoot "staging") `
        -Sidecar $isolatedCli `
        -MainExecutable $isolatedDesktop `
        -OutputPath (Join-Path $isolatedPortableRoot "target\release\bundle\.isolated-installed.pending.json") `
        -NoBundleMode $true
    $isolatedInstalledValidation = Assert-MihoStaticInstalledPayloadManifestV1 `
        -Manifest $isolatedInstalled `
        -PortableDirectory $isolatedPortable.Directory `
        -StagingRoot (Join-Path $isolatedPortableRoot "staging") `
        -ProductVersion "9.8.7" `
        -HostTriple "x86_64-pc-windows-msvc"
    $isolatedInstalledObject = $isolatedInstalledValidation.Manifest
    $ownershipRecords = @($isolatedInstalledObject.files | Where-Object {
        [string]$_.install_path -ceq "miho-static-ownership-v1.json"
    })
    if ($ownershipRecords.Count -ne 1 -or
        [string]$ownershipRecords[0].sha256 -cne (Get-Sha256Hex -LiteralPath (Join-Path $isolatedPortable.Directory "miho-static-ownership-v1.json"))) {
        throw "External installed-payload manifest does not cover the non-self-referential ownership manifest"
    }
    Remove-Item -LiteralPath (Join-Path $isolatedPortableRoot "target\release\miho-desktop.exe") -Force -ErrorAction Stop
    $isolatedPortableWithoutLegacyTarget = New-MihoPortableBundle `
        -Root $isolatedPortableRoot `
        -ProductVersion "9.8.7" `
        -HostTriple "x86_64-pc-windows-msvc" `
        -StagingRoot (Join-Path $isolatedPortableRoot "staging") `
        -MainExecutable $isolatedDesktop `
        -ReleaseCli $isolatedCli
    if ($isolatedPortableWithoutLegacyTarget.PayloadId -cne $isolatedPortable.PayloadId) {
        throw "Portable bundle changed when the unused root target was absent"
    }
    $secondPortableRoot = Join-Path $temporary "isolated-portable-second-root"
    New-Item -ItemType Directory -Path (Join-Path $secondPortableRoot "target\release") -Force -ErrorAction Stop | Out-Null
    Copy-MihoSafeTreeV1 `
        -Source (Join-Path $isolatedPortableRoot "staging") `
        -Destination (Join-Path $secondPortableRoot "staging")
    $secondDesktop = Join-Path $secondPortableRoot "isolated-miho-desktop.exe"
    $secondCli = Join-Path $secondPortableRoot "isolated-miho.exe"
    Copy-Item -LiteralPath $isolatedDesktop -Destination $secondDesktop -ErrorAction Stop
    Copy-Item -LiteralPath $isolatedCli -Destination $secondCli -ErrorAction Stop
    $secondPortable = New-MihoPortableBundle `
        -Root $secondPortableRoot `
        -ProductVersion "9.8.7" `
        -HostTriple "x86_64-pc-windows-msvc" `
        -StagingRoot (Join-Path $secondPortableRoot "staging") `
        -MainExecutable $secondDesktop `
        -ReleaseCli $secondCli
    $firstPortableZipHash = Get-Sha256Hex -LiteralPath $isolatedPortable.Archive
    $secondPortableZipHash = Get-Sha256Hex -LiteralPath $secondPortable.Archive
    if ($secondPortable.PayloadId -cne $isolatedPortable.PayloadId -or
        [System.IO.Path]::GetFileName($secondPortable.Archive) -cne [System.IO.Path]::GetFileName($isolatedPortable.Archive) -or
        $secondPortableZipHash -cne $firstPortableZipHash) {
        throw "Identical portable payloads from fresh roots did not produce identical container bytes"
    }
    $expectedPortableZipHash = "6aff220e4deb530682ef402ee3111507292929f90d25bb9312c0ef9fc69bd3f5"
    if ($firstPortableZipHash -cne $expectedPortableZipHash) {
        throw "Portable container bytes differ from the cross-shell deterministic fixture"
    }
    if ($env:MIHO_TEST_SHOW_DETERMINISTIC_ZIP_V1 -ceq "1") {
        Write-Output "portable-deterministic-sha256: $firstPortableZipHash"
        $portableTree = Get-MihoTreeDigestV1 -LiteralPath $isolatedPortable.Directory
        Write-Output "portable-tree-sha256: $($portableTree.digest)"
        Write-Output "portable-ownership-sha256: $(Get-Sha256Hex -LiteralPath (Join-Path $isolatedPortable.Directory 'miho-static-ownership-v1.json'))"
        Write-Output "portable-manifest-sha256: $(Get-Sha256Hex -LiteralPath $isolatedPortable.PayloadManifest)"
        Write-Output "portable-readme-sha256: $(Get-Sha256Hex -LiteralPath (Join-Path $isolatedPortable.Directory 'README-portable.txt'))"
    }

    $spoofedPortable = New-MihoReleaseAssertionFixtureV1 `
        -Parent $temporary `
        -Name "spoofed-portable" `
        -SpoofPortableManifest
    Assert-ThrowsV1 -Label "product assertion rejects semantic portable spoof" -Action {
        $null = Assert-MihoReleaseArtifactsManifestV1 `
            -Root $spoofedPortable.Root `
            -BuildWorkspaceRoot $spoofedPortable.BuildWorkspaceRoot `
            -ToolchainRoot $spoofedPortable.ToolchainRoot `
            -ProductVersion $spoofedPortable.ProductVersion `
            -HostTriple $spoofedPortable.HostTriple `
            -Portable $spoofedPortable.Portable `
            -InstalledPayloadManifest $spoofedPortable.InstalledPayloadManifest `
            -NoBundleMode $true `
            -StagingRoot $spoofedPortable.StagingRoot `
            -NodePath $node `
            -Manifest $spoofedPortable.Manifest
    }
    Remove-Item -LiteralPath $spoofedPortable.Manifest -Force -ErrorAction Stop
    if (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $spoofedPortable.Manifest) "miho-release-artifacts-v1.json")) {
        throw "Rejected semantic portable manifest left an active anchor"
    }

    $spoofedInstalled = New-MihoReleaseAssertionFixtureV1 `
        -Parent $temporary `
        -Name "spoofed-installed" `
        -SpoofInstalledManifest
    Assert-ThrowsV1 -Label "product assertion rejects semantic installed spoof" -Action {
        $null = Assert-MihoReleaseArtifactsManifestV1 `
            -Root $spoofedInstalled.Root `
            -BuildWorkspaceRoot $spoofedInstalled.BuildWorkspaceRoot `
            -ToolchainRoot $spoofedInstalled.ToolchainRoot `
            -ProductVersion $spoofedInstalled.ProductVersion `
            -HostTriple $spoofedInstalled.HostTriple `
            -Portable $spoofedInstalled.Portable `
            -InstalledPayloadManifest $spoofedInstalled.InstalledPayloadManifest `
            -NoBundleMode $true `
            -StagingRoot $spoofedInstalled.StagingRoot `
            -NodePath $node `
            -Manifest $spoofedInstalled.Manifest
    }
    Remove-Item -LiteralPath $spoofedInstalled.Manifest -Force -ErrorAction Stop
    if (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $spoofedInstalled.Manifest) "miho-release-artifacts-v1.json")) {
        throw "Rejected semantic installed manifest left an active anchor"
    }

    Write-Output "release-contract-tests: PASS"
}
finally {
    if (Test-Path -LiteralPath $temporary) {
        Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction Stop
    }
}

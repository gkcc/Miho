$ErrorActionPreference = "Stop"

$Fresh = $false
$OpenOnly = $false
$ShowHelp = $false
foreach ($Arg in $args) {
    switch ($Arg) {
        "--fresh" { $Fresh = $true }
        "-fresh" { $Fresh = $true }
        "/fresh" { $Fresh = $true }
        "--open-only" { $OpenOnly = $true }
        "-open-only" { $OpenOnly = $true }
        "/open-only" { $OpenOnly = $true }
        "--help" { $ShowHelp = $true }
        "-help" { $ShowHelp = $true }
        "/?" { $ShowHelp = $true }
    }
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Dashboard = Join-Path $RepoRoot "data\probes\demo\index.html"
$SummaryJson = Join-Path $RepoRoot "data\probes\demo\demo_summary.json"
$Renderer = Join-Path $RepoRoot "tools\probes\render_demo_dashboard.py"
$FigsDir = Join-Path $RepoRoot "figs"

function Get-ShareImageCount {
    param([string]$Path)

    if (-not (Test-Path -Path $Path -PathType Container)) {
        return 0
    }
    return @(
        Get-ChildItem -Path $Path -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -match '^\.(jpg|jpeg|png|webp)$' }
    ).Count
}

function Test-LegacyDashboard {
    param([string]$Path)

    if (-not (Test-Path -Path $Path -PathType Leaf)) {
        return $false
    }
    $Html = Get-Content -Path $Path -Raw -ErrorAction SilentlyContinue
    if (-not $Html) {
        return $false
    }
    return $Html -match "Brief Warning|brief status|trusted ready|ready targets|pending review|watch only|final_brief\.md|final_brief\.json|简报 Markdown|简报 JSON|pending 只会生成复核模板|watch_only"
}

function Get-DashboardRefreshReason {
    if (-not (Test-Path -Path $Dashboard -PathType Leaf)) {
        return $null
    }
    if (Test-LegacyDashboard -Path $Dashboard) {
        return "legacy dashboard markup"
    }
    if ((Test-Path -Path $Renderer -PathType Leaf) -and ((Get-Item $Dashboard).LastWriteTimeUtc -lt (Get-Item $Renderer).LastWriteTimeUtc)) {
        return "dashboard renderer changed"
    }
    return $null
}

function Update-CachedDashboardIfNeeded {
    $Reason = Get-DashboardRefreshReason
    if (-not $Reason) {
        return
    }
    if (-not (Test-Path -Path $SummaryJson -PathType Leaf)) {
        Write-Warning "Cached dashboard looks stale ($Reason), but demo_summary.json is missing. Opening cached HTML as-is."
        return
    }
    $Python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $Python) {
        Write-Warning "Cached dashboard looks stale ($Reason), but Python was not found. Opening cached HTML as-is."
        return
    }
    Write-Host "Refreshing cached dashboard without OCR: $Reason"
    & $Python.Source $Renderer --summary $SummaryJson --output $Dashboard
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Dashboard refresh failed. Opening cached HTML as-is."
    }
}

if ($ShowHelp) {
    Write-Host "Miho Demo Launcher"
    Write-Host ""
    Write-Host "Default: open cached local dashboard immediately. It never runs OCR automatically."
    Write-Host "Fresh OCR: scripts\run_miho_demo.bat --fresh"
    Write-Host "Open only: scripts\run_miho_demo.bat --open-only"
    Write-Host ""
    Write-Host "If you are just checking the UI, run without arguments."
    Write-Host "Use --fresh only after putting new official share images under figs\."
    exit 0
}

if ($Fresh -and $OpenOnly) {
    Write-Error "--fresh and --open-only cannot be used together."
}

if (-not $Fresh) {
    if (Test-Path -Path $Dashboard -PathType Leaf) {
        Update-CachedDashboardIfNeeded
        Start-Process $Dashboard
        Write-Host "Opened cached local demo dashboard: $Dashboard"
        Write-Host "To re-run OCR for figs, use: scripts\run_miho_demo.bat --fresh"
        exit 0
    }
    Write-Host "Miho Dashboard cache does not exist yet."
    Write-Host "Path: $Dashboard"
    Write-Host ""
    Write-Host "This shortcut does not run OCR automatically."
    Write-Host "This launcher deliberately does not run OCR by default."
    Write-Host "For UI acceptance, build/open MihoProbe after a cached dashboard exists."
    Write-Host "To create the first cache from local official share images, run:"
    Write-Host "  scripts\run_miho_demo.bat --fresh"
    Write-Host "Run scripts\run_miho_demo.bat --fresh only when you want to scan figs."
    exit 1
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    Write-Error "Python was not found in PATH. Install Python or activate the project environment, then rerun this demo."
}

if (-not (Test-Path -Path $FigsDir -PathType Container)) {
    Write-Error "Missing local image directory: $FigsDir. Put official share images under figs\ first. This directory is local-only and must not be committed."
}

$DemoScript = Join-Path $RepoRoot "tools\probes\run_demo_pipeline.py"
Write-Host "Miho Fresh OCR"
Write-Host "Running fresh OCR for official share images under figs."
Write-Host ""
Write-Host "This is the slow path. PaddleOCR may spend several minutes loading models before the first useful result."
Write-Host "If you only want to check the visual Dashboard, stop this window and run scripts\run_miho_demo.bat without --fresh."
Write-Host "Image directory: $FigsDir"
Write-Host "Candidate images: $(Get-ShareImageCount -Path $FigsDir)"
Write-Host "Output dashboard: $Dashboard"
Write-Host ""
Write-Host "Starting OCR pipeline..."
& $Python.Source $DemoScript --images-dir $FigsDir --open
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Dashboard: $Dashboard"

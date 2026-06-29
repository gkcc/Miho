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

if ($ShowHelp) {
    Write-Host "Miho Demo Launcher"
    Write-Host ""
    Write-Host "Default: open cached local demo dashboard immediately."
    Write-Host "Fresh OCR: scripts\run_miho_demo.bat --fresh"
    Write-Host "Open only: scripts\run_miho_demo.bat --open-only"
    exit 0
}

if ((-not $Fresh) -and (Test-Path -Path $Dashboard -PathType Leaf)) {
    Start-Process $Dashboard
    Write-Host "Opened cached local demo dashboard: $Dashboard"
    Write-Host "To re-run OCR for figs, use: scripts\run_miho_demo.bat --fresh"
    exit 0
}

if ($OpenOnly) {
    Write-Error "Dashboard does not exist yet: $Dashboard. Run scripts\run_miho_demo.bat --fresh first."
    exit 1
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    Write-Error "Python was not found in PATH. Install Python or activate the project environment, then rerun this demo."
}

$FigsDir = Join-Path $RepoRoot "figs"
if (-not (Test-Path -Path $FigsDir -PathType Container)) {
    Write-Error "Missing local image directory: $FigsDir. Put official share images under figs\ first. This directory is local-only and must not be committed."
}

$DemoScript = Join-Path $RepoRoot "tools\probes\run_demo_pipeline.py"
Write-Host "Running fresh OCR for official share images under figs. PaddleOCR can be slow."
Write-Host "Image directory: $FigsDir"
& $Python.Source $DemoScript --images-dir $FigsDir --open
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Dashboard: $Dashboard"

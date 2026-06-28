$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    Write-Error "Python was not found in PATH. Install Python or activate the project environment, then rerun this demo."
}

$FigsDir = Join-Path $RepoRoot "figs"
if (-not (Test-Path -Path $FigsDir -PathType Container)) {
    Write-Error "Missing local image directory: $FigsDir. Put official share images under figs\ first. This directory is local-only and must not be committed."
}

$DemoScript = Join-Path $RepoRoot "tools\probes\run_demo_pipeline.py"
& $Python.Source $DemoScript --images-dir $FigsDir --open
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$Dashboard = Join-Path $RepoRoot "data\probes\demo\index.html"
Write-Host "Dashboard: $Dashboard"

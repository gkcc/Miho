$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    Write-Error "Python was not found in PATH. Install Python or activate the project environment first."
}

$SpecFile = Join-Path $RepoRoot "packaging\MihoProbe.spec"
if (-not (Test-Path -Path $SpecFile -PathType Leaf)) {
    Write-Error "Missing PyInstaller spec: $SpecFile"
}

Push-Location $RepoRoot
try {
    & $Python.Source -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "PyInstaller is not installed in this Python environment."
        Write-Host "Install it, then rerun:"
        Write-Host "  python -m pip install pyinstaller"
        exit 1
    }

    & $Python.Source -m PyInstaller $SpecFile --clean --noconfirm
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    $ExePath = Join-Path $RepoRoot "dist\MihoProbe.exe"
    if (-not (Test-Path -Path $ExePath -PathType Leaf)) {
        Write-Error "Build finished but dist\MihoProbe.exe was not found."
    }
    Write-Host "Built dist\MihoProbe.exe."
    Write-Host "Try:"
    Write-Host "  dist\MihoProbe.exe status"
    Write-Host "  dist\MihoProbe.exe meta --current-only"
    Write-Host "  dist\MihoProbe.exe box-value --roster-json data\probes\box\zzz_box_roster.json --meta-snapshot data\probes\meta\zzz_prydwen_meta_all_phases.json"
}
finally {
    Pop-Location
}

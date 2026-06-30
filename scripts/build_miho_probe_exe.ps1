$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    Write-Error "Python was not found in PATH. Install Python or activate the project environment first."
}

Push-Location $RepoRoot
try {
    & $Python.Source -m PyInstaller tools/probes/miho_probe_cli.py --name MihoProbe --onefile --clean --noconfirm
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    Write-Host "Built dist\MihoProbe.exe. Run it without args for the cached dashboard, or run dist\MihoProbe.exe replay for P0.9 accuracy acceptance; Fresh OCR remains a separate shortcut."
}
finally {
    Pop-Location
}

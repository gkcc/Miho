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
    Write-Host "Built dist\MihoProbe.exe. P1.1 treats this as a local command shell only; a real release package is P1.2+."
}
finally {
    Pop-Location
}

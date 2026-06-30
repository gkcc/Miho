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
    Write-Host "Built dist\MihoProbe.exe. Run it without args for the cached dashboard, dist\MihoProbe.exe app-export for the official share-image workflow, dist\MihoProbe.exe app-export-calibrate for the coordinate grid, dist\MihoProbe.exe update for saved share images, dist\MihoProbe.exe plan-update for local endgame/Tier suggestions, dist\MihoProbe.exe rank-check for A/S rank crops, dist\MihoProbe.exe check for accuracy acceptance, or dist\MihoProbe.exe ask-gpt for the fixed review packet."
}
finally {
    Pop-Location
}

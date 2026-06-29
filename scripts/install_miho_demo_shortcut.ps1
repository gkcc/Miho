$ErrorActionPreference = "Stop"

$ShowHelp = $false
$OutputDir = $null
$NoFreshShortcut = $false
$FreshOnly = $false

for ($Index = 0; $Index -lt $args.Count; $Index++) {
    $Arg = $args[$Index]
    switch ($Arg) {
        "--help" { $ShowHelp = $true }
        "-help" { $ShowHelp = $true }
        "/?" { $ShowHelp = $true }
        "--output-dir" {
            $Index++
            if ($Index -ge $args.Count) {
                Write-Error "--output-dir requires a path."
            }
            $OutputDir = $args[$Index]
        }
        "-output-dir" {
            $Index++
            if ($Index -ge $args.Count) {
                Write-Error "-output-dir requires a path."
            }
            $OutputDir = $args[$Index]
        }
        "--no-fresh-shortcut" { $NoFreshShortcut = $true }
        "-no-fresh-shortcut" { $NoFreshShortcut = $true }
        "--fresh-only" { $FreshOnly = $true }
        "-fresh-only" { $FreshOnly = $true }
        default { Write-Error "Unknown argument: $Arg" }
    }
}

if ($ShowHelp) {
    Write-Host "Miho Demo Shortcut Installer"
    Write-Host ""
    Write-Host "Default: create desktop shortcuts for Miho Demo, Miho Demo Fresh OCR, MihoProbe, and MihoProbe CLI when available."
    Write-Host "Usage: scripts\install_miho_demo_shortcut.bat"
    Write-Host "Test output: scripts\install_miho_demo_shortcut.bat --output-dir <dir>"
    Write-Host "Skip fresh OCR shortcut: scripts\install_miho_demo_shortcut.bat --no-fresh-shortcut"
    exit 0
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RunBat = (Resolve-Path (Join-Path $PSScriptRoot "run_miho_demo.bat")).Path
$CliBat = Join-Path $PSScriptRoot "open_miho_probe_cli.bat"
$ProbeExe = Join-Path $RepoRoot "dist\MihoProbe.exe"

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = [Environment]::GetFolderPath("Desktop")
}
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    Write-Error "Desktop path is unavailable. Use --output-dir <dir>."
}

$ShortcutDir = (New-Item -ItemType Directory -Force -Path $OutputDir).FullName
$Shell = New-Object -ComObject WScript.Shell
$IconPath = Join-Path $env:SystemRoot "System32\shell32.dll"

function New-MihoShortcut {
    param(
        [string]$Name,
        [string]$TargetPath,
        [string]$Arguments,
        [string]$Description
    )

    $ShortcutPath = Join-Path $ShortcutDir "$Name.lnk"
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $TargetPath
    $Shortcut.Arguments = $Arguments
    $Shortcut.WorkingDirectory = $RepoRoot
    $Shortcut.Description = $Description
    $Shortcut.IconLocation = "$IconPath,167"
    $Shortcut.Save()
    Write-Host "Created shortcut: $ShortcutPath"
}

if (-not $FreshOnly) {
    New-MihoShortcut `
        -Name "Miho Demo" `
        -TargetPath $RunBat `
        -Arguments "" `
        -Description "Open the cached Miho dashboard immediately, or run fresh OCR if no dashboard exists."
}

if (-not $NoFreshShortcut) {
    New-MihoShortcut `
        -Name "Miho Demo Fresh OCR" `
        -TargetPath $RunBat `
        -Arguments "--fresh" `
        -Description "Run fresh PaddleOCR over local official share images under figs, then open the dashboard."
}

if ((Test-Path -Path $CliBat -PathType Leaf) -and (-not $FreshOnly)) {
    if (Test-Path -Path $ProbeExe -PathType Leaf) {
        New-MihoShortcut `
            -Name "MihoProbe" `
            -TargetPath $ProbeExe `
            -Arguments "dashboard --open" `
            -Description "Open the app-like local Miho dashboard without rerunning OCR."
    }

    New-MihoShortcut `
        -Name "MihoProbe CLI" `
        -TargetPath $CliBat `
        -Arguments "" `
        -Description "Open the local MihoProbe executable command shell help."
}

Write-Host "Done. Main shortcut opens cached dashboard first and does not rerun OCR when cache exists."
Write-Host "If MihoProbe was not created, build dist\MihoProbe.exe first and rerun this installer."

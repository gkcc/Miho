param([switch]$Release)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$desktop = Join-Path $root "crates\miho-desktop"
$node = if ($env:CODEX_NODE) { $env:CODEX_NODE } else { (Get-Command node -ErrorAction Stop).Source }
. (Join-Path $PSScriptRoot "native_command.ps1")
Push-Location $desktop
try {
    if (-not (Test-Path "node_modules")) { throw "Run pnpm install once before building." }
    Invoke-NativeCommand -FilePath $node -ArgumentList @("node_modules\typescript\bin\tsc") -FailureMessage "TypeScript compilation failed"
    Invoke-NativeCommand -FilePath $node -ArgumentList @("node_modules\vite\bin\vite.js", "build") -FailureMessage "Vite build failed"
    if ($Release) {
        Invoke-NativeCommand -FilePath "cargo" -ArgumentList @("build", "--locked", "--release", "-p", "miho-cli") -FailureMessage "Native update CLI release build failed"
        $releaseCli = Join-Path $root "target\release\miho.exe"
        if (-not (Test-Path -LiteralPath $releaseCli -PathType Leaf)) {
            throw "Native update CLI release artifact is missing"
        }
        Invoke-NativeCommand -FilePath $node -ArgumentList @("node_modules\@tauri-apps\cli\tauri.js", "build") -FailureMessage "Tauri release build failed"
    } else {
        Invoke-NativeCommand -FilePath "cargo" -ArgumentList @("test", "--workspace") -FailureMessage "Rust workspace tests failed"
    }
} finally { Pop-Location }

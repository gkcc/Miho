param([switch]$Release)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$desktop = Join-Path $root "crates\miho-desktop"
$node = if ($env:CODEX_NODE) { $env:CODEX_NODE } else { (Get-Command node -ErrorAction Stop).Source }
Push-Location $desktop
try {
    if (-not (Test-Path "node_modules")) { throw "Run pnpm install once before building." }
    & $node "node_modules\typescript\bin\tsc"
    & $node "node_modules\vite\bin\vite.js" build
    if ($Release) {
        & $node "node_modules\@tauri-apps\cli\tauri.js" build
    } else {
        cargo test --workspace
    }
} finally { Pop-Location }

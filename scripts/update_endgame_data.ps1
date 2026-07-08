param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$HsrOut = "out",
    [string]$ZzzOut = "out_zzz",
    [string]$ZzzBox = ".miho\zzz_box_state.json",
    [string]$ZzzPlan = "configs\zzz_banner_plan.json",
    [string]$ZzzPlanStatus = "next",
    [string]$ZzzPullPlanStatus = "current,next",
    [string]$HsrRepoId = "LvlUrArti/MocDataProcessed",
    [string]$ZzzRepoId = "LvlUrArti/ShiyuDataProcessed",
    [int]$Days = 183,
    [switch]$SkipHsr,
    [switch]$SkipZzz,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $Root

$toDate = (Get-Date).ToString("yyyy-MM-dd")
$fromDate = (Get-Date).AddDays(-1 * $Days).ToString("yyyy-MM-dd")

function Invoke-Step {
    param(
        [string]$Name,
        [string[]]$Command
    )
    Write-Host "==> $Name"
    & $Command[0] @($Command[1..($Command.Length - 1)])
}

function Get-HfSourceState {
    param([string]$RepoId)
    $probe = @'
import datetime as dt
import json
import re
import sys
import urllib.parse
import urllib.request

repo_id = sys.argv[1]
headers = {
    "User-Agent": "miho-endgame-updater/0.1 (+https://huggingface.co)",
    "Accept": "application/json,text/plain,*/*",
}

def fetch_json(url):
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))

def version_key(value):
    return tuple(int(part) for part in str(value).split(".") if part.isdigit())

def source_date(value):
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text

quoted_repo = urllib.parse.quote(repo_id, safe="/")
config = fetch_json(f"https://huggingface.co/datasets/{quoted_repo}/resolve/main/config.json")
tree = fetch_json(f"https://huggingface.co/api/datasets/{quoted_repo}/tree/main?recursive=false&expand=false")
available = sorted(
    [
        item.get("path", "")
        for item in tree
        if item.get("type") == "directory" and re.match(r"^\d+(\.\d+)+$", str(item.get("path", "")))
    ],
    key=version_key,
)
collect_rows = [
    {"snapshot_id": snapshot_id, "collect_date": source_date(entry.get("collect_date"))}
    for snapshot_id, entry in config.items()
    if isinstance(entry, dict) and source_date(entry.get("collect_date"))
]
collect_rows.sort(key=lambda row: (row["collect_date"], version_key(row["snapshot_id"])))
latest_collect = collect_rows[-1] if collect_rows else {"snapshot_id": "", "collect_date": ""}
latest_available = available[-1] if available else ""
signature = f"{latest_available}|{latest_collect['snapshot_id']}|{latest_collect['collect_date']}|config:{len(config)}|tree:{len(available)}"
print(json.dumps({
    "repo_id": repo_id,
    "latest_available_snapshot": latest_available,
    "latest_collect_snapshot": latest_collect["snapshot_id"],
    "latest_collect_date": latest_collect["collect_date"],
    "source_signature": signature,
}, ensure_ascii=False))
'@
    $json = $probe | & python - $RepoId
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to probe Hugging Face source state for $RepoId"
    }
    return ($json | ConvertFrom-Json)
}

function Read-SourceState {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return [pscustomobject]@{}
    }
    return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Get-StateEntry {
    param([object]$State, [string]$Game)
    if ($null -eq $State) {
        return $null
    }
    if ($State.PSObject.Properties.Name -contains $Game) {
        return $State.$Game
    }
    return $null
}

function Set-StateEntry {
    param([object]$State, [string]$Game, [object]$SourceState, [string]$Path)
    $output = [ordered]@{}
    if ($null -ne $State) {
        foreach ($property in $State.PSObject.Properties) {
            $output[$property.Name] = $property.Value
        }
    }
    $output[$Game] = [ordered]@{
        repo_id = $SourceState.repo_id
        source_signature = $SourceState.source_signature
        source_latest_available_snapshot = $SourceState.latest_available_snapshot
        source_latest_collect_snapshot = $SourceState.latest_collect_snapshot
        source_latest_collect_date = $SourceState.latest_collect_date
    }
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent | Out-Null
    }
    $output | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Test-ExportFresh {
    param(
        [object]$State,
        [string]$Game,
        [object]$SourceState,
        [string[]]$RequiredPaths
    )
    if ($Force) {
        return $false
    }
    $entry = Get-StateEntry $State $Game
    if ($null -eq $entry -or $entry.source_signature -ne $SourceState.source_signature) {
        return $false
    }
    foreach ($path in $RequiredPaths) {
        if (-not (Test-Path -LiteralPath $path)) {
            return $false
        }
    }
    return $true
}

function Get-LatestPathWriteTime {
    param([string[]]$Paths)
    $latest = [datetime]::MinValue
    foreach ($path in $Paths) {
        $items = @(Get-ChildItem -LiteralPath $path -File -ErrorAction SilentlyContinue)
        if (-not $items -and (Test-Path -LiteralPath $path -PathType Leaf)) {
            $items = @(Get-Item -LiteralPath $path)
        }
        foreach ($item in $items) {
            if ($item.LastWriteTime -gt $latest) {
                $latest = $item.LastWriteTime
            }
        }
    }
    return $latest
}

function Test-OutputsFresh {
    param(
        [string[]]$Inputs,
        [string[]]$Outputs
    )
    foreach ($output in $Outputs) {
        if (-not (Test-Path -LiteralPath $output)) {
            return $false
        }
    }
    if ($Force) {
        return $false
    }
    $latestInput = Get-LatestPathWriteTime $Inputs
    $oldestOutput = [datetime]::MaxValue
    foreach ($output in $Outputs) {
        $item = Get-Item -LiteralPath $output
        if ($item.LastWriteTime -lt $oldestOutput) {
            $oldestOutput = $item.LastWriteTime
        }
    }
    return $oldestOutput -ge $latestInput
}

$statePath = Join-Path $Root ".miho\update_source_state.json"
$sourceState = Read-SourceState $statePath

if (-not $SkipHsr) {
    $hsrSource = Get-HfSourceState $HsrRepoId
    $hsrRequired = @(
        (Join-Path $HsrOut "export_report.md"),
        (Join-Path $HsrOut "phase_index.csv"),
        (Join-Path $HsrOut "team_rank_dedup_unordered.csv")
    )
    if (Test-ExportFresh $sourceState "hsr" $hsrSource $hsrRequired) {
        Write-Host "==> Refresh HSR endgame export"
        Write-Host "    skipped: source unchanged ($($hsrSource.latest_collect_snapshot) / $($hsrSource.latest_collect_date))"
    }
    else {
        Invoke-Step "Refresh HSR endgame export" @(
            "python", "-m", "hsr_endgame_exporter", "export",
            "--from-date", $fromDate,
            "--to-date", $toDate,
            "--out", $HsrOut
        )
        $sourceState = Read-SourceState $statePath
        Set-StateEntry $sourceState "hsr" $hsrSource $statePath
        $sourceState = Read-SourceState $statePath
    }
}

if (-not $SkipZzz) {
    $zzzSource = Get-HfSourceState $ZzzRepoId
    $zzzRequired = @(
        (Join-Path $ZzzOut "export_report.md"),
        (Join-Path $ZzzOut "phase_index.csv"),
        (Join-Path $ZzzOut "team_rank_dedup_unordered.csv")
    )
    $zzzExportFresh = Test-ExportFresh $sourceState "zzz" $zzzSource $zzzRequired
    if ($zzzExportFresh) {
        Write-Host "==> Refresh ZZZ endgame export"
        Write-Host "    skipped: source unchanged ($($zzzSource.latest_collect_snapshot) / $($zzzSource.latest_collect_date))"
    }
    else {
        Invoke-Step "Refresh ZZZ endgame export" @(
            "python", "-m", "zzz_endgame_exporter", "export",
            "--from-date", $fromDate,
            "--to-date", $toDate,
            "--out", $ZzzOut
        )
        $sourceState = Read-SourceState $statePath
        Set-StateEntry $sourceState "zzz" $zzzSource $statePath
        $sourceState = Read-SourceState $statePath
    }

    $zzzCoreInputs = @(
        (Join-Path $ZzzOut "phase_index.csv"),
        (Join-Path $ZzzOut "character_usage_long.csv"),
        (Join-Path $ZzzOut "team_rank_dedup_unordered.csv"),
        (Join-Path $ZzzOut "prydwen_tier_current.csv"),
        $ZzzBox,
        $ZzzPlan,
        "configs\zzz_decision_baseline.json"
    )
    $notesDir = "configs\zzz_mechanism_notes"
    if (Test-Path -LiteralPath $notesDir) {
        $zzzCoreInputs += @(
            Get-ChildItem -LiteralPath $notesDir -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Extension -in @(".yaml", ".yml", ".json") } |
                Select-Object -ExpandProperty FullName
        )
    }
    $coverageOutputs = @(
        (Join-Path $ZzzOut "current_box_team_coverage.md"),
        (Join-Path $ZzzOut "target_box_team_coverage.md"),
        (Join-Path $ZzzOut "team_signature_aggregates.csv")
    )
    if (Test-OutputsFresh $zzzCoreInputs $coverageOutputs) {
        Write-Host "==> Build ZZZ current/target coverage"
        Write-Host "    skipped: derived outputs are fresh"
    }
    else {
        Invoke-Step "Build ZZZ current/target coverage" @(
            "python", "-m", "zzz_endgame_exporter", "coverage",
            "--box", $ZzzBox,
            "--out", $ZzzOut,
            "--plan", $ZzzPlan,
            "--plan-status", $ZzzPullPlanStatus
        )
    }

    $pullOutputs = @(
        (Join-Path $ZzzOut "current_pull_value_report.md"),
        (Join-Path $ZzzOut "next_pull_value_report.md")
    )
    if (Test-OutputsFresh ($zzzCoreInputs + $coverageOutputs) $pullOutputs) {
        Write-Host "==> Build ZZZ pull value report"
        Write-Host "    skipped: derived outputs are fresh"
    }
    else {
        Invoke-Step "Build ZZZ pull value report" @(
            "python", "-m", "zzz_endgame_exporter", "pull-value",
            "--box", $ZzzBox,
            "--out", $ZzzOut,
            "--plan", $ZzzPlan,
            "--plan-status", $ZzzPullPlanStatus
        )
    }

    $packetOutputs = @(
        (Join-Path $ZzzOut "current_gpt_pull_reviewer_packet.md"),
        (Join-Path $ZzzOut "next_gpt_pull_reviewer_packet.md")
    )
    if (Test-OutputsFresh ($zzzCoreInputs + $coverageOutputs + $pullOutputs) $packetOutputs) {
        Write-Host "==> Build ZZZ GPT reviewer packet"
        Write-Host "    skipped: derived outputs are fresh"
    }
    else {
        Invoke-Step "Build ZZZ GPT reviewer packet" @(
            "python", "-m", "zzz_endgame_exporter", "review-packet",
            "--box", $ZzzBox,
            "--out", $ZzzOut,
            "--plan", $ZzzPlan,
            "--plan-status", $ZzzPullPlanStatus
        )
    }
}

Write-Host "Update complete: $fromDate -> $toDate"

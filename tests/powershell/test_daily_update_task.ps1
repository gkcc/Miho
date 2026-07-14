param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $root "scripts\task_scheduler_v1.ps1")

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        throw $Message
    }
}

function Assert-Equal {
    param($Actual, $Expected, [string]$Message)
    if ($Actual -ne $Expected) {
        throw "$Message Expected=[$Expected] Actual=[$Actual]"
    }
}

function Assert-BytesEqual {
    param([byte[]]$Actual, [byte[]]$Expected, [string]$Message)
    Assert-Equal (Get-MihoSha256BytesV1 -Bytes $Actual) (Get-MihoSha256BytesV1 -Bytes $Expected) $Message
}

function Assert-Throws {
    param([scriptblock]$Action, [string]$MessageContains = "")
    $threw = $false
    try {
        & $Action
    }
    catch {
        $threw = $true
        if (-not [string]::IsNullOrEmpty($MessageContains) -and $_.Exception.Message -notlike "*$MessageContains*") {
            throw "Failure did not contain '$MessageContains': $($_.Exception.Message)"
        }
    }
    if (-not $threw) {
        throw "Expected action to fail."
    }
}

function Copy-TestSnapshot {
    param($Snapshot)
    if ($null -eq $Snapshot) { return $null }
    return Convert-MihoTaskXmlToSnapshotV1 -TaskName $Snapshot.TaskName -Xml ([string]$Snapshot.RawXml) -Sddl ([string]$Snapshot.Sddl)
}

function Set-TestTaskArguments {
    param($State, [string]$TaskName, [string]$Arguments)
    $snapshot = $State.Tasks[$TaskName]
    [xml]$document = $snapshot.RawXml
    $namespaces = New-Object System.Xml.XmlNamespaceManager($document.NameTable)
    $namespaces.AddNamespace("t", "http://schemas.microsoft.com/windows/2004/02/mit/task")
    $document.SelectSingleNode("/t:Task/t:Actions/t:Exec/t:Arguments", $namespaces).InnerText = $Arguments
    $State.Tasks[$TaskName] = Convert-MihoTaskXmlToSnapshotV1 -TaskName $TaskName -Xml $document.OuterXml -Sddl $snapshot.Sddl
}

function New-TestCase {
    param([string]$Label)

    $base = Join-Path ([System.IO.Path]::GetTempPath()) ("miho-task-v1-{0}-{1}" -f $Label, [guid]::NewGuid().ToString("N"))
    $workspace = Join-Path $base "中文 workspace with spaces"
    $automation = Join-Path $base "automation sibling"
    $source = Join-Path $base "source portable miho.exe"
    New-Item -ItemType Directory -Path (Join-Path $workspace "configs") -Force | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $workspace "configs\update_v1.json"), "{}", (Get-MihoUtf8V1))
    [System.IO.File]::WriteAllBytes($source, (Get-MihoUtf8V1).GetBytes("fake-cli-v1-$Label"))
    $identity = Get-MihoTaskIdentityV1 -OwnerSid (Get-MihoCurrentSidV1)
    $ownerKind = "manual"
    $ownerInstanceId = [guid]::NewGuid().ToString("D").ToLowerInvariant()
    $state = [pscustomobject]@{
        Tasks = @{}
        Calls = New-Object System.Collections.ArrayList
        RegisteredSpecs = New-Object System.Collections.ArrayList
        Version = "miho 1.0.0"
        CandidateExit = 0
        HealthExit = 0
        HealthHealthy = $true
        HealthAttempt = "pre-existing-attempt"
        HealthJson = ""
        HealthJsonAfterRun = ""
        DoNotAdvanceHealth = $false
        CandidateHasRun = $false
        WrongRunIdentity = $false
        BootstrapVerifyExit = 0
        FailRestoreCount = 0
        RestoreCount = 0
        LegacyRemovalManifestSeen = $false
        LegacyRemovalCanonicalSeen = $false
        ManifestPath = Join-Path $automation "automation-owner-v1.json"
        CanonicalName = $identity.TaskName
        OwnerSid = $identity.OwnerSid
    }

    $getTask = {
        param($name)
        $null = $state.Calls.Add([pscustomobject]@{ Operation = "GetTask"; Name = $name })
        if ($state.Tasks.ContainsKey([string]$name)) {
            return $state.Tasks[[string]$name]
        }
        return $null
    }.GetNewClosure()
    $registerTask = {
        param($spec)
        $null = $state.Calls.Add([pscustomobject]@{ Operation = "RegisterTask"; Name = $spec.TaskName })
        $null = $state.RegisteredSpecs.Add($spec)
        if ($state.Tasks.ContainsKey([string]$spec.TaskName) -and -not [bool]$spec.ReplaceExisting) {
            throw "fake collision"
        }
        $xml = New-MihoTaskXmlV1 -Spec $spec
        $sddl = "O:$($state.OwnerSid)G:$($state.OwnerSid)D:(A;;FA;;;$($state.OwnerSid))"
        $state.Tasks[[string]$spec.TaskName] = Convert-MihoTaskXmlToSnapshotV1 -TaskName $spec.TaskName -Xml $xml -Sddl $sddl
    }.GetNewClosure()
    $removeTask = {
        param($name)
        $null = $state.Calls.Add([pscustomobject]@{ Operation = "RemoveTask"; Name = $name })
        if ([string]$name -eq "MiHoYoEndgameDailyUpdate") {
            $state.LegacyRemovalManifestSeen = Test-Path -LiteralPath $state.ManifestPath
            $state.LegacyRemovalCanonicalSeen = $state.Tasks.ContainsKey($state.CanonicalName)
        }
        $state.Tasks.Remove([string]$name)
    }.GetNewClosure()
    $restoreTask = {
        param($name, $xml, $sddl)
        $state.RestoreCount += 1
        $null = $state.Calls.Add([pscustomobject]@{ Operation = "RestoreTask"; Name = $name })
        if ($state.FailRestoreCount -gt 0) {
            $state.FailRestoreCount -= 1
            throw "injected restore failure"
        }
        $state.Tasks[[string]$name] = Convert-MihoTaskXmlToSnapshotV1 -TaskName $name -Xml $xml -Sddl $sddl
    }.GetNewClosure()
    $runTask = {
        param($name, $timeout)
        $null = $state.Calls.Add([pscustomobject]@{ Operation = "RunTask"; Name = $name; Timeout = $timeout })
        $reportedName = [string]$name
        if ($state.WrongRunIdentity) {
            $reportedName = "wrong-candidate"
        }
        if ($state.CandidateExit -eq 0 -and -not $state.DoNotAdvanceHealth -and $state.Tasks.ContainsKey([string]$name)) {
            $arguments = [string]$state.Tasks[[string]$name].Arguments
            if ($arguments -match '--attempt-id "([A-Za-z0-9_-]+)"') {
                $state.HealthAttempt = [string]$Matches[1]
            }
        }
        $state.CandidateHasRun = $true
        return [pscustomobject]@{
            TaskName = $reportedName
            RunToken = "fake-run-$name"
            Completed = $true
            ExitCode = $state.CandidateExit
        }
    }.GetNewClosure()
    $disableTask = {
        param($name)
        $null = $state.Calls.Add([pscustomobject]@{ Operation = "DisableTask"; Name = $name })
        $snapshot = $state.Tasks[[string]$name]
        [xml]$document = $snapshot.RawXml
        $namespaces = New-Object System.Xml.XmlNamespaceManager($document.NameTable)
        $namespaces.AddNamespace("t", "http://schemas.microsoft.com/windows/2004/02/mit/task")
        $document.SelectSingleNode("/t:Task/t:Settings/t:Enabled", $namespaces).InnerText = "false"
        $state.Tasks[[string]$name] = Convert-MihoTaskXmlToSnapshotV1 -TaskName $name -Xml $document.OuterXml -Sddl $snapshot.Sddl
    }.GetNewClosure()
    $stopTask = {
        param($name, $timeout)
        $null = $state.Calls.Add([pscustomobject]@{ Operation = "StopTask"; Name = $name; Timeout = $timeout })
    }.GetNewClosure()
    $invokeProcess = {
        param($request)
        $argumentCopy = @($request.Arguments | ForEach-Object { [string]$_ })
        $null = $state.Calls.Add([pscustomobject]@{
            Operation = "InvokeProcess"
            File = [string]$request.FilePath
            Arguments = $argumentCopy
            WorkingDirectory = [string]$request.WorkingDirectory
            Timeout = $request.TimeoutSeconds
        })
        if ($argumentCopy.Count -eq 1 -and $argumentCopy[0] -eq "--version") {
            return [pscustomobject]@{ ExitCode = 0; StdOut = $state.Version; StdErr = "" }
        }
        if ($argumentCopy.Count -ge 7 -and $argumentCopy[0] -eq "workspace" -and $argumentCopy[1] -eq "bootstrap-transaction") {
            $operation = $argumentCopy[2]
            $transaction = $argumentCopy[6]
            if ($operation -eq "begin") {
                $state.CandidateHasRun = $false
                if (-not (Test-Path -LiteralPath $transaction)) { New-Item -ItemType Directory -Path $transaction | Out-Null }
                return [pscustomobject]@{ ExitCode = 0; StdOut = '{"schema_version":"miho-release-bootstrap-transaction-receipt-v1","operation":"begin","files_verified":12,"files_restored":0,"files_removed":0,"transaction_cleaned":false,"bootstrap":{"schema_version":"miho-release-bootstrap-receipt-v1","installed":[],"upgraded":[],"preserved":[],"unchanged":[],"state_updated":false}}'; StdErr = "" }
            }
            if ($operation -eq "verify") {
                return [pscustomobject]@{ ExitCode = $state.BootstrapVerifyExit; StdOut = '{"schema_version":"miho-release-bootstrap-transaction-receipt-v1","operation":"verify","files_verified":12,"files_restored":0,"files_removed":0,"transaction_cleaned":false}'; StdErr = "" }
            }
            if ($operation -eq "rollback") {
                return [pscustomobject]@{ ExitCode = 0; StdOut = '{"schema_version":"miho-release-bootstrap-transaction-receipt-v1","operation":"rollback","files_verified":12,"files_restored":0,"files_removed":0,"transaction_cleaned":false}'; StdErr = "" }
            }
            if ($operation -eq "commit" -or $operation -eq "discard") {
                if (Test-Path -LiteralPath $transaction) { Remove-Item -LiteralPath $transaction -Force }
                return [pscustomobject]@{ ExitCode = 0; StdOut = '{"schema_version":"miho-release-bootstrap-transaction-receipt-v1","operation":"' + $operation + '","files_verified":12,"files_restored":0,"files_removed":12,"transaction_cleaned":true}'; StdErr = "" }
            }
            if ($operation -eq "finalize") {
                $completed = $argumentCopy[8]
                return [pscustomobject]@{ ExitCode = 0; StdOut = '{"schema_version":"miho-release-bootstrap-transaction-receipt-v1","operation":"finalize","files_verified":12,"files_restored":0,"files_removed":0,"transaction_cleaned":true,"completed_operation":"' + $completed + '","completion_marker_removed":true}'; StdErr = "" }
            }
        }
        if ($argumentCopy.Count -ge 2 -and $argumentCopy[0] -eq "update" -and $argumentCopy[1] -eq "health") {
            if ($state.CandidateHasRun -and -not [string]::IsNullOrWhiteSpace($state.HealthJsonAfterRun)) {
                return [pscustomobject]@{ ExitCode = $state.HealthExit; StdOut = $state.HealthJsonAfterRun; StdErr = "" }
            }
            if (-not [string]::IsNullOrWhiteSpace($state.HealthJson)) {
                return [pscustomobject]@{ ExitCode = $state.HealthExit; StdOut = $state.HealthJson; StdErr = "" }
            }
            $healthyText = "false"
            if ($state.HealthHealthy) { $healthyText = "true" }
            return [pscustomobject]@{
                ExitCode = $state.HealthExit
                StdOut = '{"schema_version":"miho-update-health-v1","healthy":' + $healthyText + ',"attempt_id":"' + $state.HealthAttempt + '","checked_games":["hsr","zzz"]}'
                StdErr = ""
            }
        }
        throw "unexpected fake process invocation: $($argumentCopy -join ' ')"
    }.GetNewClosure()
    $adapter = @{
        GetTask = $getTask
        RegisterTask = $registerTask
        RemoveTask = $removeTask
        RestoreTask = $restoreTask
        RunTask = $runTask
        DisableTask = $disableTask
        StopTask = $stopTask
        InvokeProcess = $invokeProcess
    }
    $claimResult = Claim-MihoAutomationOwnerV1 -ExpectedOwnerKind $ownerKind -ExpectedOwnerInstanceId $ownerInstanceId -AutomationRoot $automation -Adapter $adapter
    $paths = Get-MihoAutomationPathsV1 -AutomationRoot $automation
    return [pscustomobject]@{
        Base = $base
        Workspace = $workspace
        Automation = $automation
        Source = $source
        Paths = $paths
        Identity = $identity
        OwnerKind = $ownerKind
        OwnerInstanceId = $ownerInstanceId
        State = $state
        Adapter = $adapter
        ClaimResult = $claimResult
    }
}

function Remove-TestCase {
    param($Case)
    if ($null -ne $Case -and (Test-Path -LiteralPath $Case.Base)) {
        Remove-Item -LiteralPath $Case.Base -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-TestInstall {
    param($Case, [hashtable]$FileHooks)
    $parameters = @{
        SourceCli = $Case.Source
        ExpectedOwnerKind = $Case.OwnerKind
        ExpectedOwnerInstanceId = $Case.OwnerInstanceId
        Workspace = $Case.Workspace
        AutomationRoot = $Case.Automation
        Adapter = $Case.Adapter
        CandidateTimeoutSeconds = 5
        ProcessTimeoutSeconds = 5
    }
    if ($null -ne $FileHooks) {
        $parameters.FileHooks = $FileHooks
    }
    return Install-MihoDailyUpdateTaskV1 @parameters
}

function Set-TestSourceV2 {
    param($Case)
    [System.IO.File]::WriteAllBytes($Case.Source, (Get-MihoUtf8V1).GetBytes("fake-cli-v2-$([guid]::NewGuid().ToString('N'))"))
    $Case.State.Version = "miho 2.0.0"
}

function Get-TestCurrentGenerationPath {
    param($Case)
    $slug = [regex]::Replace($Case.State.Version.ToLowerInvariant(), "[^a-z0-9._-]+", "-").Trim("-")
    $hash = Get-MihoFileSha256V1 -Path $Case.Source
    return Join-Path $Case.Paths.Generations "$slug-$hash"
}

function New-StrictLegacySnapshot {
    param($Case)
    $legacyRoot = "C:\Miho Legacy Root $([guid]::NewGuid().ToString('N'))"
    $scriptPath = Join-Path $legacyRoot "scripts\update_endgame_data.ps1"
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $scriptPath + '" -Root "' + $legacyRoot + '"'
    $escapedArguments = ConvertTo-MihoXmlEscapedV1 -Value $arguments
    $escapedSid = ConvertTo-MihoXmlEscapedV1 -Value $Case.Identity.OwnerSid
    $description = ConvertTo-MihoXmlEscapedV1 -Value $script:MihoLegacyDescriptionV1
    $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>$description</Description><URI>\MiHoYoEndgameDailyUpdate</URI><Source></Source></RegistrationInfo>
  <Triggers><CalendarTrigger><StartBoundary>2030-01-01T09:30:00</StartBoundary><Enabled>true</Enabled><ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>$escapedSid</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><StartWhenAvailable>true</StartWhenAvailable><AllowStartOnDemand>true</AllowStartOnDemand><Enabled>false</Enabled><Hidden>false</Hidden><ExecutionTimeLimit>PT2H</ExecutionTimeLimit></Settings>
  <Actions Context="Author"><Exec><Command>powershell.exe</Command><Arguments>$escapedArguments</Arguments><WorkingDirectory></WorkingDirectory></Exec></Actions>
</Task>
"@
    $sddl = "O:$($Case.Identity.OwnerSid)G:$($Case.Identity.OwnerSid)D:(A;;FA;;;$($Case.Identity.OwnerSid))"
    return Convert-MihoTaskXmlToSnapshotV1 -TaskName "MiHoYoEndgameDailyUpdate" -Xml $xml -Sddl $sddl
}

function Test-SuccessAndUnicodeQuoting {
    $case = New-TestCase -Label "success"
    try {
        $result = Invoke-TestInstall -Case $case
        Assert-True $result.healthy "Install did not report healthy."
        Assert-True ($case.State.Tasks.ContainsKey($case.Identity.TaskName)) "Canonical task was not registered."
        Assert-True (Test-Path -LiteralPath $case.Paths.Manifest) "Ownership manifest is missing."
        $manifest = (Read-MihoJsonFileV1 -Path $case.Paths.Manifest).Object
        Assert-Equal $manifest.schema "miho-automation-owner-v1" "Manifest schema mismatch."
        Assert-Equal $manifest.owner_sid $case.Identity.OwnerSid "Owner SID mismatch."
        Assert-True ([string]$manifest.install_id -match "^[0-9a-f-]{36}$") "Install id is not canonical."
        Assert-True (Test-MihoPathBelowV1 -Path $manifest.exe_path -Parent $case.Paths.Generations) "Task executable is not generation-owned."
        Assert-True (-not (Test-MihoPathBelowV1 -Path $manifest.exe_path -Parent $case.Workspace)) "Task points into workspace."
        Assert-True (-not (Test-MihoPathEqualV1 -Left $manifest.exe_path -Right $case.Source)) "Task points at source CLI."
        Assert-Equal (Get-MihoFileSha256V1 -Path $manifest.exe_path) $manifest.exe_sha256 "Copied CLI hash mismatch."
        $canonical = $case.State.Tasks[$case.Identity.TaskName]
        Assert-Equal $canonical.WorkingDirectory ([System.IO.Path]::GetFullPath($case.Workspace)) "WorkingDirectory is not explicit/canonical."
        $expectedArguments = 'update run --workspace "' + ([System.IO.Path]::GetFullPath($case.Workspace)) + '" --config "configs\update_v1.json"'
        Assert-Equal $canonical.Arguments $expectedArguments "CJK/space arguments were not quoted exactly."
        Assert-Equal $canonical.LogonType "InteractiveToken" "Canonical logon type mismatch."
        Assert-Equal $canonical.RunLevel "Limited" "Canonical run level mismatch."
        Assert-Equal $canonical.OwnerSid $case.Identity.OwnerSid "Canonical principal SID mismatch."
        Assert-Equal $canonical.TriggerCount 1 "Canonical task must have one daily trigger."
        $candidateSpecs = @($case.State.RegisteredSpecs | Where-Object { $_.TriggerKind -eq "None" })
        Assert-Equal $candidateSpecs.Count 1 "Exactly one no-trigger candidate was expected."
        Assert-Equal $candidateSpecs[0].WorkingDirectory ([System.IO.Path]::GetFullPath($case.Workspace)) "Candidate WorkingDirectory mismatch."
        Assert-True ($candidateSpecs[0].Arguments -like ($expectedArguments + ' --attempt-id "installer-*"')) "Candidate did not bind an explicit update attempt."
        Assert-True (-not $case.State.Tasks.ContainsKey($candidateSpecs[0].TaskName)) "Candidate was not removed."
        $processCalls = @($case.State.Calls | Where-Object { $_.Operation -eq "InvokeProcess" })
        Assert-Equal $processCalls[0].Arguments[0] "--version" "Generation version probe was not first."
        Assert-Equal $processCalls[1].Arguments[0] "workspace" "Bootstrap transaction did not follow generation staging."
        Assert-Equal $processCalls[1].Arguments[1] "bootstrap-transaction" "Bootstrap transaction command mismatch."
        Assert-Equal $processCalls[1].Arguments[2] "begin" "Bootstrap begin operation mismatch."
        Assert-Equal $processCalls[1].File $manifest.exe_path "Bootstrap transaction did not use the staged generation."
        Assert-Equal $processCalls[3].File $manifest.exe_path "Post-candidate health did not use copied generation."
        Assert-Equal $processCalls[3].Arguments[0] "update" "Health command mismatch."
        Assert-Equal $processCalls[3].Arguments[1] "health" "Health command mismatch."
        Assert-Equal $result.health_attempt_id (($candidateSpecs[0].Arguments -replace '^.*--attempt-id "([A-Za-z0-9_-]+)"$', '$1')) "Health was not bound to the explicit candidate attempt."
        Assert-Equal (Get-MihoSnapshotActionFingerprintV1 -Snapshot $canonical -InstallId $manifest.install_id) $manifest.action_fingerprint "Live action fingerprint mismatch."
    }
    finally {
        Remove-TestCase $case
    }
}

function Test-OwnershipConflictPreservesState {
    $case = New-TestCase -Label "ownership"
    try {
        $null = Invoke-TestInstall $case
        $manifestBytes = [System.IO.File]::ReadAllBytes($case.Paths.Manifest)
        Set-TestTaskArguments -State $case.State -TaskName $case.Identity.TaskName -Arguments "foreign drift"
        $drifted = Copy-TestSnapshot $case.State.Tasks[$case.Identity.TaskName]
        $callsBefore = $case.State.Calls.Count
        Assert-Throws { Invoke-TestInstall $case } "drifted"
        Assert-True (Test-MihoSnapshotExactlyV1 -Snapshot $case.State.Tasks[$case.Identity.TaskName] -Expected $drifted) "Foreign task drift was overwritten."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $manifestBytes "Conflict changed manifest."
        $newCalls = @($case.State.Calls | Select-Object -Skip $callsBefore | Where-Object { $_.Operation -eq "InvokeProcess" })
        Assert-Equal $newCalls.Count 0 "Conflict should fail before bootstrap."
    }
    finally { Remove-TestCase $case }
}

function Test-CaseSensitiveWorkspaceIdentityIsNotCollapsed {
    $case = New-TestCase -Label "case-sensitive-workspace"
    try {
        $sensitive = Join-Path $case.Base "case-sensitive-owner-boundary"
        New-Item -ItemType Directory -Path $sensitive -ErrorAction Stop | Out-Null
        & fsutil.exe file SetCaseSensitiveInfo $sensitive enable | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "fsutil could not enable the case-sensitive test directory." }
        $upper = Join-Path $sensitive "A"
        $lower = Join-Path $sensitive "a"
        foreach ($workspace in @($upper, $lower)) {
            New-Item -ItemType Directory -Path (Join-Path $workspace "configs") -ErrorAction Stop | Out-Null
            [System.IO.File]::WriteAllText((Join-Path $workspace "configs\update_v1.json"), "{}", (Get-MihoUtf8V1))
        }
        Assert-Equal @(Get-ChildItem -LiteralPath $sensitive -Directory -Force).Count 2 "Case-sensitive fixture did not create distinct A/a directories."
        Assert-True (-not (Test-MihoPathEqualV1 -Left $upper -Right $lower)) "Distinct case-sensitive directory identities were collapsed."
        Assert-True (-not (Test-MihoPathBelowV1 -Path (Join-Path $lower "configs") -Parent $upper)) "Case-sensitive sibling was accepted below the bound workspace."

        $parameters = @{
            SourceCli = $case.Source
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            Workspace = $upper
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            CandidateTimeoutSeconds = 5
            ProcessTimeoutSeconds = 5
        }
        $null = Install-MihoDailyUpdateTaskV1 @parameters
        $oldTask = Copy-TestSnapshot $case.State.Tasks[$case.Identity.TaskName]
        $oldManifest = [System.IO.File]::ReadAllBytes($case.Paths.Manifest)
        $parameters.Workspace = $lower
        Assert-Throws { Install-MihoDailyUpdateTaskV1 @parameters } "different workspace"
        Assert-True (Test-MihoSnapshotExactlyV1 -Snapshot $case.State.Tasks[$case.Identity.TaskName] -Expected $oldTask) "Case-sensitive workspace mismatch changed the canonical task."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $oldManifest "Case-sensitive workspace mismatch changed the manifest."
    }
    finally { Remove-TestCase $case }
}

function Test-CandidateFailurePreservesOld {
    $case = New-TestCase -Label "candidate"
    try {
        $null = Invoke-TestInstall $case
        $oldTask = Copy-TestSnapshot $case.State.Tasks[$case.Identity.TaskName]
        $oldManifest = [System.IO.File]::ReadAllBytes($case.Paths.Manifest)
        Set-TestSourceV2 $case
        $failedGeneration = Get-TestCurrentGenerationPath $case
        $case.State.CandidateExit = 7
        Assert-Throws { Invoke-TestInstall $case } "specific candidate"
        Assert-True (Test-MihoSnapshotExactlyV1 $case.State.Tasks[$case.Identity.TaskName] $oldTask) "Candidate failure changed canonical task."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $oldManifest "Candidate failure changed manifest."
        Assert-Equal @($case.State.Tasks.Keys | Where-Object { $_ -like "*Candidate*" }).Count 0 "Candidate failure left a task."
        Assert-True (-not (Test-Path -LiteralPath $failedGeneration)) "Candidate failure left its newly created generation."
    }
    finally { Remove-TestCase $case }
}

function Test-HealthFailurePreservesOld {
    $case = New-TestCase -Label "health"
    try {
        $null = Invoke-TestInstall $case
        $oldTask = Copy-TestSnapshot $case.State.Tasks[$case.Identity.TaskName]
        $oldManifest = [System.IO.File]::ReadAllBytes($case.Paths.Manifest)
        Set-TestSourceV2 $case
        $failedGeneration = Get-TestCurrentGenerationPath $case
        $case.State.HealthHealthy = $false
        Assert-Throws { Invoke-TestInstall $case } "healthy=true"
        Assert-True (Test-MihoSnapshotExactlyV1 $case.State.Tasks[$case.Identity.TaskName] $oldTask) "Health failure changed canonical task."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $oldManifest "Health failure changed manifest."
        Assert-True (-not (Test-Path -LiteralPath $failedGeneration)) "Health failure left its newly created generation."
    }
    finally { Remove-TestCase $case }
}

function New-ManifestFailureHooks {
    param($HookState)
    $writer = {
        param($path, $bytes, $purpose)
        if ($purpose -eq "manifest" -and $HookState.FailCount -gt 0) {
            $HookState.FailCount -= 1
            throw "injected manifest write failure"
        }
        Write-MihoAtomicBytesCoreV1 -Path $path -Bytes ([byte[]]$bytes)
    }.GetNewClosure()
    return @{ WriteAtomicFile = $writer }
}

function New-JournalPhaseCrashHooks {
    param($HookState)
    $writer = {
        param($path, $bytes, $purpose)
        Write-MihoAtomicBytesCoreV1 -Path $path -Bytes ([byte[]]$bytes)
        if ($purpose -eq "journal" -and $HookState.FailCount -gt 0) {
            $json = (New-Object System.Text.UTF8Encoding($false, $true)).GetString([byte[]]$bytes)
            $record = $json | ConvertFrom-Json -ErrorAction Stop
            if ([string]$record.phase -ceq [string]$HookState.TargetPhase) {
                $HookState.FailCount -= 1
                throw "simulated crash after journal phase $($HookState.TargetPhase)"
            }
        }
    }.GetNewClosure()
    return @{ WriteAtomicFile = $writer }
}

function New-GenerationCheckpointCrashHooks {
    param($HookState)
    $checkpoint = {
        param($stage, $path)
        if ($HookState.FailCount -gt 0 -and [string]$stage -ceq [string]$HookState.TargetStage) {
            $HookState.FailCount -= 1
            throw "simulated generation crash after $stage"
        }
    }.GetNewClosure()
    return @{ GenerationCheckpoint = $checkpoint }
}

function New-OrderedFailureHooks {
    param($HookState)
    $writer = {
        param($path, $bytes, $purpose)
        $null = $HookState.Calls.Add([pscustomobject]@{ Operation = "FileWrite"; Purpose = [string]$purpose })
        if ($purpose -eq "manifest" -and $HookState.FailCount -gt 0) {
            $HookState.FailCount -= 1
            throw "ordered manifest failure"
        }
        Write-MihoAtomicBytesCoreV1 -Path $path -Bytes ([byte[]]$bytes)
    }.GetNewClosure()
    return @{ WriteAtomicFile = $writer }
}

function New-AtomicWriteThenThrowHooks {
    param($HookState)
    $writer = {
        param($path, $bytes, $purpose)
        Write-MihoAtomicBytesCoreV1 -Path $path -Bytes ([byte[]]$bytes)
        if ($HookState.FailCount -gt 0 -and [string]$purpose -ceq [string]$HookState.TargetPurpose) {
            $HookState.FailCount -= 1
            throw "simulated write-then-throw for $purpose"
        }
    }.GetNewClosure()
    return @{ WriteAtomicFile = $writer }
}

function New-ReleaseCheckpointCrashHooks {
    param($HookState)
    $checkpoint = {
        param($stage)
        if ($HookState.FailCount -gt 0 -and [string]$stage -ceq [string]$HookState.TargetStage) {
            $HookState.FailCount -= 1
            throw "simulated release crash after $stage"
        }
    }.GetNewClosure()
    return @{ ReleaseCheckpoint = $checkpoint }
}

function Invoke-TestPowerShellProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Engine,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& $Engine @Arguments 2>&1 | ForEach-Object { [string]$_ })
        $exitCode = [int]$LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previousPreference }
    return [pscustomobject][ordered]@{ ExitCode = $exitCode; Output = $output }
}

function Test-ManifestFailureRollsBackXmlSddlAndManifest {
    $case = New-TestCase -Label "manifest-rollback"
    try {
        $null = Invoke-TestInstall $case
        $oldTask = Copy-TestSnapshot $case.State.Tasks[$case.Identity.TaskName]
        $oldManifest = [System.IO.File]::ReadAllBytes($case.Paths.Manifest)
        Set-TestSourceV2 $case
        $failedGeneration = Get-TestCurrentGenerationPath $case
        $hookState = [pscustomobject]@{ FailCount = 1 }
        $hooks = New-ManifestFailureHooks $hookState
        Assert-Throws { Invoke-TestInstall -Case $case -FileHooks $hooks } "manifest write failure"
        Assert-True (Test-MihoSnapshotExactlyV1 $case.State.Tasks[$case.Identity.TaskName] $oldTask) "Manifest failure did not restore XML/SDDL."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $oldManifest "Manifest failure did not restore exact manifest bytes."
        Assert-True ($case.State.RestoreCount -gt 0) "Rollback did not invoke exact task restore."
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Journal)) "Successful rollback left unfinished journal."
        Assert-True (-not (Test-Path -LiteralPath $failedGeneration)) "Rolled-back install left its new generation."
    }
    finally { Remove-TestCase $case }
}

function Test-UnfinishedJournalRecoversFirst {
    $case = New-TestCase -Label "journal-recovery"
    try {
        $null = Invoke-TestInstall $case
        $oldTask = Copy-TestSnapshot $case.State.Tasks[$case.Identity.TaskName]
        $oldManifest = [System.IO.File]::ReadAllBytes($case.Paths.Manifest)
        Set-TestSourceV2 $case
        $failedGeneration = Get-TestCurrentGenerationPath $case
        $case.State.FailRestoreCount = 1
        $hookState = [pscustomobject]@{ FailCount = 1 }
        $hooks = New-ManifestFailureHooks $hookState
        Assert-Throws { Invoke-TestInstall -Case $case -FileHooks $hooks } "rollback is pending"
        Assert-True (Test-Path -LiteralPath $case.Paths.Journal) "Interrupted rollback did not preserve journal."
        $case.State.FailRestoreCount = 0
        $recovered = Repair-MihoAutomationJournalV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        Assert-True $recovered.recovered "Journal recovery did not run."
        Assert-True (Test-MihoSnapshotExactlyV1 $case.State.Tasks[$case.Identity.TaskName] $oldTask) "Journal recovery did not restore task."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $oldManifest "Journal recovery did not restore manifest."
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Journal)) "Recovered journal was not removed."
        Assert-True (-not (Test-Path -LiteralPath $failedGeneration)) "Journal recovery left the failed new generation."
    }
    finally { Remove-TestCase $case }
}

function Test-UninstallSuccessIsNarrow {
    $case = New-TestCase -Label "uninstall"
    try {
        $null = Invoke-TestInstall $case
        $manifest = (Read-MihoJsonFileV1 $case.Paths.Manifest).Object
        $workspaceSentinel = Join-Path $case.Workspace "Box and output sentinel.txt"
        [System.IO.File]::WriteAllText($workspaceSentinel, "keep")
        $otherGeneration = Join-Path $case.Paths.Generations "foreign-generation"
        New-Item -ItemType Directory -Path $otherGeneration | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $otherGeneration "keep.txt"), "keep")
        $unrelatedSpec = New-MihoTaskSpecV1 -TaskName ("Unrelated-" + [guid]::NewGuid().ToString("N")) -Execute $manifest.exe_path -Arguments "unrelated" -WorkingDirectory $case.Workspace -OwnerSid $case.Identity.OwnerSid -Source "foreign" -InstallId ([guid]::NewGuid().ToString("D"))
        Invoke-MihoAdapterV1 -Adapter $case.Adapter -Operation RegisterTask -Arguments @($unrelatedSpec) | Out-Null
        $result = Uninstall-MihoDailyUpdateTaskV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -QuiesceTimeoutSeconds 5
        Assert-True $result.removed "Uninstall did not remove owned state."
        Assert-True (-not $case.State.Tasks.ContainsKey($case.Identity.TaskName)) "Owned canonical task remains."
        Assert-True (-not (Test-Path -LiteralPath $manifest.generation_path)) "Owned generation remains."
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Manifest)) "Owned manifest remains."
        Assert-True (Test-Path -LiteralPath $workspaceSentinel) "Uninstall touched workspace/Box/output."
        Assert-True (Test-Path -LiteralPath $otherGeneration) "Uninstall touched unrelated generation."
        Assert-True ($case.State.Tasks.ContainsKey($unrelatedSpec.TaskName)) "Uninstall touched unrelated task."
    }
    finally { Remove-TestCase $case }
}

function Test-UninstallDriftFailsClosed {
    $case = New-TestCase -Label "uninstall-drift"
    try {
        $null = Invoke-TestInstall $case
        $manifest = (Read-MihoJsonFileV1 $case.Paths.Manifest).Object
        Set-TestTaskArguments -State $case.State -TaskName $case.Identity.TaskName -Arguments "drift before uninstall"
        $drifted = Copy-TestSnapshot $case.State.Tasks[$case.Identity.TaskName]
        Assert-Throws { Uninstall-MihoDailyUpdateTaskV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter } "drifted"
        Assert-True (Test-MihoSnapshotExactlyV1 $case.State.Tasks[$case.Identity.TaskName] $drifted) "Uninstall overwrote drifted task."
        Assert-True (Test-Path -LiteralPath $manifest.generation_path) "Uninstall removed generation after drift."
        Assert-True (Test-Path -LiteralPath $case.Paths.Manifest) "Uninstall removed manifest after drift."
        Assert-Equal @($case.State.Calls | Where-Object { $_.Operation -eq "DisableTask" }).Count 0 "Drifted uninstall quiesced task before rejecting."
    }
    finally { Remove-TestCase $case }
}

function Test-PasswordAndHighestAreRejected {
    foreach ($mode in @("Password", "Highest")) {
        $case = New-TestCase -Label $mode
        try {
            $installId = [guid]::NewGuid().ToString("D")
            $spec = New-MihoTaskSpecV1 -TaskName $case.Identity.TaskName -Execute $case.Source -Arguments "foreign" -WorkingDirectory $case.Workspace -OwnerSid $case.Identity.OwnerSid -Source "foreign" -InstallId $installId -TriggerKind Daily
            $xml = New-MihoTaskXmlV1 $spec
            if ($mode -eq "Password") {
                $xml = $xml.Replace("<LogonType>InteractiveToken</LogonType>", "<LogonType>Password</LogonType>")
            }
            else {
                $xml = $xml.Replace("<RunLevel>LeastPrivilege</RunLevel>", "<RunLevel>HighestAvailable</RunLevel>")
            }
            $foreignSddl = "O:$($case.Identity.OwnerSid)G:$($case.Identity.OwnerSid)D:(A;;FA;;;$($case.Identity.OwnerSid))"
            $foreign = Convert-MihoTaskXmlToSnapshotV1 -TaskName $case.Identity.TaskName -Xml $xml -Sddl $foreignSddl
            $case.State.Tasks[$case.Identity.TaskName] = $foreign
            Assert-Throws { Invoke-TestInstall $case } $(if ($mode -eq "Password") { "password" } else { "highest" })
            Assert-True (Test-MihoSnapshotExactlyV1 $case.State.Tasks[$case.Identity.TaskName] $foreign) "$mode task was overwritten."
            Assert-Equal @($case.State.Calls | Where-Object { $_.Operation -eq "InvokeProcess" }).Count 0 "$mode task was not rejected before bootstrap."
        }
        finally { Remove-TestCase $case }
    }
}

function Test-StrictLegacyRequiresExactExternalAuthorization {
    $case = New-TestCase -Label "legacy"
    try {
        $legacy = New-StrictLegacySnapshot $case
        $case.State.Tasks["MiHoYoEndgameDailyUpdate"] = $legacy
        $case.State.CandidateExit = 7
        Assert-Throws { Invoke-TestInstall $case } "specific candidate"
        Assert-True ($case.State.Tasks.ContainsKey("MiHoYoEndgameDailyUpdate")) "Legacy task was removed before candidate/commit."
        $case.State.CandidateExit = 0
        $result = Invoke-TestInstall $case
        Assert-True (-not $result.legacy_removed) "Legacy task was removed without external authorization."
        Assert-True ($case.State.Tasks.ContainsKey("MiHoYoEndgameDailyUpdate")) "Legacy task was not preserved by default."

        $parameters = @{
            SourceCli = $case.Source
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            Workspace = $case.Workspace
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            CandidateTimeoutSeconds = 5
            ProcessTimeoutSeconds = 5
            ExpectedLegacyXmlSha256 = Get-MihoSha256TextV1 -Text ([string]$legacy.RawXml)
            ExpectedLegacySddlSha256 = Get-MihoSddlSemanticFingerprintV1 -Sddl ([string]$legacy.Sddl)
        }
        $authorized = Install-MihoDailyUpdateTaskV1 @parameters
        Assert-True $authorized.legacy_removed "Exactly authorized legacy task was not removed after commit."
        Assert-True (-not $case.State.Tasks.ContainsKey("MiHoYoEndgameDailyUpdate")) "Strict legacy task remains."
        Assert-True $case.State.LegacyRemovalManifestSeen "Legacy was removed before manifest commit."
        Assert-True $case.State.LegacyRemovalCanonicalSeen "Legacy was removed before canonical task existed."
    }
    finally { Remove-TestCase $case }
}

function Test-LegacyNearMissIsPreserved {
    $case = New-TestCase -Label "legacy-near-miss"
    try {
        $legacy = New-StrictLegacySnapshot $case
        $case.State.Tasks["MiHoYoEndgameDailyUpdate"] = $legacy
        Set-TestTaskArguments -State $case.State -TaskName "MiHoYoEndgameDailyUpdate" -Arguments ($legacy.Arguments + " --extra")
        $result = Invoke-TestInstall $case
        Assert-True (-not $result.legacy_removed) "Near-miss legacy task was removed."
        Assert-True ($case.State.Tasks.ContainsKey("MiHoYoEndgameDailyUpdate")) "Near-miss legacy task was not preserved."
    }
    finally { Remove-TestCase $case }
}

function Test-SuccessfulUpgradeRetiresExactOldGeneration {
    $case = New-TestCase -Label "upgrade-cleanup"
    try {
        $null = Invoke-TestInstall $case
        $oldManifest = (Read-MihoJsonFileV1 $case.Paths.Manifest).Object
        Assert-True (Test-Path -LiteralPath $oldManifest.generation_path) "Initial generation missing."
        Set-TestSourceV2 $case
        $newGeneration = Get-TestCurrentGenerationPath $case
        $result = Invoke-TestInstall $case
        Assert-True $result.retired_generation_removed "Upgrade did not report retired generation cleanup."
        Assert-True (-not (Test-Path -LiteralPath $oldManifest.generation_path)) "Upgrade left exact old generation."
        Assert-True (Test-Path -LiteralPath $newGeneration) "Upgrade removed new generation."
    }
    finally { Remove-TestCase $case }
}

function Test-OmittedWorkspaceReusesOwnedWorkspaceBeforeFallback {
    $case = New-TestCase -Label "owned-workspace-upgrade"
    try {
        $null = Invoke-TestInstall $case
        Set-TestSourceV2 $case
        $fallback = Join-Path $case.Base "different fallback workspace"
        New-Item -ItemType Directory -Path (Join-Path $fallback "configs") -Force | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $fallback "configs\update_v1.json"), "{}", (Get-MihoUtf8V1))
        $settingsPath = Join-Path $fallback "desktop-settings-v1.json"
        $settings = [pscustomobject][ordered]@{
            schema_version = "miho-desktop-settings-v1"
            selected_workspace = $fallback
            revision = 2
        }
        [System.IO.File]::WriteAllText($settingsPath, (($settings | ConvertTo-Json) + "`n"), (Get-MihoUtf8V1))
        $callsBefore = $case.State.Calls.Count
        $parameters = @{
            SourceCli = $case.Source
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            DefaultWorkspace = $fallback
            DesktopSettingsPath = $settingsPath
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            CandidateTimeoutSeconds = 5
            ProcessTimeoutSeconds = 5
        }
        $result = Install-MihoDailyUpdateTaskV1 @parameters
        Assert-True (Test-MihoPathEqualV1 -Left $result.workspace -Right $case.Workspace) "Upgrade used fallback instead of existing owned workspace."
        $newProcessCalls = @($case.State.Calls | Select-Object -Skip $callsBefore | Where-Object { $_.Operation -eq "InvokeProcess" })
        Assert-True ($newProcessCalls.Count -ge 1) "Upgrade did not run bootstrap."
        Assert-True (Test-MihoPathEqualV1 -Left $newProcessCalls[1].WorkingDirectory -Right $case.Workspace) "Bootstrap used fallback workspace."
        Assert-Equal $newProcessCalls[1].Arguments[4] ([System.IO.Path]::GetFullPath($case.Workspace)) "Bootstrap argument used fallback workspace."
        $canonical = $case.State.Tasks[$case.Identity.TaskName]
        Assert-True ($canonical.Arguments -like "*$($case.Workspace)*") "Canonical action did not retain owned workspace."
        Assert-True ($canonical.Arguments -notlike "*$fallback*") "Canonical action bound fallback workspace."
    }
    finally { Remove-TestCase $case }
}

function Test-FreshInstallUsesEnvironmentWorkspaceBeforeDesktopFallback {
    $case = New-TestCase -Label "environment-workspace-selection"
    $previousEnvironmentWorkspace = [Environment]::GetEnvironmentVariable("MIHO_DATA_ROOT", [EnvironmentVariableTarget]::Process)
    try {
        $environmentWorkspace = Join-Path $case.Base "environment 用户 workspace"
        $default = Join-Path $case.Base "default app data"
        $persisted = Join-Path $case.Base "persisted desktop workspace"
        foreach ($workspace in @($environmentWorkspace, $default, $persisted)) {
            New-Item -ItemType Directory -Path (Join-Path $workspace "configs") -Force | Out-Null
            [System.IO.File]::WriteAllText((Join-Path $workspace "configs\update_v1.json"), "{}", (Get-MihoUtf8V1))
        }
        $settingsPath = Join-Path $default "desktop-settings-v1.json"
        $settings = [pscustomobject][ordered]@{
            schema_version = "miho-desktop-settings-v1"
            selected_workspace = $persisted
            revision = 11
        }
        [System.IO.File]::WriteAllText($settingsPath, (($settings | ConvertTo-Json) + "`n"), (Get-MihoUtf8V1))
        [Environment]::SetEnvironmentVariable("MIHO_DATA_ROOT", $environmentWorkspace, [EnvironmentVariableTarget]::Process)

        $workspaceOverride = Select-MihoInstallWorkspaceOverrideV1 `
            -ExplicitWorkspace "" `
            -EnvironmentWorkspace $env:MIHO_DATA_ROOT
        Assert-True (Test-MihoPathEqualV1 -Left $workspaceOverride -Right $environmentWorkspace) "Install wrapper selection ignored MIHO_DATA_ROOT."
        $explicitOverride = Select-MihoInstallWorkspaceOverrideV1 `
            -ExplicitWorkspace $case.Workspace `
            -EnvironmentWorkspace $env:MIHO_DATA_ROOT
        Assert-True (Test-MihoPathEqualV1 -Left $explicitOverride -Right $case.Workspace) "Explicit Workspace did not override MIHO_DATA_ROOT."

        $parameters = @{
            SourceCli = $case.Source
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            Workspace = $workspaceOverride
            DefaultWorkspace = $default
            DesktopSettingsPath = $settingsPath
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            CandidateTimeoutSeconds = 5
            ProcessTimeoutSeconds = 5
        }
        $result = Install-MihoDailyUpdateTaskV1 @parameters

        Assert-True (Test-MihoPathEqualV1 -Left $result.workspace -Right $environmentWorkspace) "Fresh install did not bind MIHO_DATA_ROOT."
        $canonical = $case.State.Tasks[$case.Identity.TaskName]
        Assert-True (Test-MihoPathEqualV1 -Left $canonical.WorkingDirectory -Right $environmentWorkspace) "Fresh canonical task used desktop fallback instead of MIHO_DATA_ROOT."
        Assert-True ($canonical.Arguments -like "*$environmentWorkspace*") "Fresh canonical arguments omitted MIHO_DATA_ROOT."
        Assert-True ($canonical.Arguments -notlike "*$persisted*") "Fresh canonical arguments bound persisted desktop settings."
    }
    finally {
        [Environment]::SetEnvironmentVariable("MIHO_DATA_ROOT", $previousEnvironmentWorkspace, [EnvironmentVariableTarget]::Process)
        Remove-TestCase $case
    }
}

function Test-ExistingOwnedWorkspaceRejectsEnvironmentMismatchWithoutMutation {
    $case = New-TestCase -Label "owned-environment-mismatch"
    $previousEnvironmentWorkspace = [Environment]::GetEnvironmentVariable("MIHO_DATA_ROOT", [EnvironmentVariableTarget]::Process)
    try {
        $null = Invoke-TestInstall $case
        $oldTask = Copy-TestSnapshot $case.State.Tasks[$case.Identity.TaskName]
        $oldManifest = [System.IO.File]::ReadAllBytes($case.Paths.Manifest)
        $environmentWorkspace = Join-Path $case.Base "different environment workspace"
        New-Item -ItemType Directory -Path (Join-Path $environmentWorkspace "configs") -Force | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $environmentWorkspace "configs\update_v1.json"), "{}", (Get-MihoUtf8V1))
        [Environment]::SetEnvironmentVariable("MIHO_DATA_ROOT", $environmentWorkspace, [EnvironmentVariableTarget]::Process)
        $workspaceOverride = Select-MihoInstallWorkspaceOverrideV1 `
            -ExplicitWorkspace "" `
            -EnvironmentWorkspace $env:MIHO_DATA_ROOT
        $callsBefore = $case.State.Calls.Count
        $parameters = @{
            SourceCli = $case.Source
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            Workspace = $workspaceOverride
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            CandidateTimeoutSeconds = 5
            ProcessTimeoutSeconds = 5
        }

        Assert-Throws { Install-MihoDailyUpdateTaskV1 @parameters } "different workspace"

        Assert-True (Test-MihoSnapshotExactlyV1 -Snapshot $case.State.Tasks[$case.Identity.TaskName] -Expected $oldTask) "Environment mismatch changed the owned task."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $oldManifest "Environment mismatch changed the ownership manifest."
        $mutatingCalls = @($case.State.Calls | Select-Object -Skip $callsBefore | Where-Object { $_.Operation -in @("InvokeProcess", "RegisterTask", "RemoveTask", "RestoreTask") })
        Assert-Equal $mutatingCalls.Count 0 "Environment mismatch performed work before requiring explicit rebind."
    }
    finally {
        [Environment]::SetEnvironmentVariable("MIHO_DATA_ROOT", $previousEnvironmentWorkspace, [EnvironmentVariableTarget]::Process)
        Remove-TestCase $case
    }
}

function Test-FreshInstallUsesStrictDesktopSettingsWorkspace {
    $case = New-TestCase -Label "desktop-settings-selection"
    try {
        $default = Join-Path $case.Base "default app data"
        $selected = Join-Path $case.Base "用户 selected workspace"
        foreach ($workspace in @($default, $selected)) {
            New-Item -ItemType Directory -Path (Join-Path $workspace "configs") -Force | Out-Null
            [System.IO.File]::WriteAllText((Join-Path $workspace "configs\update_v1.json"), "{}", (Get-MihoUtf8V1))
        }
        $settingsPath = Join-Path $default "desktop-settings-v1.json"
        $settings = [pscustomobject][ordered]@{
            schema_version = "miho-desktop-settings-v1"
            selected_workspace = $selected
            revision = 7
        }
        [System.IO.File]::WriteAllText($settingsPath, (($settings | ConvertTo-Json) + "`n"), (Get-MihoUtf8V1))
        $parameters = @{
            SourceCli = $case.Source
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            DefaultWorkspace = $default
            DesktopSettingsPath = $settingsPath
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            CandidateTimeoutSeconds = 5
            ProcessTimeoutSeconds = 5
        }

        $result = Install-MihoDailyUpdateTaskV1 @parameters

        Assert-True (Test-MihoPathEqualV1 -Left $result.workspace -Right $selected) "Fresh install ignored selected desktop workspace."
        $canonical = $case.State.Tasks[$case.Identity.TaskName]
        Assert-True (Test-MihoPathEqualV1 -Left $canonical.WorkingDirectory -Right $selected) "Fresh canonical task used the default workspace."
        Assert-True ($canonical.Arguments -like "*$selected*") "Fresh canonical arguments omitted selected workspace."
    }
    finally { Remove-TestCase $case }
}

function Test-DesktopSettingsParserRejectsUnknownDuplicateAndInvalidBytes {
    $case = New-TestCase -Label "desktop-settings-invalid"
    try {
        $default = Join-Path $case.Base "default"
        $selected = Join-Path $case.Base "selected"
        New-Item -ItemType Directory -Path $default | Out-Null
        New-Item -ItemType Directory -Path $selected | Out-Null
        $settingsPath = Join-Path $default "desktop-settings-v1.json"
        $selectedJson = $selected | ConvertTo-Json -Compress
        $invalidTexts = @(
            ('{"schema_version":"miho-desktop-settings-v1","schema_version":"miho-desktop-settings-v1","selected_workspace":' + $selectedJson + ',"revision":1}'),
            ('{"schema_version":"miho-desktop-settings-v1","selected_workspace":' + $selectedJson + ',"revision":1,"unknown":true}'),
            ('{"Schema_version":"miho-desktop-settings-v1","selected_workspace":' + $selectedJson + ',"revision":1}'),
            ('{"schema_version":"future","selected_workspace":' + $selectedJson + ',"revision":1}'),
            ('{"schema_version":"miho-desktop-settings-v1","selected_workspace":"relative","revision":1}'),
            ('{"schema_version":"miho-desktop-settings-v1","selected_workspace":' + $selectedJson + ',"revision":1.5}')
        )
        foreach ($text in $invalidTexts) {
            [System.IO.File]::WriteAllText($settingsPath, $text, (Get-MihoUtf8V1))
            Assert-Throws {
                Resolve-MihoDesktopWorkspaceV1 -DefaultWorkspace $default -SettingsPath $settingsPath
            } "settings"
        }
        [System.IO.File]::WriteAllBytes($settingsPath, [byte[]](0xC3, 0x28))
        Assert-Throws {
            Resolve-MihoDesktopWorkspaceV1 -DefaultWorkspace $default -SettingsPath $settingsPath
        } "UTF-8"
        [System.IO.File]::WriteAllBytes($settingsPath, [byte[]](0x20) * ($script:MihoDesktopSettingsMaximumBytesV1 + 1))
        Assert-Throws {
            Resolve-MihoDesktopWorkspaceV1 -DefaultWorkspace $default -SettingsPath $settingsPath
        } "size"
    }
    finally { Remove-TestCase $case }
}

function Test-FreshOmittedWorkspaceWithoutFallbackFails {
    $case = New-TestCase -Label "fresh-no-workspace"
    try {
        $parameters = @{
            SourceCli = $case.Source
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            CandidateTimeoutSeconds = 5
            ProcessTimeoutSeconds = 5
        }
        Assert-Throws { Install-MihoDailyUpdateTaskV1 @parameters } "Workspace is required"
        Assert-Equal @($case.State.Calls | Where-Object { $_.Operation -eq "InvokeProcess" }).Count 0 "Fresh missing workspace invoked CLI."
        Assert-True (-not $case.State.Tasks.ContainsKey($case.Identity.TaskName)) "Fresh missing workspace registered canonical task."
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Manifest)) "Fresh missing workspace wrote manifest."
    }
    finally { Remove-TestCase $case }
}

function Test-WrongCandidateRunIdentityFails {
    $case = New-TestCase -Label "run-identity"
    try {
        $case.State.WrongRunIdentity = $true
        Assert-Throws { Invoke-TestInstall $case } "specific candidate"
        Assert-True (-not $case.State.Tasks.ContainsKey($case.Identity.TaskName)) "Wrong candidate run identity installed canonical task."
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Manifest)) "Wrong candidate run identity wrote manifest."
    }
    finally { Remove-TestCase $case }
}

function Test-PersistentPrepareCommitAndRollback {
    $case = New-TestCase -Label "two-phase-commit"
    try {
        $parameters = @{
            SourceCli = $case.Source
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            Workspace = $case.Workspace
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            CandidateTimeoutSeconds = 5
            ProcessTimeoutSeconds = 5
        }
        $prepared = Prepare-MihoDailyUpdateTaskInstallV1 @parameters
        Assert-Equal $prepared.schema "miho-automation-prepare-result-v1" "Prepare result schema mismatch."
        Assert-True ([string]$prepared.transaction_token -cmatch '^[0-9a-f]{32}$') "Prepare did not return a random transaction token."
        Assert-Equal $prepared.phase "candidate-removed" "Prepare crossed the canonical commit boundary."
        Assert-True (-not $case.State.Tasks.ContainsKey($case.Identity.TaskName)) "Prepare installed the canonical task."
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Manifest)) "Prepare installed the ownership manifest."
        Assert-True (Test-Path -LiteralPath $case.Paths.Journal) "Prepare did not retain its journal."
        Assert-True (Test-Path -LiteralPath $prepared.retained_bootstrap_transaction) "Prepare did not retain bootstrap rollback evidence."
        Assert-Equal @($case.State.Tasks.Keys | Where-Object { $_ -like "*Candidate*" }).Count 0 "Prepare left its candidate task."

        $wrongToken = [guid]::NewGuid().ToString("N")
        Assert-Throws {
            Commit-MihoDailyUpdateTaskInstallV1 -TransactionToken $wrongToken -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5
        } "does not match"
        Assert-Throws { Invoke-TestInstall $case } "pending explicit Commit or Rollback"
        Assert-True (Test-Path -LiteralPath $case.Paths.Journal) "Wrong token or competing install consumed the prepared journal."

        $committed = Commit-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5
        Assert-True $committed.healthy "Two-phase commit did not report healthy."
        Assert-Equal $committed.health_attempt_id $prepared.health_attempt_id "Commit did not preserve exact candidate attempt evidence."
        Assert-True ($case.State.Tasks.ContainsKey($case.Identity.TaskName)) "Commit did not install canonical task."
        Assert-True (Test-Path -LiteralPath $case.Paths.Manifest) "Commit did not install manifest."
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Journal)) "Commit left journal."
        Assert-True (-not (Test-Path -LiteralPath $prepared.retained_bootstrap_transaction)) "Commit left bootstrap transaction evidence."
    }
    finally { Remove-TestCase $case }

    $case = New-TestCase -Label "two-phase-rollback"
    try {
        $null = Invoke-TestInstall $case
        $oldTask = Copy-TestSnapshot $case.State.Tasks[$case.Identity.TaskName]
        $oldManifest = [System.IO.File]::ReadAllBytes($case.Paths.Manifest)
        Set-TestSourceV2 $case
        $newGeneration = Get-TestCurrentGenerationPath $case
        $parameters = @{
            SourceCli = $case.Source
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            Workspace = $case.Workspace
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            CandidateTimeoutSeconds = 5
            ProcessTimeoutSeconds = 5
        }
        $prepared = Prepare-MihoDailyUpdateTaskInstallV1 @parameters
        Assert-True (Test-MihoTaskEquivalentExceptEnabledV1 -Snapshot $case.State.Tasks[$case.Identity.TaskName] -Expected $oldTask) "Prepare did not leave old canonical quiesced."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $oldManifest "Prepare changed old manifest."
        Assert-Throws {
            Rollback-MihoDailyUpdateTaskInstallV1 -TransactionToken ([guid]::NewGuid().ToString("N")) -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5
        } "does not match"
        $rolledBack = Rollback-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5
        Assert-True $rolledBack.rolled_back "Explicit rollback did not report rollback."
        Assert-True (-not $rolledBack.idempotent_replay) "First rollback was marked replay."
        Assert-True (Test-MihoSnapshotExactlyV1 -Snapshot $case.State.Tasks[$case.Identity.TaskName] -Expected $oldTask) "Rollback did not restore old XML/semantic SDDL."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $oldManifest "Rollback did not restore old manifest bytes."
        Assert-True (-not (Test-Path -LiteralPath $newGeneration)) "Rollback left new generation."
        Assert-Equal $rolledBack.retained_transaction "" "Rollback result retained obsolete Rust transaction evidence."
        Assert-True (-not (Test-Path -LiteralPath $prepared.retained_bootstrap_transaction)) "Rollback did not discard/finalize Rust transaction evidence."
        $bootstrapOperations = @($case.State.Calls |
            Where-Object { $_.Operation -eq "InvokeProcess" -and $_.Arguments.Count -ge 3 -and $_.Arguments[0] -eq "workspace" -and $_.Arguments[1] -eq "bootstrap-transaction" } |
            ForEach-Object { [string]$_.Arguments[2] })
        Assert-Equal (($bootstrapOperations | Select-Object -Last 3) -join ",") "rollback,discard,finalize" "Rollback did not durably rollback, discard, then finalize Rust evidence."
        Assert-True (Test-Path -LiteralPath $rolledBack.rollback_receipt) "Rollback did not leave a durable receipt."
        $rollbackReceipt = (Read-MihoJsonFileV1 -Path $rolledBack.rollback_receipt).Object
        Assert-Equal $rollbackReceipt.retained_bootstrap_transaction "" "Rollback receipt retained an obsolete transaction path."
        $replay = Rollback-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5
        Assert-True ($replay.rolled_back -and $replay.idempotent_replay) "Rollback was not idempotent."
        Assert-Equal $replay.retained_transaction "" "Rollback replay reintroduced obsolete transaction evidence."
    }
    finally { Remove-TestCase $case }
}

function Test-OrphanedAndExpiredPrepareAreRecoveredBeforeInstall {
    $case = New-TestCase -Label "orphaned-prepare"
    $coordinator = $null
    try {
        $null = Invoke-TestInstall $case
        Set-TestSourceV2 $case
        $processInfo = New-Object System.Diagnostics.ProcessStartInfo
        $processInfo.FileName = (Get-Process -Id $PID).Path
        $processInfo.Arguments = '-NoProfile -NonInteractive -Command "Start-Sleep -Seconds 30"'
        $processInfo.UseShellExecute = $false
        $processInfo.CreateNoWindow = $true
        $coordinator = [System.Diagnostics.Process]::Start($processInfo)
        $parameters = @{
            SourceCli = $case.Source
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            Workspace = $case.Workspace
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            CandidateTimeoutSeconds = 5
            ProcessTimeoutSeconds = 5
            CoordinatorPid = [int64]$coordinator.Id
        }
        $prepared = Prepare-MihoDailyUpdateTaskInstallV1 @parameters
        Assert-True (Test-Path -LiteralPath $prepared.retained_bootstrap_transaction) "External prepare did not retain transaction evidence."
        $coordinator.Kill()
        $coordinator.WaitForExit()
        $coordinator.Dispose()
        $coordinator = $null

        $callsBeforeRecovery = $case.State.Calls.Count
        $installed = Invoke-TestInstall $case
        Assert-True $installed.healthy "Installer did not recover an orphaned prepare and retry."
        $recoveryCalls = @($case.State.Calls | Select-Object -Skip $callsBeforeRecovery)
        Assert-True (@($recoveryCalls | Where-Object { $_.Operation -eq "RestoreTask" }).Count -ge 1) "Orphan recovery did not restore the old task before retry."
        Assert-True (@($recoveryCalls | Where-Object { $_.Operation -eq "InvokeProcess" -and $_.Arguments.Count -ge 3 -and $_.Arguments[0] -eq "workspace" -and $_.Arguments[1] -eq "bootstrap-transaction" -and $_.Arguments[2] -eq "rollback" }).Count -eq 1) "Orphan recovery did not perform one exact Rust rollback."
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Journal)) "Orphan recovery and retry left a journal."
    }
    finally {
        if ($null -ne $coordinator) {
            try { if (-not $coordinator.HasExited) { $coordinator.Kill(); $coordinator.WaitForExit() } } catch {}
            $coordinator.Dispose()
        }
        Remove-TestCase $case
    }

    $case = New-TestCase -Label "expired-prepare"
    try {
        $parameters = @{
            SourceCli = $case.Source
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            Workspace = $case.Workspace
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            CandidateTimeoutSeconds = 5
            ProcessTimeoutSeconds = 5
            PrepareValiditySeconds = 1
            CoordinatorPid = [int64]$PID
        }
        $null = Prepare-MihoDailyUpdateTaskInstallV1 @parameters
        Start-Sleep -Milliseconds 1200
        $installed = Invoke-TestInstall $case
        Assert-True $installed.healthy "Installer did not recover an expired prepare."
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Journal)) "Expired prepare recovery left a journal."
    }
    finally { Remove-TestCase $case }
}

function Test-PreparedCommitRevalidatesEvidence {
    foreach ($drift in @("bootstrap-verify", "wrong-attempt", "artifact-health")) {
        $case = New-TestCase -Label ("commit-drift-" + $drift)
        try {
            $null = Invoke-TestInstall $case
            $oldTask = Copy-TestSnapshot $case.State.Tasks[$case.Identity.TaskName]
            $oldManifest = [System.IO.File]::ReadAllBytes($case.Paths.Manifest)
            Set-TestSourceV2 $case
            $newGeneration = Get-TestCurrentGenerationPath $case
            $parameters = @{
                SourceCli = $case.Source
                ExpectedOwnerKind = $case.OwnerKind
                ExpectedOwnerInstanceId = $case.OwnerInstanceId
                Workspace = $case.Workspace
                AutomationRoot = $case.Automation
                Adapter = $case.Adapter
                CandidateTimeoutSeconds = 5
                ProcessTimeoutSeconds = 5
                CoordinatorPid = [int64]$PID
            }
            $prepared = Prepare-MihoDailyUpdateTaskInstallV1 @parameters
            $canonicalRegistrationsBefore = @($case.State.RegisteredSpecs | Where-Object { $_.TaskName -eq $case.Identity.TaskName }).Count
            switch ($drift) {
                "bootstrap-verify" { $case.State.BootstrapVerifyExit = 9 }
                "wrong-attempt" { $case.State.HealthAttempt = "foreign-prepared-attempt" }
                "artifact-health" { $case.State.HealthExit = 7 }
            }
            Assert-Throws {
                Commit-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5
            } "rolled back"
            Assert-Equal @($case.State.RegisteredSpecs | Where-Object { $_.TaskName -eq $case.Identity.TaskName }).Count $canonicalRegistrationsBefore "Commit drift registered a new canonical task: $drift"
            Assert-True (Test-MihoSnapshotExactlyV1 -Snapshot $case.State.Tasks[$case.Identity.TaskName] -Expected $oldTask) "Commit drift did not restore the old task: $drift"
            Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $oldManifest "Commit drift did not restore the old manifest: $drift"
            Assert-True (-not (Test-Path -LiteralPath $newGeneration)) "Commit drift left the new generation: $drift"
            Assert-True (-not (Test-Path -LiteralPath $case.Paths.Journal)) "Commit drift left the active journal: $drift"
            Assert-True (-not (Test-Path -LiteralPath $prepared.retained_bootstrap_transaction)) "Commit drift did not discard/finalize Rust evidence: $drift"
            $receipt = Join-Path $case.Automation ("rollback-receipt-" + $prepared.transaction_token + ".json")
            Assert-True (Test-Path -LiteralPath $receipt) "Commit drift did not leave a durable rollback receipt: $drift"
            Assert-Equal (Read-MihoJsonFileV1 -Path $receipt).Object.retained_bootstrap_transaction "" "Commit drift receipt retained obsolete Rust evidence: $drift"
        }
        finally { Remove-TestCase $case }
    }
}

function Test-StrictHealthAdversarialMatrix {
    $invalid = @(
        '{"schema_version":"miho-update-health-v1","healthy":true,"attempt_id":"a","checked_games":["hsr","zzz"],"unknown":1}',
        '{"schema_version":"miho-update-health-v1","healthy":true,"healthy":true,"attempt_id":"a","checked_games":["hsr","zzz"]}',
        '{"schema_version":"miho-update-health-v1","healthy":true,"attempt_id":"a","checked_games":[{"x":1,"x":2},"zzz"]}',
        '{"schema_version":"miho-update-health-v1","healthy":"true","attempt_id":"a","checked_games":["hsr","zzz"]}',
        '{"schema_version":"miho-update-health-v1","healthy":true,"attempt_id":"a"}',
        '{"schema_version":"miho-update-health-v1","healthy":true,"attempt_id":"a","checked_games":["hsr","hsr"]}'
    )
    foreach ($json in $invalid) {
        Assert-Throws { ConvertFrom-MihoHealthJsonV1 -Json $json }
    }
    Assert-Throws { ConvertFrom-MihoHealthJsonV1 -Json (' ' * ($script:MihoHealthMaximumCharactersV1 + 1)) } "size"

    foreach ($index in 0..($invalid.Count - 1)) {
        $case = New-TestCase -Label "health-adversary-$index"
        try {
            $case.State.HealthJsonAfterRun = $invalid[$index]
            Assert-Throws { Invoke-TestInstall $case }
            Assert-True (-not $case.State.Tasks.ContainsKey($case.Identity.TaskName)) "Invalid health installed canonical task."
            Assert-True (-not (Test-Path -LiteralPath $case.Paths.Manifest)) "Invalid health installed manifest."
            Assert-True (-not (Test-Path -LiteralPath $case.Paths.Journal)) "Invalid health left an unrecovered journal."
        }
        finally { Remove-TestCase $case }
    }
    $case = New-TestCase -Label "health-wrong-attempt"
    try {
        $case.State.DoNotAdvanceHealth = $true
        Assert-Throws { Invoke-TestInstall $case } "exact candidate attempt"
        Assert-True (-not $case.State.Tasks.ContainsKey($case.Identity.TaskName)) "Foreign health attempt installed canonical task."
    }
    finally { Remove-TestCase $case }
}

function Test-BoundedNativeProcessOutput {
    $hostExe = (Get-Process -Id $PID).Path
    $working = [System.IO.Path]::GetTempPath()
    $result = Invoke-MihoProcessCoreV1 -FilePath $hostExe -Arguments @(
        "-NoProfile", "-NonInteractive", "-Command",
        "[Console]::Out.Write(('o' * 60000)); [Console]::Error.Write(('e' * 60000))"
    ) -WorkingDirectory $working -TimeoutSeconds 20
    Assert-Equal $result.StdOut.Length 60000 "Bounded stdout was not drained concurrently."
    Assert-Equal $result.StdErr.Length 60000 "Bounded stderr was not drained concurrently."
    Assert-Throws {
        Invoke-MihoProcessCoreV1 -FilePath $hostExe -Arguments @(
            "-NoProfile", "-NonInteractive", "-Command",
            "[Console]::Out.Write(('x' * 70000)); Start-Sleep -Seconds 30"
        ) -WorkingDirectory $working -TimeoutSeconds 20
    } "stdout exceeded"
    Assert-Throws {
        Invoke-MihoProcessCoreV1 -FilePath $hostExe -Arguments @(
            "-NoProfile", "-NonInteractive", "-Command",
            "[Console]::Error.Write(('x' * 70000)); Start-Sleep -Seconds 30"
        ) -WorkingDirectory $working -TimeoutSeconds 20
    } "stderr exceeded"
}

function Test-TaskQuiesceRecognizesQueuedAndRejectsUnknown {
    $script:QuiesceState = "Queued"
    $script:QuiesceStopCount = 0
    function Get-ScheduledTask {
        param([string]$TaskName, [string]$TaskPath, $ErrorAction)
        return [pscustomobject]@{ State = $script:QuiesceState }
    }
    function Stop-ScheduledTask {
        param($InputObject, $ErrorAction)
        $script:QuiesceStopCount += 1
        $script:QuiesceState = "Ready"
    }
    try {
        Stop-MihoTaskCoreV1 -TaskName "queued-test" -TimeoutSeconds 1
        Assert-Equal $script:QuiesceStopCount 1 "Queued task was not stopped."
        $script:QuiesceState = "Unknown"
        Assert-Throws { Stop-MihoTaskCoreV1 -TaskName "unknown-test" -TimeoutSeconds 1 } "unknown"
    }
    finally {
        Remove-Item -LiteralPath Function:Get-ScheduledTask -Force
        Remove-Item -LiteralPath Function:Stop-ScheduledTask -Force
        Remove-Variable -Name QuiesceState -Scope Script -ErrorAction SilentlyContinue
        Remove-Variable -Name QuiesceStopCount -Scope Script -ErrorAction SilentlyContinue
    }
}

function Test-TaskRunDoesNotTreatQueuedStaleSuccessAsTerminal {
    $script:RunState = "Ready"
    $script:RunInfoCount = 0
    $script:RunStopCount = 0
    $script:RunBefore = [DateTime]::UtcNow.AddMinutes(-5)
    function Get-ScheduledTask {
        param([string]$TaskName, [string]$TaskPath, $ErrorAction)
        return [pscustomobject]@{ State = $script:RunState }
    }
    function Get-ScheduledTaskInfo {
        param($InputObject, $ErrorAction)
        $script:RunInfoCount += 1
        if ($script:RunInfoCount -eq 1) {
            return [pscustomobject]@{ LastRunTime = $script:RunBefore; LastTaskResult = 0 }
        }
        return [pscustomobject]@{ LastRunTime = $script:RunBefore.AddMinutes(1); LastTaskResult = 0 }
    }
    function Start-ScheduledTask {
        param($InputObject, $ErrorAction)
        $script:RunState = "Queued"
    }
    function Stop-ScheduledTask {
        param($InputObject, $ErrorAction)
        $script:RunStopCount += 1
        $script:RunState = "Ready"
    }
    try {
        Assert-Throws { Invoke-MihoTaskRunCoreV1 -TaskName "queued-stale-success" -TimeoutSeconds 1 } "timed out"
        Assert-True ($script:RunInfoCount -gt 1) "Queued run was not polled after LastRunTime advanced."
        Assert-Equal $script:RunStopCount 1 "Timed-out queued run was not quiesced."
    }
    finally {
        foreach ($name in @("Get-ScheduledTask", "Get-ScheduledTaskInfo", "Start-ScheduledTask", "Stop-ScheduledTask")) {
            Remove-Item -LiteralPath ("Function:" + $name) -Force -ErrorAction SilentlyContinue
        }
        foreach ($name in @("RunState", "RunInfoCount", "RunStopCount", "RunBefore")) {
            Remove-Variable -Name $name -Scope Script -ErrorAction SilentlyContinue
        }
    }
}

function Test-JournalCrashPhaseRecoveryMatrix {
    $case = New-TestCase -Label "crash-prepared"
    try {
        $hookState = [pscustomobject]@{ TargetPhase = "prepared"; FailCount = 1 }
        Assert-Throws { Invoke-TestInstall -Case $case -FileHooks (New-JournalPhaseCrashHooks $hookState) } "requires explicit repair"
        $record = Read-MihoJsonFileV1 -Path $case.Paths.Journal -MaximumBytes $script:MihoJournalMaximumBytesV1
        Assert-Equal $record.Object.phase "prepared" "Prepared crash did not leave exact phase."
        $newGeneration = [string]$record.Object.new_generation_path
        $stagedGeneration = [string]$record.Object.new_generation_staging_path
        Assert-True (-not [string]::IsNullOrEmpty($stagedGeneration)) "Prepared crash journal did not bind its staging generation."
        Assert-True (Test-Path -LiteralPath $stagedGeneration) "Prepared crash deleted journal-bound staging generation."
        Assert-True (-not (Test-Path -LiteralPath $newGeneration)) "Prepared crash published a generation before its durable journal."
        $repaired = Repair-MihoAutomationJournalV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5
        Assert-True ($repaired.recovered -and -not $repaired.committed) "Prepared crash did not roll back."
        Assert-True (-not (Test-Path -LiteralPath $newGeneration)) "Prepared recovery left new generation."
        Assert-True (-not (Test-Path -LiteralPath $stagedGeneration)) "Prepared recovery left staged generation."
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Journal)) "Prepared recovery left journal."
    }
    finally { Remove-TestCase $case }

    $phases = @(
        "old-quiesced", "bootstrap-begin-started", "bootstrap-begun", "candidate-registered",
        "candidate-ran", "candidate-healthy", "bootstrap-verified", "candidate-removed",
        "canonical-replaced", "committed"
    )
    foreach ($phase in $phases) {
        $case = New-TestCase -Label ("crash-" + $phase)
        try {
            $null = Invoke-TestInstall $case
            $oldTask = Copy-TestSnapshot $case.State.Tasks[$case.Identity.TaskName]
            $oldManifest = [System.IO.File]::ReadAllBytes($case.Paths.Manifest)
            Set-TestSourceV2 $case
            $newGeneration = Get-TestCurrentGenerationPath $case
            $case.State.FailRestoreCount = 1
            $hookState = [pscustomobject]@{ TargetPhase = $phase; FailCount = 1 }
            Assert-Throws { Invoke-TestInstall -Case $case -FileHooks (New-JournalPhaseCrashHooks $hookState) } "rollback is pending"
            $record = Read-MihoJsonFileV1 -Path $case.Paths.Journal -MaximumBytes $script:MihoJournalMaximumBytesV1
            $expectedPendingPhase = if ($phase -in @("bootstrap-begun", "candidate-registered", "candidate-ran", "candidate-healthy", "bootstrap-verified", "candidate-removed", "canonical-replaced", "committed")) { "bootstrap-discarded" } else { $phase }
            Assert-Equal $record.Object.phase $expectedPendingPhase "Crash recovery did not preserve its exact resumable phase."
            $case.State.FailRestoreCount = 0
            $repaired = Repair-MihoAutomationJournalV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5
            Assert-True ($repaired.recovered -and -not $repaired.committed) "Crash phase did not roll back: $phase"
            Assert-True (Test-MihoSnapshotExactlyV1 -Snapshot $case.State.Tasks[$case.Identity.TaskName] -Expected $oldTask) "Crash recovery did not restore old task: $phase"
            Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $oldManifest "Crash recovery did not restore old manifest: $phase"
            Assert-True (-not (Test-Path -LiteralPath $newGeneration)) "Crash recovery left new generation: $phase"
            Assert-True (-not (Test-Path -LiteralPath $case.Paths.Journal)) "Crash recovery left journal: $phase"
            Assert-Equal $repaired.retained_transaction "" "Crash recovery retained obsolete transaction evidence: $phase"
            $journalTransactionPath = [string]$record.Object.bootstrap_transaction_path
            if (-not [string]::IsNullOrEmpty($journalTransactionPath)) {
                Assert-True (-not (Test-Path -LiteralPath $journalTransactionPath)) "Crash recovery did not discard/finalize transaction evidence: $phase"
            }
        }
        finally { Remove-TestCase $case }
    }

    foreach ($phase in @("bootstrap-commit-started", "bootstrap-committed")) {
        $case = New-TestCase -Label ("crash-" + $phase)
        try {
            $hookState = [pscustomobject]@{ TargetPhase = $phase; FailCount = 1 }
            $result = Invoke-TestInstall -Case $case -FileHooks (New-JournalPhaseCrashHooks $hookState)
            Assert-True $result.healthy "Commit-boundary crash was not forward recovered: $phase"
            Assert-True ($result.warning -like "*exact committed state was recovered*") "Commit-boundary recovery was not disclosed: $phase"
            Assert-True ($case.State.Tasks.ContainsKey($case.Identity.TaskName)) "Commit-boundary recovery lost canonical task: $phase"
            Assert-True (Test-Path -LiteralPath $case.Paths.Manifest) "Commit-boundary recovery lost manifest: $phase"
            Assert-True (-not (Test-Path -LiteralPath $case.Paths.Journal)) "Commit-boundary recovery left journal: $phase"
        }
        finally { Remove-TestCase $case }
    }
}

function Test-GenerationStagingCrashRecovery {
    foreach ($stage in @("staging-created", "staging-copied", "generation-published")) {
        $case = New-TestCase -Label ("generation-crash-" + $stage)
        try {
            $expectedGeneration = Get-TestCurrentGenerationPath $case
            $hookState = [pscustomobject]@{ TargetStage = $stage; FailCount = 1 }
            Assert-Throws { Invoke-TestInstall -Case $case -FileHooks (New-GenerationCheckpointCrashHooks $hookState) } "simulated generation crash"
            Assert-True (-not (Test-Path -LiteralPath $case.Paths.Journal)) "Pre-journal generation crash wrote a transaction journal: $stage"
            Assert-True (-not $case.State.Tasks.ContainsKey($case.Identity.TaskName)) "Pre-journal generation crash installed a canonical task: $stage"
            Assert-True (-not (Test-Path -LiteralPath $case.Paths.Manifest)) "Pre-journal generation crash installed a manifest: $stage"
            $staging = @(Get-ChildItem -LiteralPath $case.Paths.Generations -Directory -Force | Where-Object { $_.Name -like ".staging-*" })
            Assert-True (-not (Test-Path -LiteralPath $expectedGeneration)) "Generation crash recovery left a published generation: $stage"
            Assert-Equal $staging.Count 0 "Generation crash recovery left its private staging directory: $stage"

            $foreignStaging = Join-Path $case.Paths.Generations (".staging-" + [guid]::NewGuid().ToString("N"))
            New-Item -ItemType Directory -Path $foreignStaging -ErrorAction Stop | Out-Null
            [System.IO.File]::WriteAllText((Join-Path $foreignStaging "unknown-sentinel.txt"), "preserve", (Get-MihoUtf8V1))

            $installed = Invoke-TestInstall $case
            Assert-True $installed.healthy "Retry after generation crash did not install successfully: $stage"
            $null = Assert-MihoExactGenerationDirectoryV1 -Directory $expectedGeneration -Sha256 (Get-MihoFileSha256V1 $case.Source) -Paths $case.Paths
            Assert-True (Test-Path -LiteralPath (Join-Path $foreignStaging "unknown-sentinel.txt")) "Retry deleted unknown staging contents: $stage"
        }
        finally { Remove-TestCase $case }
    }
}

function Test-JournalGenerationCreationEvidenceIsExact {
    $case = New-TestCase -Label "journal-generation-evidence"
    try {
        $hookState = [pscustomobject]@{ TargetPhase = "prepared"; FailCount = 1 }
        Assert-Throws { Invoke-TestInstall -Case $case -FileHooks (New-JournalPhaseCrashHooks $hookState) } "requires explicit repair"
        $record = Read-MihoJsonFileV1 -Path $case.Paths.Journal -MaximumBytes $script:MihoJournalMaximumBytesV1
        $journal = $record.Object
        $staging = [string]$journal.new_generation_staging_path
        $final = [string]$journal.new_generation_path
        $authority = (Read-MihoJsonFileV1 -Path $case.Paths.Authority -MaximumBytes $script:MihoOwnerStateMaximumBytesV1).Object
        $owner = [pscustomobject]@{
            Kind = [string]$authority.owner_kind
            InstanceId = [string]$authority.owner_instance_id
            Epoch = [string]$authority.owner_epoch
        }
        Assert-True ([bool]$journal.new_generation_created -and (Test-Path -LiteralPath $staging)) "Prepared fixture lacks a real journal-bound staging generation."

        foreach ($spoof in @(
            [pscustomobject]@{ Label = "empty"; Value = ""; Error = "creation and staging evidence disagree" },
            [pscustomobject]@{ Label = "null"; Value = $null; Error = "values are invalid" },
            [pscustomobject]@{ Label = "wrong-parent"; Value = (Join-Path $case.Base (".staging-" + [guid]::NewGuid().ToString("N"))); Error = "staging generation identity is invalid" },
            [pscustomobject]@{ Label = "wrong-name"; Value = (Join-Path $case.Paths.Generations "not-private-staging"); Error = "staging generation identity is invalid" }
        )) {
            $journal.new_generation_staging_path = $spoof.Value
            Assert-Throws {
                Assert-MihoJournalIdentityV1 -Journal $journal -Identity $case.Identity -Owner $owner -Paths $case.Paths
            } $spoof.Error
            Assert-True (Test-Path -LiteralPath (Join-Path $staging "miho.exe")) "Invalid created=true staging spoof deleted real evidence: $($spoof.Label)"
        }

        $journal.new_generation_staging_path = $staging
        $journal.new_generation_created = $false
        Assert-Throws {
            Assert-MihoJournalIdentityV1 -Journal $journal -Identity $case.Identity -Owner $owner -Paths $case.Paths
        } "creation and staging evidence disagree"
        Assert-True (Test-Path -LiteralPath (Join-Path $staging "miho.exe")) "created=false/nonempty staging spoof deleted real evidence."

        $journal.new_generation_staging_path = ""
        Assert-Throws {
            Assert-MihoJournalIdentityV1 -Journal $journal -Identity $case.Identity -Owner $owner -Paths $case.Paths
        } "not available"
        Assert-True (Test-Path -LiteralPath (Join-Path $staging "miho.exe")) "Missing reused final validation deleted staged evidence."

        Move-Item -LiteralPath $staging -Destination $final -ErrorAction Stop
        $null = Assert-MihoJournalIdentityV1 -Journal $journal -Identity $case.Identity -Owner $owner -Paths $case.Paths
        [System.IO.File]::WriteAllText((Join-Path $final "foreign.dll"), "foreign", (Get-MihoUtf8V1))
        Assert-Throws {
            Assert-MihoJournalIdentityV1 -Journal $journal -Identity $case.Identity -Owner $owner -Paths $case.Paths
        } "unrecorded or unsafe contents"
    }
    finally { Remove-TestCase $case }
}

function Test-PrepareHandoffParametersAreAtomic {
    $case = New-TestCase -Label "handoff-parameter-atomicity"
    try {
        $receiptPath = Join-Path $case.Base "prepare-handoff.json"
        $nonce = [guid]::NewGuid().ToString("N")
        $token = [guid]::NewGuid().ToString("N")
        $prepareParameters = @{
            SourceCli = $case.Source
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            Workspace = $case.Workspace
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            CandidateTimeoutSeconds = 5
            ProcessTimeoutSeconds = 5
        }

        Assert-Throws { Prepare-MihoDailyUpdateTaskInstallV1 @prepareParameters -ResultPath $receiptPath } "required together"
        Assert-Throws { Prepare-MihoDailyUpdateTaskInstallV1 @prepareParameters -CallerNonce $nonce } "required together"
        Assert-Throws {
            Prepare-MihoDailyUpdateTaskInstallV1 @prepareParameters -ResultPath $receiptPath -CallerNonce $nonce
        } "positive CoordinatorPid"

        $terminalParameters = @{
            TransactionToken = $token
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            ProcessTimeoutSeconds = 5
        }
        foreach ($operation in @("Commit", "Rollback")) {
            $invoke = if ($operation -eq "Commit") {
                { param($parameters, $path, $callerNonce, $pidValue) Commit-MihoDailyUpdateTaskInstallV1 @parameters -ResultPath $path -CallerNonce $callerNonce -CoordinatorPid $pidValue }
            }
            else {
                { param($parameters, $path, $callerNonce, $pidValue) Rollback-MihoDailyUpdateTaskInstallV1 @parameters -ResultPath $path -CallerNonce $callerNonce -CoordinatorPid $pidValue }
            }
            Assert-Throws { & $invoke $terminalParameters $receiptPath "" 0 } "required together"
            Assert-Throws { & $invoke $terminalParameters "" $nonce 0 } "required together"
            Assert-Throws { & $invoke $terminalParameters "" "" ([int64]$PID) } "required together"
            Assert-Throws { & $invoke $terminalParameters $receiptPath $nonce 0 } "required together"
        }
        Assert-True (-not (Test-Path -LiteralPath $receiptPath)) "Partial handoff parameters created a receipt."
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Journal)) "Partial handoff parameters created a switch journal."
    }
    finally { Remove-TestCase $case }
}

function Test-PrepareHandoffLifecycle {
    $case = New-TestCase -Label "handoff-commit"
    try {
        $receiptPath = Join-Path $case.Base "prepare handoff commit.json"
        $nonce = [guid]::NewGuid().ToString("N")
        $owner = New-MihoExpectedOwnerV1 -OwnerKind $case.OwnerKind -OwnerInstanceId $case.OwnerInstanceId
        $parameters = @{
            SourceCli = $case.Source
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            Workspace = $case.Workspace
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            CandidateTimeoutSeconds = 5
            ProcessTimeoutSeconds = 5
            CoordinatorPid = [int64]$PID
            ResultPath = $receiptPath
            CallerNonce = $nonce
        }
        $hookState = [pscustomobject]@{ TargetPurpose = "prepare-handoff-receipt"; FailCount = 1 }
        $parameters.FileHooks = New-AtomicWriteThenThrowHooks -HookState $hookState
        $prepared = Prepare-MihoDailyUpdateTaskInstallV1 @parameters
        Assert-Equal $hookState.FailCount 0 "Prepare handoff write-then-throw hook did not run."
        Assert-True (Test-Path -LiteralPath $receiptPath) "Prepare handoff receipt is missing after exact-byte write recovery."
        $handoff = Read-MihoPrepareHandoffReceiptV1 -Path $receiptPath -CallerNonce $nonce -ExpectedOwner $owner -CoordinatorPid ([int64]$PID)
        Assert-MihoObjectExactPropertyNamesV1 -Object $handoff.Object -ExpectedNames @(
            "schema", "caller_nonce", "transaction_token", "owner_kind", "owner_instance_id", "owner_epoch", "coordinator_pid", "phase",
            "generation", "exe_sha256", "workspace_sha256"
        ) -Label "Prepare handoff receipt"
        Assert-Equal $handoff.Object.schema "miho-automation-prepare-handoff-v1" "Prepare handoff schema mismatch."
        Assert-Equal $handoff.Object.transaction_token $prepared.transaction_token "Prepare handoff token mismatch."
        Assert-Equal $handoff.Object.owner_epoch $prepared.owner_epoch "Prepare handoff owner epoch mismatch."
        Assert-Equal ([int64]$handoff.Object.coordinator_pid) ([int64]$PID) "Prepare handoff coordinator PID mismatch."
        Assert-Equal $handoff.Object.phase "candidate-removed" "Prepare handoff crossed the commit boundary."
        Assert-Equal $handoff.Object.workspace_sha256 (Get-MihoSha256TextV1 -Text (Get-MihoNormalizedFullPathV1 -Path $case.Workspace)) "Prepare handoff workspace evidence mismatch."
        $journal = (Read-MihoJsonFileV1 -Path $case.Paths.Journal -MaximumBytes $script:MihoJournalMaximumBytesV1).Object
        Assert-Equal $handoff.Object.generation $journal.new_generation "Prepare handoff generation evidence mismatch."
        Assert-Equal $handoff.Object.exe_sha256 $journal.new_exe_sha256 "Prepare handoff executable evidence mismatch."

        $journalHash = Get-MihoFileSha256V1 -Path $case.Paths.Journal
        Assert-Throws {
            Read-MihoPrepareHandoffReceiptV1 -Path $receiptPath -CallerNonce ([guid]::NewGuid().ToString("N")) -ExpectedOwner $owner -CoordinatorPid ([int64]$PID)
        } "foreign or corrupt"
        $foreignOwner = New-MihoExpectedOwnerV1 -OwnerKind $case.OwnerKind -OwnerInstanceId ([guid]::NewGuid().ToString("D").ToLowerInvariant())
        Assert-Throws {
            Read-MihoPrepareHandoffReceiptV1 -Path $receiptPath -CallerNonce $nonce -ExpectedOwner $foreignOwner -CoordinatorPid ([int64]$PID)
        } "foreign or corrupt"
        Assert-Throws {
            Read-MihoPrepareHandoffReceiptV1 -Path $receiptPath -CallerNonce $nonce -ExpectedOwner $owner -CoordinatorPid ([int64]$PID + 100000)
        } "foreign or corrupt"
        Assert-Throws {
            Commit-MihoDailyUpdateTaskInstallV1 -TransactionToken ([guid]::NewGuid().ToString("N")) -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5 -ResultPath $receiptPath -CallerNonce $nonce -CoordinatorPid ([int64]$PID)
        } "transaction token disagrees"

        $receiptBytes = [System.IO.File]::ReadAllBytes($receiptPath)
        $staleReceipt = (Read-MihoJsonFileV1 -Path $receiptPath -MaximumBytes $script:MihoOwnerStateMaximumBytesV1).Object
        $staleReceipt.owner_epoch = [guid]::NewGuid().ToString("D").ToLowerInvariant()
        [System.IO.File]::WriteAllBytes($receiptPath, (ConvertTo-MihoJsonBytesV1 -Object $staleReceipt))
        try {
            Assert-Throws {
                Commit-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5 -ResultPath $receiptPath -CallerNonce $nonce -CoordinatorPid ([int64]$PID)
            } "owner epoch is stale"
        }
        finally { [System.IO.File]::WriteAllBytes($receiptPath, $receiptBytes) }
        Assert-Equal (Get-MihoFileSha256V1 -Path $case.Paths.Journal) $journalHash "Rejected handoff drift changed the prepared journal."

        $committed = Commit-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5 -ResultPath $receiptPath -CallerNonce $nonce -CoordinatorPid ([int64]$PID)
        Assert-True $committed.healthy "Handoff commit did not report healthy."
        $terminal = Read-MihoPrepareHandoffReceiptV1 -Path $receiptPath -CallerNonce $nonce -ExpectedOwner $owner -CoordinatorPid ([int64]$PID)
        Assert-Equal $terminal.Object.phase "committed" "Handoff commit did not durably publish committed."
        $replay = Commit-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5 -ResultPath $receiptPath -CallerNonce $nonce -CoordinatorPid ([int64]$PID)
        Assert-True ($replay.healthy -and $replay.warning -like "*Idempotent committed prepare handoff replay*") "Committed handoff replay was not idempotent."
        Assert-Throws {
            Rollback-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5 -ResultPath $receiptPath -CallerNonce $nonce -CoordinatorPid ([int64]$PID)
        } "already committed"
    }
    finally { Remove-TestCase $case }

    $case = New-TestCase -Label "handoff-rollback"
    try {
        $receiptPath = Join-Path $case.Base "prepare handoff rollback.json"
        $nonce = [guid]::NewGuid().ToString("N")
        $owner = New-MihoExpectedOwnerV1 -OwnerKind $case.OwnerKind -OwnerInstanceId $case.OwnerInstanceId
        $parameters = @{
            SourceCli = $case.Source
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            Workspace = $case.Workspace
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            CandidateTimeoutSeconds = 5
            ProcessTimeoutSeconds = 5
            CoordinatorPid = [int64]$PID
            ResultPath = $receiptPath
            CallerNonce = $nonce
        }
        $prepared = Prepare-MihoDailyUpdateTaskInstallV1 @parameters
        $rolledBack = Rollback-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5 -ResultPath $receiptPath -CallerNonce $nonce -CoordinatorPid ([int64]$PID)
        Assert-True ($rolledBack.rolled_back -and -not $rolledBack.idempotent_replay) "Handoff rollback did not complete."
        $terminal = Read-MihoPrepareHandoffReceiptV1 -Path $receiptPath -CallerNonce $nonce -ExpectedOwner $owner -CoordinatorPid ([int64]$PID)
        Assert-Equal $terminal.Object.phase "rolled-back" "Handoff rollback did not durably publish rolled-back."
        $replay = Rollback-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5 -ResultPath $receiptPath -CallerNonce $nonce -CoordinatorPid ([int64]$PID)
        Assert-True ($replay.rolled_back -and $replay.idempotent_replay) "Rolled-back handoff replay was not idempotent."
        Assert-Throws {
            Commit-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5 -ResultPath $receiptPath -CallerNonce $nonce -CoordinatorPid ([int64]$PID)
        } "already rolled back"
        Assert-True (Test-Path -LiteralPath $rolledBack.rollback_receipt) "Fresh rollback did not retain its exact terminal receipt before ReleaseClaim."
        $released = Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        Assert-True ($released.released -and -not $released.already_absent) "Fresh Prepare -> Rollback -> ReleaseClaim did not close the owner root."
        Assert-True (-not (Test-Path -LiteralPath $case.Automation)) "ReleaseClaim left the rolled-back fresh owner root."
        Assert-True (-not (Test-Path -LiteralPath $rolledBack.rollback_receipt)) "ReleaseClaim left the exact terminal rollback receipt."
    }
    finally { Remove-TestCase $case }

    $case = New-TestCase -Label "handoff-commit-recovery"
    try {
        $receiptPath = Join-Path $case.Base "prepare handoff commit recovery.json"
        $nonce = [guid]::NewGuid().ToString("N")
        $owner = New-MihoExpectedOwnerV1 -OwnerKind $case.OwnerKind -OwnerInstanceId $case.OwnerInstanceId
        $prepared = Prepare-MihoDailyUpdateTaskInstallV1 -SourceCli $case.Source -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -Workspace $case.Workspace -AutomationRoot $case.Automation -Adapter $case.Adapter -CandidateTimeoutSeconds 5 -ProcessTimeoutSeconds 5 -CoordinatorPid ([int64]$PID) -ResultPath $receiptPath -CallerNonce $nonce
        $null = Commit-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Journal)) "Commit recovery fixture still has a journal."
        Assert-Equal (Read-MihoPrepareHandoffReceiptV1 -Path $receiptPath -CallerNonce $nonce -ExpectedOwner $owner -CoordinatorPid ([int64]$PID)).Object.phase "candidate-removed" "Non-handoff commit unexpectedly changed external handoff evidence."
        $recovered = Commit-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5 -ResultPath $receiptPath -CallerNonce $nonce -CoordinatorPid ([int64]$PID)
        Assert-True ($recovered.healthy -and $recovered.warning -like "*Recovered committed state from exact prepare handoff evidence*") "Missing-journal committed state was not recovered from exact handoff evidence."
        Assert-Equal (Read-MihoPrepareHandoffReceiptV1 -Path $receiptPath -CallerNonce $nonce -ExpectedOwner $owner -CoordinatorPid ([int64]$PID)).Object.phase "committed" "Committed recovery did not update the handoff terminal phase."
    }
    finally { Remove-TestCase $case }

    $case = New-TestCase -Label "handoff-rollback-recovery"
    try {
        $receiptPath = Join-Path $case.Base "prepare handoff rollback recovery.json"
        $nonce = [guid]::NewGuid().ToString("N")
        $owner = New-MihoExpectedOwnerV1 -OwnerKind $case.OwnerKind -OwnerInstanceId $case.OwnerInstanceId
        $prepared = Prepare-MihoDailyUpdateTaskInstallV1 -SourceCli $case.Source -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -Workspace $case.Workspace -AutomationRoot $case.Automation -Adapter $case.Adapter -CandidateTimeoutSeconds 5 -ProcessTimeoutSeconds 5 -CoordinatorPid ([int64]$PID) -ResultPath $receiptPath -CallerNonce $nonce
        $first = Rollback-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5
        Assert-True ($first.rolled_back -and -not $first.idempotent_replay -and (Test-Path -LiteralPath $first.rollback_receipt)) "Rollback recovery fixture lacks its durable rollback receipt."
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Journal)) "Rollback recovery fixture still has a journal."
        Assert-Equal (Read-MihoPrepareHandoffReceiptV1 -Path $receiptPath -CallerNonce $nonce -ExpectedOwner $owner -CoordinatorPid ([int64]$PID)).Object.phase "candidate-removed" "Non-handoff rollback unexpectedly changed external handoff evidence."
        $recovered = Rollback-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5 -ResultPath $receiptPath -CallerNonce $nonce -CoordinatorPid ([int64]$PID)
        Assert-True ($recovered.rolled_back -and $recovered.idempotent_replay) "Missing-journal rollback receipt was not recovered through the handoff."
        Assert-Equal (Read-MihoPrepareHandoffReceiptV1 -Path $receiptPath -CallerNonce $nonce -ExpectedOwner $owner -CoordinatorPid ([int64]$PID)).Object.phase "rolled-back" "Rollback receipt recovery did not update the handoff terminal phase."
    }
    finally { Remove-TestCase $case }
}

function Test-RollbackMutationOrder {
    $case = New-TestCase -Label "rollback-order"
    try {
        $null = Invoke-TestInstall $case
        Set-TestSourceV2 $case
        $case.State.Calls.Clear()
        $hookState = [pscustomobject]@{ FailCount = 1; Calls = $case.State.Calls }
        Assert-Throws { Invoke-TestInstall -Case $case -FileHooks (New-OrderedFailureHooks $hookState) } "ordered manifest failure"
        $calls = @($case.State.Calls)
        $removeCanonical = -1
        $rollbackProcess = -1
        $manifestRestore = -1
        $restoreTask = -1
        for ($index = 0; $index -lt $calls.Count; $index++) {
            $call = $calls[$index]
            if ($removeCanonical -lt 0 -and $call.Operation -eq "RemoveTask" -and $call.Name -eq $case.Identity.TaskName) { $removeCanonical = $index }
            if ($rollbackProcess -lt 0 -and $call.Operation -eq "InvokeProcess" -and $call.Arguments.Count -ge 3 -and $call.Arguments[0] -eq "workspace" -and $call.Arguments[1] -eq "bootstrap-transaction" -and $call.Arguments[2] -eq "rollback") { $rollbackProcess = $index }
            if ($manifestRestore -lt 0 -and $call.Operation -eq "FileWrite" -and $call.Purpose -eq "manifest-restore") { $manifestRestore = $index }
            if ($restoreTask -lt 0 -and $call.Operation -eq "RestoreTask" -and $call.Name -eq $case.Identity.TaskName) { $restoreTask = $index }
        }
        Assert-True ($removeCanonical -ge 0 -and $rollbackProcess -gt $removeCanonical -and $manifestRestore -gt $rollbackProcess -and $restoreTask -gt $manifestRestore) "Rollback order was not new canonical -> Rust workspace -> old manifest -> old task last."
    }
    finally { Remove-TestCase $case }
}

function Invoke-TestDesktopProbeWithLease {
    param($Case, [string]$ExpectedOwnerKind, [string]$ExpectedOwnerInstanceId, [string]$ExpectedWorkspace = "")

    $coordinator = Enter-MihoAutomationCoordinatorV1 -AutomationRoot $Case.Automation
    $lease = $null
    try {
        $lease = [System.IO.File]::Open(
            $Case.Paths.Lock,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
        return Test-MihoDesktopAutomationBindingV1 `
            -AutomationRoot $Case.Automation `
            -ExpectedOwnerKind $ExpectedOwnerKind `
            -ExpectedOwnerInstanceId $ExpectedOwnerInstanceId `
            -ExpectedWorkspace $ExpectedWorkspace `
            -CallerHoldsSwitchLease $true `
            -Adapter $Case.Adapter
    }
    finally {
        if ($null -ne $lease) { $lease.Dispose() }
        Exit-MihoAutomationCoordinatorV1 -Coordinator $coordinator
    }
}

function Test-DesktopAutomationBindingProbeIsPathlessAndReadOnly {
    $base = Join-Path ([System.IO.Path]::GetTempPath()) ("miho-probe-absent-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $base -ErrorAction Stop | Out-Null
    $absentRoot = Join-Path $base "automation"
    $absentCoordinator = $null
    try {
        $absentCoordinator = Enter-MihoAutomationCoordinatorV1 -AutomationRoot $absentRoot
        $absent = Test-MihoDesktopAutomationBindingV1 -AutomationRoot $absentRoot -CallerHoldsSwitchLease $false
        Assert-Equal $absent.status "absent" "Desktop probe did not report an absent root."
        Assert-MihoObjectExactPropertyNamesV1 -Object $absent -ExpectedNames @(
            "schema", "status", "manifest_sha256", "exe_sha256", "authority_sha256", "unbound_sha256", "task_xml_sha256", "task_sddl_sha256"
        ) -Label "Desktop probe result"
        Assert-Equal (($absent.PSObject.Properties | Where-Object { $_.Name -like "*_sha256" } | ForEach-Object { [string]$_.Value }) -join "") "" "Absent probe exposed partial evidence."

        $identity = Get-MihoTaskIdentityV1 -OwnerSid (Get-MihoCurrentSidV1)
        $intentOwner = New-MihoExpectedOwnerV1 -OwnerKind "manual" -OwnerInstanceId ([guid]::NewGuid().ToString("D").ToLowerInvariant())
        $intent = New-MihoClaimIntentRecordV1 -ExpectedOwner $intentOwner -OwnerEpoch ([guid]::NewGuid().ToString("D").ToLowerInvariant()) -Identity $identity -AutomationRoot $absentRoot -RootWasAbsent $true
        Write-MihoAtomicBytesCoreV1 -Path ($absentRoot + ".claim-intent-v1.json") -Bytes (ConvertTo-MihoJsonBytesV1 -Object $intent)
        $pending = Test-MihoDesktopAutomationBindingV1 -AutomationRoot $absentRoot -ExpectedOwnerKind $intentOwner.Kind -ExpectedOwnerInstanceId $intentOwner.InstanceId -CallerHoldsSwitchLease $false
        Assert-Equal $pending.status "busy" "Root-absent valid owner intent was not busy."
        $foreign = Test-MihoDesktopAutomationBindingV1 -AutomationRoot $absentRoot -ExpectedOwnerKind "manual" -ExpectedOwnerInstanceId ([guid]::NewGuid().ToString("D").ToLowerInvariant()) -CallerHoldsSwitchLease $false
        Assert-Equal $foreign.status "conflict" "Root-absent foreign owner intent was not a conflict."
        [System.IO.File]::WriteAllText(($absentRoot + ".claim-intent-v1.json"), "{", (Get-MihoUtf8V1))
        $malformed = Test-MihoDesktopAutomationBindingV1 -AutomationRoot $absentRoot -CallerHoldsSwitchLease $false
        Assert-Equal $malformed.status "invalid" "Malformed root-absent owner intent was not invalid."
    }
    finally {
        Exit-MihoAutomationCoordinatorV1 -Coordinator $absentCoordinator
        Remove-Item -LiteralPath $base -Recurse -Force -ErrorAction SilentlyContinue
    }

    $case = New-TestCase -Label "desktop-probe-clean"
    try {
        $beforeNames = @((Get-ChildItem -LiteralPath $case.Automation -Force | Sort-Object Name | ForEach-Object { $_.Name }) -join "|")
        $authorityBefore = [System.IO.File]::ReadAllBytes($case.Paths.Authority)
        $unboundBefore = [System.IO.File]::ReadAllBytes($case.Paths.Unbound)
        $clean = Invoke-TestDesktopProbeWithLease -Case $case -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -ExpectedWorkspace $case.Workspace
        Assert-Equal $clean.status "clean-unbound" "Exact claimed root did not probe clean-unbound under a real Share.None lease."
        Assert-True ($clean.authority_sha256 -cmatch '^[0-9a-f]{64}$' -and $clean.unbound_sha256 -cmatch '^[0-9a-f]{64}$') "Clean-unbound probe omitted owner receipt hashes."
        Assert-Equal ($clean.manifest_sha256 + $clean.exe_sha256 + $clean.task_xml_sha256 + $clean.task_sddl_sha256) "" "Clean-unbound probe exposed active evidence."
        $conflict = Invoke-TestDesktopProbeWithLease -Case $case -ExpectedOwnerKind "manual" -ExpectedOwnerInstanceId ([guid]::NewGuid().ToString("D").ToLowerInvariant())
        Assert-Equal $conflict.status "conflict" "Clean-unbound owner mismatch was not a conflict."
        Assert-Equal (@((Get-ChildItem -LiteralPath $case.Automation -Force | Sort-Object Name | ForEach-Object { $_.Name }) -join "|")) $beforeNames "Desktop probe changed root entries."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Authority)) $authorityBefore "Desktop probe changed authority bytes."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Unbound)) $unboundBefore "Desktop probe changed unbound bytes."
        Assert-Throws { Test-MihoDesktopAutomationBindingV1 -AutomationRoot $case.Automation -CallerHoldsSwitchLease $false -Adapter $case.Adapter } "lease declaration"
    }
    finally { Remove-TestCase $case }

    $case = New-TestCase -Label "desktop-probe-active"
    try {
        $null = Invoke-TestInstall $case
        $active = Invoke-TestDesktopProbeWithLease -Case $case -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -ExpectedWorkspace $case.Workspace
        Assert-Equal $active.status "active" "Installed owner state did not probe active."
        foreach ($name in @("manifest_sha256", "exe_sha256", "authority_sha256", "task_xml_sha256", "task_sddl_sha256")) {
            Assert-True ([string]$active.$name -cmatch '^[0-9a-f]{64}$') "Active probe omitted evidence: $name"
        }
        Assert-Equal $active.unbound_sha256 "" "Active probe exposed an unbound receipt hash."
        $manifest = (Read-MihoJsonFileV1 -Path $case.Paths.Manifest).Object
        $sideLoad = Join-Path ([string]$manifest.generation_path) "side-load.dll"
        [System.IO.File]::WriteAllText($sideLoad, "foreign", (Get-MihoUtf8V1))
        Assert-Equal (Invoke-TestDesktopProbeWithLease -Case $case -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId).status "invalid" "Active probe accepted an extra generation file."
        Remove-Item -LiteralPath $sideLoad -Force
        $extraDirectory = Join-Path ([string]$manifest.generation_path) "side-load"
        New-Item -ItemType Directory -Path $extraDirectory -ErrorAction Stop | Out-Null
        Assert-Equal (Invoke-TestDesktopProbeWithLease -Case $case -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId).status "invalid" "Active probe accepted an extra generation directory."
        Remove-Item -LiteralPath $extraDirectory -Force
        $foreignFinal = Join-Path $case.Paths.Generations "foreign-final"
        New-Item -ItemType Directory -Path $foreignFinal -ErrorAction Stop | Out-Null
        Assert-Equal (Invoke-TestDesktopProbeWithLease -Case $case -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId).status "invalid" "Active probe accepted an extra final generation sibling."
        Remove-Item -LiteralPath $foreignFinal -Force
        $preservedStaging = Join-Path $case.Paths.Generations (".staging-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $preservedStaging -ErrorAction Stop | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $preservedStaging "unknown-sentinel.txt"), "preserve", (Get-MihoUtf8V1))
        Assert-Equal (Invoke-TestDesktopProbeWithLease -Case $case -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId).status "active" "Active probe rejected a preserved private staging sibling."
        Assert-True (Test-Path -LiteralPath (Join-Path $preservedStaging "unknown-sentinel.txt")) "Active probe changed a preserved private staging sibling."
        Remove-Item -LiteralPath $preservedStaging -Recurse -Force
        $stagingFile = Join-Path $case.Paths.Generations (".staging-" + [guid]::NewGuid().ToString("N"))
        [System.IO.File]::WriteAllText($stagingFile, "not-a-directory", (Get-MihoUtf8V1))
        Assert-Equal (Invoke-TestDesktopProbeWithLease -Case $case -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId).status "invalid" "Active probe accepted a staging-shaped file sibling."
        Remove-Item -LiteralPath $stagingFile -Force
        $wrongWorkspace = Join-Path $case.Base "other workspace"
        New-Item -ItemType Directory -Path $wrongWorkspace -ErrorAction Stop | Out-Null
        $workspaceConflict = Invoke-TestDesktopProbeWithLease -Case $case -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -ExpectedWorkspace $wrongWorkspace
        Assert-Equal $workspaceConflict.status "conflict" "Active workspace mismatch was not a conflict."
    }
    finally { Remove-TestCase $case }

    $case = New-TestCase -Label "desktop-probe-busy"
    try {
        $parameters = @{
            SourceCli = $case.Source
            ExpectedOwnerKind = $case.OwnerKind
            ExpectedOwnerInstanceId = $case.OwnerInstanceId
            Workspace = $case.Workspace
            AutomationRoot = $case.Automation
            Adapter = $case.Adapter
            CandidateTimeoutSeconds = 5
            ProcessTimeoutSeconds = 5
        }
        $prepared = Prepare-MihoDailyUpdateTaskInstallV1 @parameters
        $busy = Invoke-TestDesktopProbeWithLease -Case $case -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -ExpectedWorkspace $case.Workspace
        Assert-Equal $busy.status "busy" "Valid prepared switch journal did not probe busy."
        $null = Rollback-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5
    }
    finally { Remove-TestCase $case }
}

function Test-OwnerClaimAndReleaseSemantics {
    $case = New-TestCase -Label "owner-claim-release"
    try {
        Assert-True ($case.ClaimResult.claimed -and -not $case.ClaimResult.recovered) "Fresh owner claim did not complete normally."
        Assert-True ($case.ClaimResult.root_was_absent -and $case.ClaimResult.claim_created_new_owner) "Fresh owner claim omitted root-creation evidence."
        Assert-MihoObjectExactPropertyNamesV1 -Object $case.ClaimResult -ExpectedNames @(
            "schema", "owner_kind", "owner_instance_id", "owner_epoch", "claimed", "recovered", "root_was_absent", "claim_created_new_owner"
        ) -Label "Owner claim result"

        $rootNamesBefore = @((Get-ChildItem -LiteralPath $case.Automation -Force | Sort-Object Name | ForEach-Object { $_.Name }) -join "|")
        $authorityBefore = [System.IO.File]::ReadAllBytes($case.Paths.Authority)
        $unboundBefore = [System.IO.File]::ReadAllBytes($case.Paths.Unbound)
        $foreignOwnerId = [guid]::NewGuid().ToString("D").ToLowerInvariant()
        Assert-Throws {
            Claim-MihoAutomationOwnerV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $foreignOwnerId -AutomationRoot $case.Automation -Adapter $case.Adapter
        } "different owner instance"
        Assert-Throws {
            Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $foreignOwnerId -AutomationRoot $case.Automation -Adapter $case.Adapter
        } "foreign or inconsistent"
        Assert-Equal @((Get-ChildItem -LiteralPath $case.Automation -Force | Sort-Object Name | ForEach-Object { $_.Name }) -join "|") $rootNamesBefore "Foreign owner Claim/Release changed root entries."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Authority)) $authorityBefore "Foreign owner Claim/Release changed authority bytes."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Unbound)) $unboundBefore "Foreign owner Claim/Release changed unbound bytes."
        Assert-True (-not (Test-Path -LiteralPath ($case.Automation + ".claim-intent-v1.json"))) "Foreign owner Claim left an intent."
        Assert-True (-not (Test-Path -LiteralPath ($case.Automation + ".release-intent-v1.json"))) "Foreign owner Release left an intent."

        $reclaimed = Claim-MihoAutomationOwnerV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        Assert-True ($reclaimed.claimed -and -not $reclaimed.root_was_absent -and -not $reclaimed.claim_created_new_owner) "Existing same-owner Claim reported fresh-root evidence."
        $released = Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        Assert-MihoObjectExactPropertyNamesV1 -Object $released -ExpectedNames @(
            "schema", "owner_kind", "owner_instance_id", "released", "already_absent", "recovered"
        ) -Label "Owner release result"
        Assert-True ($released.released -and -not $released.already_absent -and -not $released.recovered) "Clean same-owner ReleaseClaim did not remove the claim."
        Assert-True (-not (Test-Path -LiteralPath $case.Automation)) "ReleaseClaim left the automation root."
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Lock)) "ReleaseClaim left the switch lock."
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Authority)) "ReleaseClaim left authority state."
        Assert-True (-not (Test-Path -LiteralPath $case.Paths.Unbound)) "ReleaseClaim left unbound state."
        Assert-True (-not (Test-Path -LiteralPath ($case.Automation + ".release-intent-v1.json"))) "ReleaseClaim left its durable intent."
        $replay = Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        Assert-True (-not $replay.released -and $replay.already_absent -and -not $replay.recovered) "ReleaseClaim absent replay was not idempotent."
    }
    finally { Remove-TestCase $case }
}

function Test-ActiveSameOwnerClaimIsUpgradeIdempotent {
    $case = New-TestCase -Label "active-claim-upgrade"
    try {
        $null = Invoke-TestInstall $case
        $authorityBefore = [System.IO.File]::ReadAllBytes($case.Paths.Authority)
        $manifestRecordBefore = Read-MihoJsonFileV1 -Path $case.Paths.Manifest -MaximumBytes $script:MihoManifestMaximumBytesV1
        $manifestBefore = $manifestRecordBefore.Bytes
        $oldExeSha256 = [string]$manifestRecordBefore.Object.exe_sha256
        $taskBefore = Copy-TestSnapshot $case.State.Tasks[$case.Identity.TaskName]
        $rootNamesBefore = @((Get-ChildItem -LiteralPath $case.Automation -Force | Sort-Object Name | ForEach-Object { $_.Name }) -join "|")
        $generationNamesBefore = @((Get-ChildItem -LiteralPath $case.Paths.Generations -Force | Sort-Object Name | ForEach-Object { $_.Name }) -join "|")
        $authority = (Read-MihoJsonFileV1 -Path $case.Paths.Authority -MaximumBytes $script:MihoOwnerStateMaximumBytesV1).Object

        $claimed = Claim-MihoAutomationOwnerV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        Assert-True ($claimed.claimed -and -not $claimed.recovered -and -not $claimed.root_was_absent -and -not $claimed.claim_created_new_owner) "Active same-owner Claim was not an idempotent success."
        Assert-Equal $claimed.owner_epoch $authority.owner_epoch "Active same-owner Claim rotated the owner epoch."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Authority)) $authorityBefore "Active same-owner Claim changed authority bytes."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $manifestBefore "Active same-owner Claim changed manifest bytes."
        Assert-True (Test-MihoSnapshotExactlyV1 -Snapshot $case.State.Tasks[$case.Identity.TaskName] -Expected $taskBefore) "Active same-owner Claim changed the canonical task."
        Assert-Equal @((Get-ChildItem -LiteralPath $case.Automation -Force | Sort-Object Name | ForEach-Object { $_.Name }) -join "|") $rootNamesBefore "Active same-owner Claim changed root membership."
        Assert-Equal @((Get-ChildItem -LiteralPath $case.Paths.Generations -Force | Sort-Object Name | ForEach-Object { $_.Name }) -join "|") $generationNamesBefore "Active same-owner Claim changed generation membership."

        $foreignOwnerId = [guid]::NewGuid().ToString("D").ToLowerInvariant()
        Assert-Throws {
            Claim-MihoAutomationOwnerV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $foreignOwnerId -AutomationRoot $case.Automation -Adapter $case.Adapter
        } "different owner instance"
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $manifestBefore "Foreign active Claim changed manifest bytes."

        $foreignGeneration = Join-Path $case.Paths.Generations "active-claim-foreign-final"
        New-Item -ItemType Directory -Path $foreignGeneration -ErrorAction Stop | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $foreignGeneration "sentinel.txt"), "preserve", (Get-MihoUtf8V1))
        Assert-Throws {
            Claim-MihoAutomationOwnerV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        } "Active or ambiguously bound"
        Assert-True (Test-Path -LiteralPath (Join-Path $foreignGeneration "sentinel.txt")) "Rejected drifted active Claim removed a foreign generation sibling."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $manifestBefore "Rejected drifted active Claim changed manifest bytes."
        Remove-Item -LiteralPath $foreignGeneration -Recurse -Force

        Set-TestSourceV2 $case
        $upgraded = Invoke-TestInstall $case
        Assert-True $upgraded.healthy "Upgrade after idempotent active Claim did not complete."
        Assert-True ((Read-MihoJsonFileV1 -Path $case.Paths.Manifest).Object.exe_sha256 -cne $oldExeSha256) "Upgrade did not replace active generation evidence."
    }
    finally { Remove-TestCase $case }
}

function Test-ReleaseClaimRefusesNonCleanState {
    $case = New-TestCase -Label "release-refuses-task"
    try {
        $null = Invoke-TestInstall $case
        $manifestBefore = [System.IO.File]::ReadAllBytes($case.Paths.Manifest)
        Assert-Throws {
            Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        } "existing canonical task"
        Assert-True ($case.State.Tasks.ContainsKey($case.Identity.TaskName)) "Rejected ReleaseClaim removed the active task."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $manifestBefore "Rejected ReleaseClaim changed the active manifest."
        Assert-True (-not (Test-Path -LiteralPath ($case.Automation + ".release-intent-v1.json"))) "Rejected active ReleaseClaim wrote an intent."
    }
    finally { Remove-TestCase $case }

    $case = New-TestCase -Label "release-refuses-generations"
    try {
        $foreignGeneration = Join-Path $case.Paths.Generations "foreign-generation"
        New-Item -ItemType Directory -Path $foreignGeneration -ErrorAction Stop | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $foreignGeneration "sentinel.txt"), "preserve", (Get-MihoUtf8V1))
        Assert-Throws {
            Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        } "requires empty generations"
        Assert-True (Test-Path -LiteralPath (Join-Path $foreignGeneration "sentinel.txt")) "Rejected ReleaseClaim changed a non-empty generations root."
        Assert-True (-not (Test-Path -LiteralPath ($case.Automation + ".release-intent-v1.json"))) "Rejected non-empty ReleaseClaim wrote an intent."
    }
    finally { Remove-TestCase $case }

    $case = New-TestCase -Label "release-refuses-manifest"
    try {
        $null = Invoke-TestInstall $case
        $case.State.Tasks.Remove($case.Identity.TaskName)
        $manifestBefore = [System.IO.File]::ReadAllBytes($case.Paths.Manifest)
        Assert-Throws {
            Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        } "non-clean root state"
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $manifestBefore "Rejected ReleaseClaim changed a manifest-only root."
        Assert-True (-not (Test-Path -LiteralPath ($case.Automation + ".release-intent-v1.json"))) "Rejected manifest ReleaseClaim wrote an intent."
    }
    finally { Remove-TestCase $case }

    $case = New-TestCase -Label "release-refuses-unknown"
    try {
        $unknown = Join-Path $case.Automation "unknown-sentinel.txt"
        [System.IO.File]::WriteAllText($unknown, "preserve", (Get-MihoUtf8V1))
        Assert-Throws {
            Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        } "non-clean root state"
        Assert-True (Test-Path -LiteralPath $unknown) "Rejected ReleaseClaim removed unknown root content."
        Assert-True (-not (Test-Path -LiteralPath ($case.Automation + ".release-intent-v1.json"))) "Rejected unknown-content ReleaseClaim wrote an intent."
    }
    finally { Remove-TestCase $case }
}

function Test-ReleaseClaimRollbackReceiptEvidenceIsExact {
    $case = New-TestCase -Label "release-rollback-receipt-exact"
    try {
        $prepared = Prepare-MihoDailyUpdateTaskInstallV1 -SourceCli $case.Source -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -Workspace $case.Workspace -AutomationRoot $case.Automation -Adapter $case.Adapter -CandidateTimeoutSeconds 5 -ProcessTimeoutSeconds 5 -CoordinatorPid ([int64]$PID)
        $rolledBack = Rollback-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5
        $receiptPath = [string]$rolledBack.rollback_receipt
        $receiptBytes = [System.IO.File]::ReadAllBytes($receiptPath)
        $authorityBytes = [System.IO.File]::ReadAllBytes($case.Paths.Authority)
        $unboundBytes = [System.IO.File]::ReadAllBytes($case.Paths.Unbound)
        $releaseIntentPath = $case.Automation + ".release-intent-v1.json"

        $wrongTokenPath = Join-Path $case.Automation ("rollback-receipt-" + [guid]::NewGuid().ToString("N") + ".json")
        Move-Item -LiteralPath $receiptPath -Destination $wrongTokenPath -ErrorAction Stop
        try {
            Assert-Throws {
                Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
            } "foreign or corrupt"
            Assert-True (Test-Path -LiteralPath $wrongTokenPath) "Token-drifted rollback receipt was deleted."
        }
        finally { Move-Item -LiteralPath $wrongTokenPath -Destination $receiptPath -ErrorAction Stop }

        $foreignOwnerReceipt = (Read-MihoJsonFileV1 -Path $receiptPath -MaximumBytes $script:MihoManifestMaximumBytesV1).Object
        $foreignOwnerReceipt.owner_instance_id = [guid]::NewGuid().ToString("D").ToLowerInvariant()
        [System.IO.File]::WriteAllBytes($receiptPath, (ConvertTo-MihoJsonBytesV1 -Object $foreignOwnerReceipt))
        try {
            Assert-Throws {
                Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
            } "foreign or corrupt"
        }
        finally { [System.IO.File]::WriteAllBytes($receiptPath, $receiptBytes) }

        $nonterminalReceipt = (Read-MihoJsonFileV1 -Path $receiptPath -MaximumBytes $script:MihoManifestMaximumBytesV1).Object
        $nonterminalReceipt.retained_bootstrap_transaction = Join-Path $case.Automation ("bootstrap-transaction-" + [guid]::NewGuid().ToString("N"))
        [System.IO.File]::WriteAllBytes($receiptPath, (ConvertTo-MihoJsonBytesV1 -Object $nonterminalReceipt))
        try {
            Assert-Throws {
                Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
            } "not terminal or exact"
        }
        finally { [System.IO.File]::WriteAllBytes($receiptPath, $receiptBytes) }

        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Authority)) $authorityBytes "Rejected rollback receipt drift changed authority."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Unbound)) $unboundBytes "Rejected rollback receipt drift changed unbound state."
        Assert-True (-not (Test-Path -LiteralPath $releaseIntentPath)) "Rejected rollback receipt drift wrote a release intent."

        $hookState = [pscustomobject]@{ TargetStage = "intent-written"; FailCount = 1 }
        Assert-Throws {
            Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -FileHooks (New-ReleaseCheckpointCrashHooks -HookState $hookState)
        } "simulated release crash after intent-written"
        $intent = Read-MihoReleaseIntentV1 -Path $releaseIntentPath -Identity $case.Identity -AutomationRoot $case.Automation
        Assert-Equal ([int64]$intent.Object.rollback_receipt_count) 1 "Release intent did not reserve one rollback receipt."
        Assert-Equal @($intent.Object.rollback_receipts).Count 1 "Release intent rollback receipt evidence count mismatch."
        Assert-Equal $intent.Object.rollback_receipts[0].transaction_token $prepared.transaction_token "Release intent did not bind the rollback token."
        Assert-Equal $intent.Object.rollback_receipts[0].receipt_sha256 (Get-MihoSha256BytesV1 -Bytes $receiptBytes) "Release intent did not bind the rollback receipt hash."

        [System.IO.File]::WriteAllBytes($receiptPath, ($receiptBytes + [byte]10))
        Assert-Throws {
            Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        } "drifted state"
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Authority)) $authorityBytes "Hash-drifted reserved receipt caused partial authority deletion."
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Unbound)) $unboundBytes "Hash-drifted reserved receipt caused partial unbound deletion."
        Assert-True (Test-Path -LiteralPath $receiptPath) "Hash-drifted reserved receipt was deleted."
        [System.IO.File]::WriteAllBytes($receiptPath, $receiptBytes)
        $released = Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        Assert-True ($released.released -and $released.recovered) "Exact rollback receipt release did not recover from its durable intent."
        Assert-True (-not (Test-Path -LiteralPath $case.Automation)) "Exact rollback receipt release left its root."
    }
    finally { Remove-TestCase $case }

    $case = New-TestCase -Label "release-rollback-receipt-checkpoint"
    try {
        $prepared = Prepare-MihoDailyUpdateTaskInstallV1 -SourceCli $case.Source -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -Workspace $case.Workspace -AutomationRoot $case.Automation -Adapter $case.Adapter -CandidateTimeoutSeconds 5 -ProcessTimeoutSeconds 5 -CoordinatorPid ([int64]$PID)
        $rolledBack = Rollback-MihoDailyUpdateTaskInstallV1 -TransactionToken $prepared.transaction_token -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -ProcessTimeoutSeconds 5
        $hookState = [pscustomobject]@{ TargetStage = "rollback-receipts-removed"; FailCount = 1 }
        Assert-Throws {
            Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -FileHooks (New-ReleaseCheckpointCrashHooks -HookState $hookState)
        } "simulated release crash after rollback-receipts-removed"
        Assert-True (-not (Test-Path -LiteralPath $rolledBack.rollback_receipt)) "Rollback receipt removal checkpoint left the exact receipt."
        Assert-True (Test-Path -LiteralPath ($case.Automation + ".release-intent-v1.json")) "Rollback receipt removal checkpoint lost its durable release intent."
        $released = Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        Assert-True ($released.released -and $released.recovered) "Rollback receipt removal checkpoint did not resume."
        Assert-True (-not (Test-Path -LiteralPath $case.Automation)) "Rollback receipt checkpoint recovery left the owner root."
    }
    finally { Remove-TestCase $case }
}

function Test-ReleaseClaimCheckpointRecovery {
    $stages = @(
        "intent-written",
        "release-authority-removed",
        "release-unbound-removed",
        "rollback-receipts-removed",
        "generations-removed",
        "switch-lock-removed",
        "root-removed",
        "intent-removed"
    )
    foreach ($stage in $stages) {
        $case = New-TestCase -Label ("release-crash-" + $stage)
        try {
            $hookState = [pscustomobject]@{ TargetStage = $stage; FailCount = 1 }
            Assert-Throws {
                Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -FileHooks (New-ReleaseCheckpointCrashHooks -HookState $hookState)
            } "simulated release crash after $stage"
            Assert-Equal $hookState.FailCount 0 "Release checkpoint was not reached: $stage"
            $recovered = Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
            if ($stage -eq "intent-removed") {
                Assert-True (-not $recovered.released -and $recovered.already_absent) "Post-intent-removal replay was not already absent."
            }
            else {
                Assert-True ($recovered.released -and -not $recovered.already_absent -and $recovered.recovered) "Release checkpoint did not resume from durable intent: $stage"
            }
            Assert-True (-not (Test-Path -LiteralPath $case.Automation)) "Recovered ReleaseClaim left its root: $stage"
            Assert-True (-not (Test-Path -LiteralPath $case.Paths.Lock)) "Recovered ReleaseClaim left its switch lock: $stage"
            Assert-True (-not (Test-Path -LiteralPath $case.Paths.Authority)) "Recovered ReleaseClaim left authority: $stage"
            Assert-True (-not (Test-Path -LiteralPath $case.Paths.Unbound)) "Recovered ReleaseClaim left unbound state: $stage"
            Assert-True (-not (Test-Path -LiteralPath ($case.Automation + ".release-intent-v1.json"))) "Recovered ReleaseClaim left its intent: $stage"
            $replay = Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
            Assert-True (-not $replay.released -and $replay.already_absent) "Recovered ReleaseClaim was not idempotent: $stage"
        }
        finally { Remove-TestCase $case }
    }
}

function Test-UninstallThenReleaseCompositeSemantics {
    $case = New-TestCase -Label "uninstall-release-fresh"
    try {
        $null = Invoke-TestInstall $case
        $uninstalled = Uninstall-MihoDailyUpdateTaskV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -QuiesceTimeoutSeconds 5
        Assert-True ($uninstalled.removed -and -not $uninstalled.already_absent -and $uninstalled.generation_removed) "Fresh exact uninstall did not remove active automation."
        $released = Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        Assert-True ($released.released -and -not $released.already_absent) "Fresh exact uninstall did not release its owner root."
        Assert-True (-not (Test-Path -LiteralPath $case.Automation)) "Fresh uninstall composite left an orphan owner root."

        $absent = Uninstall-MihoDailyUpdateTaskV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -QuiesceTimeoutSeconds 5
        Assert-True (-not $absent.removed -and $absent.already_absent -and -not $absent.generation_removed) "Truly absent uninstall replay was not idempotent."
        Assert-True (-not (Test-Path -LiteralPath $case.Automation)) "Absent uninstall replay recreated an empty automation root."
        $releaseReplay = Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        Assert-True (-not $releaseReplay.released -and $releaseReplay.already_absent) "Absent owner release replay was not idempotent."
    }
    finally { Remove-TestCase $case }

    $case = New-TestCase -Label "uninstall-release-foreign"
    try {
        $null = Invoke-TestInstall $case
        $manifestBefore = [System.IO.File]::ReadAllBytes($case.Paths.Manifest)
        $taskBefore = Copy-TestSnapshot $case.State.Tasks[$case.Identity.TaskName]
        $foreignOwnerId = [guid]::NewGuid().ToString("D").ToLowerInvariant()
        Assert-Throws {
            $null = Uninstall-MihoDailyUpdateTaskV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $foreignOwnerId -AutomationRoot $case.Automation -Adapter $case.Adapter -QuiesceTimeoutSeconds 5
            $null = Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $foreignOwnerId -AutomationRoot $case.Automation -Adapter $case.Adapter
        } "different owner"
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $manifestBefore "Foreign uninstall composite changed manifest bytes."
        Assert-True (Test-MihoSnapshotExactlyV1 -Snapshot $case.State.Tasks[$case.Identity.TaskName] -Expected $taskBefore) "Foreign uninstall composite changed the task."
        Assert-True (-not (Test-Path -LiteralPath ($case.Automation + ".release-intent-v1.json"))) "Foreign uninstall composite wrote a release intent."
    }
    finally { Remove-TestCase $case }

    $case = New-TestCase -Label "uninstall-release-drift"
    try {
        $null = Invoke-TestInstall $case
        $manifestBefore = [System.IO.File]::ReadAllBytes($case.Paths.Manifest)
        Set-TestTaskArguments -State $case.State -TaskName $case.Identity.TaskName -Arguments "foreign uninstall drift"
        $taskBefore = Copy-TestSnapshot $case.State.Tasks[$case.Identity.TaskName]
        Assert-Throws {
            $null = Uninstall-MihoDailyUpdateTaskV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter -QuiesceTimeoutSeconds 5
            $null = Release-MihoAutomationOwnerClaimV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        } "drifted"
        Assert-BytesEqual ([System.IO.File]::ReadAllBytes($case.Paths.Manifest)) $manifestBefore "Drifted uninstall composite changed manifest bytes."
        Assert-True (Test-MihoSnapshotExactlyV1 -Snapshot $case.State.Tasks[$case.Identity.TaskName] -Expected $taskBefore) "Drifted uninstall composite changed the task."
        Assert-True (-not (Test-Path -LiteralPath ($case.Automation + ".release-intent-v1.json"))) "Drifted uninstall composite wrote a release intent."
    }
    finally { Remove-TestCase $case }
}

function New-CompositeReclaimBarrierHooks {
    param(
        [Parameter(Mandatory = $true)]$Case,
        [Parameter(Mandatory = $true)]$HookState
    )

    $engine = if ($PSVersionTable.PSEdition -eq "Core") { Join-Path $PSHOME "pwsh.exe" } else { Join-Path $PSHOME "powershell.exe" }
    $claimWrapper = Join-Path $root "scripts\install_daily_update_task.ps1"
    $checkpoint = {
        param($stage)
        if ($stage -cne "before-release") { return }
        $HookState.Attempted = $true
        $claimAttempt = Invoke-TestPowerShellProcess -Engine $engine -Arguments @(
            "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $claimWrapper,
            "-Mode", "Claim", "-ExpectedOwnerKind", $Case.OwnerKind,
            "-ExpectedOwnerInstanceId", $Case.OwnerInstanceId, "-AutomationRoot", $Case.Automation
        )
        $HookState.ExitCode = $claimAttempt.ExitCode
        $HookState.Error = $claimAttempt.Output -join "`n"
        if ($claimAttempt.ExitCode -eq 0) {
            $HookState.UnexpectedClaim = $true
        }
        elseif ($HookState.Error -like "*Another Miho automation owner coordinator is active*") {
            $HookState.BlockedByCoordinator = $true
        }
    }.GetNewClosure()
    return @{ CompositeCheckpoint = $checkpoint }
}

function Test-UninstallReleaseCompositeRejectsStaleSameInstanceReclaim {
    $case = New-TestCase -Label "composite-stale-reclaim"
    try {
        $null = Invoke-TestInstall $case
        $epochE1 = [string](Read-MihoAuthorityV1 -Paths $case.Paths -Identity $case.Identity).Object.owner_epoch
        $hookState = [pscustomobject]@{
            Attempted = $false
            BlockedByCoordinator = $false
            UnexpectedClaim = $false
            ExitCode = 0
            Error = ""
        }
        $result = UninstallAndRelease-MihoDailyUpdateTaskV1 `
            -ExpectedOwnerKind $case.OwnerKind `
            -ExpectedOwnerInstanceId $case.OwnerInstanceId `
            -AutomationRoot $case.Automation `
            -Adapter $case.Adapter `
            -QuiesceTimeoutSeconds 5 `
            -FileHooks (New-CompositeReclaimBarrierHooks -Case $case -HookState $hookState)

        Assert-True $hookState.Attempted "Same-instance E2 Claim was not attempted at the deterministic uninstall-to-release barrier."
        Assert-True ($hookState.BlockedByCoordinator -and -not $hookState.UnexpectedClaim) "Same-instance E2 Claim crossed the composite sibling coordinator lease: $($hookState.Error)"
        Assert-True ($result.automation.removed -and $result.claim.released) "Composite E1 uninstall/release did not complete."
        Assert-True (-not (Test-Path -LiteralPath $case.Automation)) "Composite E1 release left its owner root."

        $claimE2 = Claim-MihoAutomationOwnerV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        Assert-True ($claimE2.claimed -and $claimE2.root_was_absent) "Same-instance E2 Claim did not proceed after the composite lease was released."
        Assert-True ([string]$claimE2.owner_epoch -cne $epochE1) "Same-instance E2 Claim reused stale E1 owner_epoch."
        $authorityE2 = Read-MihoAuthorityV1 -Paths $case.Paths -Identity $case.Identity
        Assert-Equal ([string]$authorityE2.Object.owner_epoch) ([string]$claimE2.owner_epoch) "Completed composite stale release deleted or replaced E2 authority."
    }
    finally { Remove-TestCase $case }

    $case = New-TestCase -Label "composite-crash-reservation"
    try {
        $null = Invoke-TestInstall $case
        $epochE1 = [string](Read-MihoAuthorityV1 -Paths $case.Paths -Identity $case.Identity).Object.owner_epoch
        $crashHooks = @{
            CompositeCheckpoint = {
                param($stage)
                if ($stage -ceq "before-release") { throw "simulated composite crash before release" }
            }
        }
        Assert-Throws {
            UninstallAndRelease-MihoDailyUpdateTaskV1 `
                -ExpectedOwnerKind $case.OwnerKind `
                -ExpectedOwnerInstanceId $case.OwnerInstanceId `
                -AutomationRoot $case.Automation `
                -Adapter $case.Adapter `
                -QuiesceTimeoutSeconds 5 `
                -FileHooks $crashHooks
        } "simulated composite crash before release"
        Assert-True (Test-Path -LiteralPath ($case.Automation + ".release-intent-v1.json")) "Post-uninstall crash lost the durable E1 release reservation."
        $unboundE1 = Read-MihoUnboundV1 -Paths $case.Paths -Identity $case.Identity
        Assert-Equal ([string]$unboundE1.Object.owner_epoch) $epochE1 "Post-uninstall crash did not retain E1 unbound evidence."

        $engine = if ($PSVersionTable.PSEdition -eq "Core") { Join-Path $PSHOME "pwsh.exe" } else { Join-Path $PSHOME "powershell.exe" }
        $claimWrapper = Join-Path $root "scripts\install_daily_update_task.ps1"
        $claimWhileCrashed = Invoke-TestPowerShellProcess -Engine $engine -Arguments @(
            "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $claimWrapper,
            "-Mode", "Claim", "-ExpectedOwnerKind", $case.OwnerKind,
            "-ExpectedOwnerInstanceId", $case.OwnerInstanceId, "-AutomationRoot", $case.Automation
        )
        Assert-True ($claimWhileCrashed.ExitCode -ne 0 -and ($claimWhileCrashed.Output -join "`n") -like "*pending explicit same-owner ReleaseClaim recovery*") "Durable E1 release reservation allowed same-instance E2 Claim after the composite process exited."
        Assert-Equal ([string](Read-MihoAuthorityV1 -Paths $case.Paths -Identity $case.Identity).Object.owner_epoch) $epochE1 "Rejected post-crash Claim rotated E1 authority."

        $recovered = UninstallAndRelease-MihoDailyUpdateTaskV1 `
            -ExpectedOwnerKind $case.OwnerKind `
            -ExpectedOwnerInstanceId $case.OwnerInstanceId `
            -AutomationRoot $case.Automation `
            -Adapter $case.Adapter `
            -QuiesceTimeoutSeconds 5
        Assert-True ($recovered.automation.already_absent -and $recovered.claim.released -and $recovered.claim.recovered) "Composite retry did not recover the durable E1 release reservation."
        Assert-True (-not (Test-Path -LiteralPath $case.Automation)) "Recovered E1 composite left its owner root."

        $claimE2 = Claim-MihoAutomationOwnerV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        Assert-True ([string]$claimE2.owner_epoch -cne $epochE1) "Post-recovery E2 Claim reused E1 owner_epoch."
        Assert-Equal ([string](Read-MihoAuthorityV1 -Paths $case.Paths -Identity $case.Identity).Object.owner_epoch) ([string]$claimE2.owner_epoch) "Completed stale E1 recovery deleted the later E2 authority."
    }
    finally { Remove-TestCase $case }

    $case = New-TestCase -Label "composite-pending-intent-reclaim"
    try {
        $epochE1 = [string](Read-MihoAuthorityV1 -Paths $case.Paths -Identity $case.Identity).Object.owner_epoch
        $crashState = [pscustomobject]@{ TargetStage = "intent-written"; FailCount = 1 }
        Assert-Throws {
            Release-MihoAutomationOwnerClaimV1 `
                -ExpectedOwnerKind $case.OwnerKind `
                -ExpectedOwnerInstanceId $case.OwnerInstanceId `
                -AutomationRoot $case.Automation `
                -Adapter $case.Adapter `
                -FileHooks (New-ReleaseCheckpointCrashHooks -HookState $crashState)
        } "simulated release crash after intent-written"
        Assert-True (Test-Path -LiteralPath ($case.Automation + ".release-intent-v1.json")) "Pending E1 release intent was not established."

        $hookState = [pscustomobject]@{
            Attempted = $false
            BlockedByCoordinator = $false
            UnexpectedClaim = $false
            ExitCode = 0
            Error = ""
        }
        $result = UninstallAndRelease-MihoDailyUpdateTaskV1 `
            -ExpectedOwnerKind $case.OwnerKind `
            -ExpectedOwnerInstanceId $case.OwnerInstanceId `
            -AutomationRoot $case.Automation `
            -Adapter $case.Adapter `
            -QuiesceTimeoutSeconds 5 `
            -FileHooks (New-CompositeReclaimBarrierHooks -Case $case -HookState $hookState)

        Assert-True $hookState.Attempted "Same-instance reclaim was not attempted at the deterministic pending-intent recovery barrier."
        Assert-True ($hookState.BlockedByCoordinator -and -not $hookState.UnexpectedClaim) "Same-instance reclaim crossed the pending-intent composite lease: $($hookState.Error)"
        Assert-True ($result.automation.already_absent -and -not $result.automation.removed) "Pending-intent composite did not preserve the existing uninstall receipt semantics."
        Assert-True ($result.claim.released -and $result.claim.recovered) "Pending E1 release intent was not recovered by the composite operation."
        Assert-True (-not (Test-Path -LiteralPath $case.Automation)) "Recovered E1 release left its owner root."

        $claimE2 = Claim-MihoAutomationOwnerV1 -ExpectedOwnerKind $case.OwnerKind -ExpectedOwnerInstanceId $case.OwnerInstanceId -AutomationRoot $case.Automation -Adapter $case.Adapter
        Assert-True ($claimE2.claimed -and $claimE2.root_was_absent) "Same-instance reclaim did not proceed after pending-intent recovery released the lease."
        Assert-True ([string]$claimE2.owner_epoch -cne $epochE1) "Pending-intent reclaim reused stale E1 owner_epoch."
        $authorityE2 = Read-MihoAuthorityV1 -Paths $case.Paths -Identity $case.Identity
        Assert-Equal ([string]$authorityE2.Object.owner_epoch) ([string]$claimE2.owner_epoch) "Pending-intent stale recovery deleted or replaced E2 authority."
    }
    finally { Remove-TestCase $case }
}

function Test-WrapperClaimAndUninstallOwnerRoundTrip {
    $base = Join-Path ([System.IO.Path]::GetTempPath()) ("miho-wrapper-roundtrip-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $base -ErrorAction Stop | Out-Null
    $automation = Join-Path $base "automation root"
    $ownerId = [guid]::NewGuid().ToString("D").ToLowerInvariant()
    $engine = if ($PSVersionTable.PSEdition -eq "Core") { Join-Path $PSHOME "pwsh.exe" } else { Join-Path $PSHOME "powershell.exe" }
    $wrapper = Join-Path $root "scripts\install_daily_update_task.ps1"
    $uninstallWrapper = Join-Path $root "scripts\uninstall_daily_update_task.ps1"
    try {
        $claimProcess = Invoke-TestPowerShellProcess -Engine $engine -Arguments @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $wrapper,
            "-Mode", "Claim", "-ExpectedOwnerKind", "manual", "-ExpectedOwnerInstanceId", $ownerId, "-AutomationRoot", $automation
        )
        Assert-Equal $claimProcess.ExitCode 0 "Claim wrapper process failed."
        $claim = ConvertFrom-MihoJsonTextV1 -Json ($claimProcess.Output -join "`n")
        Assert-Equal $claim.schema "miho-automation-owner-claim-result-v1" "Claim wrapper result schema mismatch."
        Assert-Equal $claim.owner_instance_id $ownerId "Claim wrapper did not round-trip owner identity."
        Assert-True ($claim.root_was_absent -and $claim.claim_created_new_owner) "Claim wrapper dropped fresh-root evidence flags."

        $paths = Get-MihoAutomationPathsV1 -AutomationRoot $automation
        $identity = Get-MihoTaskIdentityV1 -OwnerSid (Get-MihoCurrentSidV1)
        $authority = (Read-MihoAuthorityV1 -Paths $paths -Identity $identity).Object
        $receiptPath = Join-Path $base "wrapper handoff.json"
        $nonce = [guid]::NewGuid().ToString("N")
        $token = [guid]::NewGuid().ToString("N")
        $receiptOwner = [pscustomobject][ordered]@{
            Kind = [string]$authority.owner_kind
            InstanceId = [string]$authority.owner_instance_id
            Epoch = [string]$authority.owner_epoch
        }
        $receipt = New-MihoPrepareHandoffReceiptV1 -CallerNonce $nonce -TransactionToken $token -Owner $receiptOwner -CoordinatorPid ([int64]$PID) -Phase "candidate-removed" -Generation "wrapper-synthetic" -ExeSha256 ("a" * 64) -Workspace $base
        $null = Write-MihoPrepareHandoffReceiptV1 -Path $receiptPath -Receipt $receipt
        $mismatch = Invoke-TestPowerShellProcess -Engine $engine -Arguments @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $wrapper,
            "-Mode", "Commit", "-ExpectedOwnerKind", "manual", "-ExpectedOwnerInstanceId", $ownerId, "-AutomationRoot", $automation,
            "-TransactionToken", ([guid]::NewGuid().ToString("N")), "-ResultPath", $receiptPath, "-CallerNonce", $nonce, "-CoordinatorPid", ([string]$PID)
        )
        Assert-True ($mismatch.ExitCode -ne 0 -and ($mismatch.Output -join "`n") -like "*Explicit TransactionToken disagrees*") "Wrapper did not read the exact handoff PID/nonce/path tuple before token validation."

        $source = Join-Path $base "wrapper-source.exe"
        [System.IO.File]::WriteAllText($source, "fake", (Get-MihoUtf8V1))
        foreach ($mode in @("Prepare", "Commit", "Rollback")) {
            $common = @(
                "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $wrapper,
                "-Mode", $mode, "-ExpectedOwnerKind", "manual", "-ExpectedOwnerInstanceId", $ownerId, "-AutomationRoot", $automation
            )
            if ($mode -eq "Prepare") { $common += @("-SourceCli", $source) }
            foreach ($partial in @(
                @("-ResultPath", $receiptPath),
                @("-CallerNonce", $nonce),
                @("-CoordinatorPid", ([string]$PID)),
                @("-ResultPath", $receiptPath, "-CallerNonce", $nonce)
            )) {
                $invalid = Invoke-TestPowerShellProcess -Engine $engine -Arguments @($common + $partial)
                Assert-True ($invalid.ExitCode -ne 0 -and ($invalid.Output -join "`n") -like "*required together*") "Wrapper accepted partial handoff parameters for ${mode}: $($partial -join ' ')"
            }
        }

        $foreignUninstall = Invoke-TestPowerShellProcess -Engine $engine -Arguments @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $uninstallWrapper,
            "-ExpectedOwnerKind", "manual", "-ExpectedOwnerInstanceId", ([guid]::NewGuid().ToString("D").ToLowerInvariant()), "-AutomationRoot", $automation
        )
        Assert-True ($foreignUninstall.ExitCode -ne 0 -and (Test-Path -LiteralPath $paths.Authority)) "Uninstall wrapper released a foreign owner."

        $unknown = Join-Path $automation "wrapper-uninstall-drift.txt"
        [System.IO.File]::WriteAllText($unknown, "preserve", (Get-MihoUtf8V1))
        $driftedUninstall = Invoke-TestPowerShellProcess -Engine $engine -Arguments @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $uninstallWrapper,
            "-ExpectedOwnerKind", "manual", "-ExpectedOwnerInstanceId", $ownerId, "-AutomationRoot", $automation
        )
        Assert-True ($driftedUninstall.ExitCode -ne 0 -and (Test-Path -LiteralPath $unknown) -and (Test-Path -LiteralPath $paths.Authority)) "Uninstall wrapper released drifted owner state."
        Remove-Item -LiteralPath $unknown -Force

        $uninstallProcess = Invoke-TestPowerShellProcess -Engine $engine -Arguments @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $uninstallWrapper,
            "-ExpectedOwnerKind", "manual", "-ExpectedOwnerInstanceId", $ownerId, "-AutomationRoot", $automation
        )
        Assert-Equal $uninstallProcess.ExitCode 0 "Uninstall wrapper process failed."
        $uninstall = ConvertFrom-MihoJsonTextV1 -Json ($uninstallProcess.Output -join "`n")
        Assert-Equal $uninstall.schema "miho-automation-uninstall-release-result-v1" "Uninstall wrapper composite schema mismatch."
        Assert-MihoObjectExactPropertyNamesV1 -Object $uninstall -ExpectedNames @("schema", "owner_kind", "owner_instance_id", "automation", "claim") -Label "Uninstall wrapper composite"
        Assert-True ($uninstall.automation.already_absent -and -not $uninstall.automation.removed) "Uninstall wrapper did not recognize clean-unbound automation."
        Assert-True ($uninstall.claim.released -and -not $uninstall.claim.already_absent) "Uninstall wrapper did not release the clean-unbound owner."
        Assert-True (-not (Test-Path -LiteralPath $automation)) "Uninstall wrapper left the automation owner root."

        $uninstallReplayProcess = Invoke-TestPowerShellProcess -Engine $engine -Arguments @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $uninstallWrapper,
            "-ExpectedOwnerKind", "manual", "-ExpectedOwnerInstanceId", $ownerId, "-AutomationRoot", $automation
        )
        Assert-Equal $uninstallReplayProcess.ExitCode 0 "Uninstall wrapper absent replay process failed."
        $uninstallReplay = ConvertFrom-MihoJsonTextV1 -Json ($uninstallReplayProcess.Output -join "`n")
        Assert-True ($uninstallReplay.automation.already_absent -and $uninstallReplay.claim.already_absent) "Uninstall wrapper absent replay was not idempotent."
        Assert-True (-not (Test-Path -LiteralPath $automation)) "Uninstall wrapper absent replay recreated the automation root."

        $reclaimProcess = Invoke-TestPowerShellProcess -Engine $engine -Arguments @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $wrapper,
            "-Mode", "Claim", "-ExpectedOwnerKind", "manual", "-ExpectedOwnerInstanceId", $ownerId, "-AutomationRoot", $automation
        )
        Assert-Equal $reclaimProcess.ExitCode 0 "Claim wrapper could not recreate an explicitly released owner."

        $releaseProcess = Invoke-TestPowerShellProcess -Engine $engine -Arguments @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $wrapper,
            "-Mode", "ReleaseClaim", "-ExpectedOwnerKind", "manual", "-ExpectedOwnerInstanceId", $ownerId, "-AutomationRoot", $automation
        )
        Assert-Equal $releaseProcess.ExitCode 0 "ReleaseClaim wrapper process failed."
        $release = ConvertFrom-MihoJsonTextV1 -Json ($releaseProcess.Output -join "`n")
        Assert-True ($release.released -and -not $release.already_absent) "ReleaseClaim wrapper did not remove the clean-unbound owner root."
        Assert-True (-not (Test-Path -LiteralPath $automation)) "ReleaseClaim wrapper left the automation root."
        $releaseReplayProcess = Invoke-TestPowerShellProcess -Engine $engine -Arguments @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $wrapper,
            "-Mode", "ReleaseClaim", "-ExpectedOwnerKind", "manual", "-ExpectedOwnerInstanceId", $ownerId, "-AutomationRoot", $automation
        )
        Assert-Equal $releaseReplayProcess.ExitCode 0 "ReleaseClaim replay wrapper process failed."
        $releaseReplay = ConvertFrom-MihoJsonTextV1 -Json ($releaseReplayProcess.Output -join "`n")
        Assert-True (-not $releaseReplay.released -and $releaseReplay.already_absent) "ReleaseClaim wrapper replay was not already absent."
    }
    finally { Remove-Item -LiteralPath $base -Recurse -Force -ErrorAction SilentlyContinue }
}

Test-SuccessAndUnicodeQuoting
Test-OwnershipConflictPreservesState
Test-CaseSensitiveWorkspaceIdentityIsNotCollapsed
Test-CandidateFailurePreservesOld
Test-HealthFailurePreservesOld
Test-ManifestFailureRollsBackXmlSddlAndManifest
Test-UnfinishedJournalRecoversFirst
Test-UninstallSuccessIsNarrow
Test-UninstallDriftFailsClosed
Test-PasswordAndHighestAreRejected
Test-StrictLegacyRequiresExactExternalAuthorization
Test-LegacyNearMissIsPreserved
Test-SuccessfulUpgradeRetiresExactOldGeneration
Test-OmittedWorkspaceReusesOwnedWorkspaceBeforeFallback
Test-FreshInstallUsesEnvironmentWorkspaceBeforeDesktopFallback
Test-ExistingOwnedWorkspaceRejectsEnvironmentMismatchWithoutMutation
Test-FreshInstallUsesStrictDesktopSettingsWorkspace
Test-DesktopSettingsParserRejectsUnknownDuplicateAndInvalidBytes
Test-FreshOmittedWorkspaceWithoutFallbackFails
Test-WrongCandidateRunIdentityFails
Test-PersistentPrepareCommitAndRollback
Test-OrphanedAndExpiredPrepareAreRecoveredBeforeInstall
Test-PreparedCommitRevalidatesEvidence
Test-StrictHealthAdversarialMatrix
Test-BoundedNativeProcessOutput
Test-TaskQuiesceRecognizesQueuedAndRejectsUnknown
Test-TaskRunDoesNotTreatQueuedStaleSuccessAsTerminal
Test-JournalCrashPhaseRecoveryMatrix
Test-GenerationStagingCrashRecovery
Test-JournalGenerationCreationEvidenceIsExact
Test-PrepareHandoffParametersAreAtomic
Test-PrepareHandoffLifecycle
Test-RollbackMutationOrder
Test-DesktopAutomationBindingProbeIsPathlessAndReadOnly
Test-OwnerClaimAndReleaseSemantics
Test-ActiveSameOwnerClaimIsUpgradeIdempotent
Test-ReleaseClaimRefusesNonCleanState
Test-ReleaseClaimRollbackReceiptEvidenceIsExact
Test-ReleaseClaimCheckpointRecovery
Test-UninstallThenReleaseCompositeSemantics
Test-UninstallReleaseCompositeRejectsStaleSameInstanceReclaim
Test-WrapperClaimAndUninstallOwnerRoundTrip

$installWrapper = Get-Content -LiteralPath (Join-Path $root "scripts\install_daily_update_task.ps1") -Raw
Assert-True ($installWrapper -match '\$SourceCli') "Install wrapper does not require SourceCli."
Assert-True ($installWrapper -match '\$Workspace') "Install wrapper does not require Workspace."
Assert-True ($installWrapper -match '\$DesktopSettingsPath') "Install wrapper does not expose DesktopSettingsPath."
Assert-True ($installWrapper -match 'Select-MihoInstallWorkspaceOverrideV1') "Install wrapper does not use the tested workspace override selector."
Assert-True ($installWrapper -match '-EnvironmentWorkspace\s+\$env:MIHO_DATA_ROOT') "Install wrapper does not forward MIHO_DATA_ROOT as an explicit workspace override."
Assert-True ($installWrapper -match 'ValidateSet\("Claim", "ReleaseClaim", "Install", "Prepare", "Commit", "Rollback"\)') "Install wrapper does not expose Claim, ReleaseClaim, and the persistent two-phase modes."
Assert-True ($installWrapper -match '\$TransactionToken') "Install wrapper does not forward a transaction token."
Assert-True ($installWrapper -match '\$PrepareValiditySeconds' -and $installWrapper -match '\$CoordinatorPid' -and
    $installWrapper -match '\$ResultPath' -and $installWrapper -match '\$CallerNonce') "Install wrapper does not forward strict external prepare handoff evidence."
Assert-True ($installWrapper -match '\$parameters\.ResultPath\s*=\s*\$ResultPath' -and
    $installWrapper -match '\$parameters\.CallerNonce\s*=\s*\$CallerNonce' -and
    $installWrapper -match '\$parameters\.CoordinatorPid\s*=\s*\$CoordinatorPid') "Install wrapper does not forward the handoff receipt path, caller nonce, and coordinator PID together."
Assert-True ($installWrapper -match 'Prepare-MihoDailyUpdateTaskInstallV1') "Install wrapper does not call the prepare entrypoint."
Assert-True ($installWrapper -match 'Commit-MihoDailyUpdateTaskInstallV1') "Install wrapper does not call the commit entrypoint."
Assert-True ($installWrapper -match 'Rollback-MihoDailyUpdateTaskInstallV1') "Install wrapper does not call the rollback entrypoint."
Assert-True ($installWrapper -match '\$ExpectedLegacyXmlSha256' -and $installWrapper -match '\$ExpectedLegacySddlSha256') "Install wrapper does not forward exact legacy cleanup authorization."
Assert-True ($installWrapper -notmatch '\$Root\s*=') "Install wrapper still defaults to a source checkout root."
Assert-True ($installWrapper -notmatch '\$TaskName') "Install wrapper allows arbitrary stable task names."

$uninstallWrapperSource = Get-Content -LiteralPath (Join-Path $root "scripts\uninstall_daily_update_task.ps1") -Raw
Assert-True ($uninstallWrapperSource -match 'UninstallAndRelease-MihoDailyUpdateTaskV1') "Uninstall wrapper does not use the single-lease automation/owner composite."
$schedulerSource = Get-Content -LiteralPath (Join-Path $root "scripts\task_scheduler_v1.ps1") -Raw
Assert-True ($schedulerSource -match 'miho-automation-uninstall-release-result-v1' -and
    $schedulerSource -match 'automation\s*=\s*\$automation' -and
    $schedulerSource -match 'claim\s*=\s*\$claim') "Single-lease uninstall/release does not emit the exact composite receipt."

Write-Host "daily update task transaction regression: PASS"

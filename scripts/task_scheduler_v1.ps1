# Reusable Windows Task Scheduler transaction for the native Miho updater.
# Keep this file compatible with Windows PowerShell 5.1.

$script:MihoAutomationSchemaV1 = "miho-automation-owner-v1"
$script:MihoAutomationAuthoritySchemaV1 = "miho-automation-authority-v1"
$script:MihoAutomationUnboundSchemaV1 = "miho-automation-unbound-v1"
$script:MihoAutomationClaimIntentSchemaV1 = "miho-automation-owner-claim-intent-v1"
$script:MihoAutomationClaimJournalSchemaV1 = "miho-automation-owner-claim-journal-v1"
$script:MihoAutomationReleaseIntentSchemaV1 = "miho-automation-owner-release-intent-v1"
$script:MihoJournalSchemaV1 = "miho-automation-switch-journal-v1"
$script:MihoPrepareHandoffSchemaV1 = "miho-automation-prepare-handoff-v1"
$script:MihoActionFingerprintSchemaV1 = "miho-task-action-fingerprint-v1"
$script:MihoCanonicalTaskPrefixV1 = "MihoEndgameDailyUpdate"
$script:MihoLegacyTaskNameV1 = "MiHoYoEndgameDailyUpdate"
$script:MihoTaskPathV1 = "\"
$script:MihoDescriptionV1 = "Refresh HSR/ZZZ endgame exports with the native Miho update runner."
$script:MihoLegacyDescriptionV1 = "Refresh HSR/ZZZ endgame exports and rebuild ZZZ coverage/pull-value reports."
$script:MihoDesktopSettingsSchemaV1 = "miho-desktop-settings-v1"
$script:MihoDesktopSettingsMaximumBytesV1 = 65536
$script:MihoManifestMaximumBytesV1 = 65536
$script:MihoJournalMaximumBytesV1 = 3145728
$script:MihoOwnerStateMaximumBytesV1 = 16384
$script:MihoReleaseIntentMaximumBytesV1 = 1048576
$script:MihoReleaseReceiptMaximumCountV1 = 4096
$script:MihoTaskXmlMaximumBytesV1 = 1048576
$script:MihoTaskSddlMaximumBytesV1 = 65536
$script:MihoHealthMaximumCharactersV1 = 65536
$script:MihoHealthSchemaV1 = "miho-update-health-v1"
$script:MihoProcessOutputMaximumBytesV1 = 65536
$script:MihoProcessReadBufferBytesV1 = 4096
$script:MihoBootstrapTransactionReceiptSchemaV1 = "miho-release-bootstrap-transaction-receipt-v1"
$script:MihoBootstrapTransactionFileCountV1 = 12

function Get-MihoUtf8V1 {
    return (New-Object System.Text.UTF8Encoding($false))
}

function Get-MihoSha256BytesV1 {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)

    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($algorithm.ComputeHash($Bytes))).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $algorithm.Dispose()
    }
}

function Get-MihoSha256TextV1 {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)

    return Get-MihoSha256BytesV1 -Bytes ((Get-MihoUtf8V1).GetBytes($Text))
}

function Get-MihoSddlSemanticFingerprintV1 {
    param([Parameter(Mandatory = $true)][string]$Sddl)

    try {
        $descriptor = New-Object System.Security.AccessControl.RawSecurityDescriptor($Sddl)
    }
    catch {
        throw "Scheduled task SDDL is invalid."
    }
    $bytes = New-Object byte[] $descriptor.BinaryLength
    $descriptor.GetBinaryForm($bytes, 0)
    return Get-MihoSha256BytesV1 -Bytes $bytes
}

function Get-MihoFileSha256V1 {
    param([Parameter(Mandatory = $true)][string]$Path)

    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
}

function ConvertTo-MihoBase64V1 {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)

    return [System.Convert]::ToBase64String($Bytes)
}

function ConvertFrom-MihoBase64V1 {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)

    try {
        return [System.Convert]::FromBase64String($Text)
    }
    catch {
        throw "Automation journal contains invalid base64 data."
    }
}

function Test-MihoObjectPropertyV1 {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )

    return ($null -ne $Object -and $null -ne $Object.PSObject.Properties[$Name])
}

function Get-MihoRequiredPropertyV1 {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if (-not (Test-MihoObjectPropertyV1 -Object $Object -Name $Name)) {
        throw "Required automation field '$Name' is missing."
    }
    return $Object.$Name
}

function Assert-MihoObjectExactPropertyNamesV1 {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string[]]$ExpectedNames,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ($null -eq $Object -or $Object -isnot [pscustomobject]) {
        throw "$Label must be one JSON object."
    }
    $actual = @($Object.PSObject.Properties | ForEach-Object { [string]$_.Name })
    if ($actual.Count -ne $ExpectedNames.Count) {
        throw "$Label fields are invalid or unknown."
    }
    foreach ($expected in $ExpectedNames) {
        if (@($actual | Where-Object { [string]::Equals($_, $expected, [System.StringComparison]::Ordinal) }).Count -ne 1) {
            throw "$Label fields are invalid or unknown."
        }
    }
}

if ($null -eq ("MihoAutomation.NativeFileIdentityV1" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace MihoAutomation {
    public static class NativeFileIdentityV1 {
        [StructLayout(LayoutKind.Sequential)]
        private struct BY_HANDLE_FILE_INFORMATION {
            public uint FileAttributes;
            public System.Runtime.InteropServices.ComTypes.FILETIME CreationTime;
            public System.Runtime.InteropServices.ComTypes.FILETIME LastAccessTime;
            public System.Runtime.InteropServices.ComTypes.FILETIME LastWriteTime;
            public uint VolumeSerialNumber;
            public uint FileSizeHigh;
            public uint FileSizeLow;
            public uint NumberOfLinks;
            public uint FileIndexHigh;
            public uint FileIndexLow;
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern SafeFileHandle CreateFileW(
            string fileName,
            uint desiredAccess,
            uint shareMode,
            IntPtr securityAttributes,
            uint creationDisposition,
            uint flagsAndAttributes,
            IntPtr templateFile);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool GetFileInformationByHandle(
            SafeFileHandle handle,
            out BY_HANDLE_FILE_INFORMATION information);

        public static string Get(string path) {
            const uint FILE_READ_ATTRIBUTES = 0x80;
            const uint FILE_SHARE_READ = 0x1;
            const uint FILE_SHARE_WRITE = 0x2;
            const uint FILE_SHARE_DELETE = 0x4;
            const uint OPEN_EXISTING = 3;
            const uint FILE_FLAG_BACKUP_SEMANTICS = 0x02000000;
            const uint FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000;
            using (SafeFileHandle handle = CreateFileW(
                path,
                FILE_READ_ATTRIBUTES,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                IntPtr.Zero,
                OPEN_EXISTING,
                FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT,
                IntPtr.Zero)) {
                if (handle.IsInvalid) {
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                }
                BY_HANDLE_FILE_INFORMATION information;
                if (!GetFileInformationByHandle(handle, out information)) {
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                }
                return information.VolumeSerialNumber.ToString("x8") + ":" +
                    information.FileIndexHigh.ToString("x8") + information.FileIndexLow.ToString("x8");
            }
        }
    }
}
"@ -ErrorAction Stop
}

function Get-MihoNormalizedFullPathV1 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $full = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetPathRoot($full)
    if ($full.Length -eq $root.Length) { return $root }
    return $full.TrimEnd("\", "/")
}

function Get-MihoFileIdentityV1 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $full = Get-MihoNormalizedFullPathV1 -Path $Path
    return [MihoAutomation.NativeFileIdentityV1]::Get($full)
}

function Test-MihoPathEqualV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Left,
        [Parameter(Mandatory = $true)][string]$Right
    )

    $leftFull = Get-MihoNormalizedFullPathV1 -Path $Left
    $rightFull = Get-MihoNormalizedFullPathV1 -Path $Right
    if ([string]::Equals($leftFull, $rightFull, [System.StringComparison]::Ordinal)) {
        return $true
    }
    if ((Test-Path -LiteralPath $leftFull) -and (Test-Path -LiteralPath $rightFull)) {
        return (Get-MihoFileIdentityV1 -Path $leftFull) -ceq (Get-MihoFileIdentityV1 -Path $rightFull)
    }
    return $false
}

function Test-MihoPathBelowV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Parent
    )

    $fullPath = Get-MihoNormalizedFullPathV1 -Path $Path
    $fullParent = Get-MihoNormalizedFullPathV1 -Path $Parent
    if (Test-MihoPathEqualV1 -Left $fullPath -Right $fullParent) {
        return $false
    }
    if (-not (Test-Path -LiteralPath $fullParent)) {
        return $fullPath.StartsWith($fullParent + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::Ordinal)
    }
    $cursor = $fullPath
    while (-not (Test-Path -LiteralPath $cursor)) {
        $next = Split-Path -Parent $cursor
        if ([string]::IsNullOrWhiteSpace($next) -or [string]::Equals($next, $cursor, [System.StringComparison]::Ordinal)) {
            return $false
        }
        $cursor = Get-MihoNormalizedFullPathV1 -Path $next
    }
    while (-not [string]::IsNullOrWhiteSpace($cursor)) {
        if (Test-MihoPathEqualV1 -Left $cursor -Right $fullParent) {
            return $true
        }
        $next = Split-Path -Parent $cursor
        if ([string]::IsNullOrWhiteSpace($next) -or [string]::Equals($next, $cursor, [System.StringComparison]::Ordinal)) {
            break
        }
        $cursor = Get-MihoNormalizedFullPathV1 -Path $next
    }
    return $false
}

function Assert-MihoNoReparseChainV1 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $full = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetPathRoot($full)
    if ([string]::IsNullOrWhiteSpace($root)) {
        throw "Path has no filesystem root: $Path"
    }
    $relative = $full.Substring($root.Length)
    $current = $root
    foreach ($component in $relative.Split(@("\", "/"), [System.StringSplitOptions]::RemoveEmptyEntries)) {
        $current = Join-Path $current $component
        if (-not (Test-Path -LiteralPath $current)) {
            break
        }
        $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Automation path contains a reparse point: $current"
        }
    }
}

function Resolve-MihoExistingDirectoryV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $full = [System.IO.Path]::GetFullPath($Path)
    Assert-MihoNoReparseChainV1 -Path $full
    $item = Get-Item -LiteralPath $full -Force -ErrorAction Stop
    if (-not $item.PSIsContainer) {
        throw "$Label is not a directory: $full"
    }
    return $item.FullName
}

function Resolve-MihoExistingFileV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $full = [System.IO.Path]::GetFullPath($Path)
    Assert-MihoNoReparseChainV1 -Path $full
    $item = Get-Item -LiteralPath $full -Force -ErrorAction Stop
    if ($item.PSIsContainer) {
        throw "$Label is not a normal file: $full"
    }
    return $item.FullName
}

function Get-MihoTopLevelJsonKeysV1 {
    param([Parameter(Mandatory = $true)][string]$Json)

    # ConvertFrom-Json validates the full JSON syntax. This scanner preserves
    # duplicate top-level key evidence that Windows PowerShell 5.1 otherwise
    # discards while decoding an object.
    $keys = New-Object System.Collections.Generic.List[string]
    $depth = 0
    $inString = $false
    $escaped = $false
    $stringStart = -1
    $topLevelKey = $false
    $expectKey = $false
    for ($index = 0; $index -lt $Json.Length; $index++) {
        $character = $Json[$index]
        if ($inString) {
            if ($escaped) {
                $escaped = $false
            }
            elseif ($character -eq '\') {
                $escaped = $true
            }
            elseif ($character -eq '"') {
                $inString = $false
                if ($topLevelKey) {
                    $literal = $Json.Substring($stringStart, $index - $stringStart + 1)
                    try {
                        $decodedArray = ConvertFrom-Json -InputObject ("[" + $literal + "]") -ErrorAction Stop
                        $decoded = @($decodedArray)[0]
                    }
                    catch {
                        throw "Desktop settings contain an invalid property name."
                    }
                    if (-not ($decoded -is [string])) {
                        throw "Desktop settings contain an invalid property name."
                    }
                    $keys.Add([string]$decoded)
                    $expectKey = $false
                    $topLevelKey = $false
                }
            }
            continue
        }
        if ($character -eq '"') {
            $inString = $true
            $stringStart = $index
            $topLevelKey = ($depth -eq 1 -and $expectKey)
            continue
        }
        if ($character -eq '{' -or $character -eq '[') {
            $depth += 1
            if ($depth -eq 1 -and $character -eq '{') {
                $expectKey = $true
            }
            continue
        }
        if ($character -eq '}' -or $character -eq ']') {
            $depth -= 1
            continue
        }
        if ($depth -eq 1 -and $character -eq ',') {
            $expectKey = $true
        }
    }
    return @($keys)
}

function Assert-MihoJsonObjectKeysUniqueV1 {
    param([Parameter(Mandatory = $true)][string]$Json)

    # Windows PowerShell 5.1 ConvertFrom-Json silently keeps the last duplicate
    # key. Preserve that otherwise-lost evidence for every nested object before
    # any ownership field is trusted.
    $containers = New-Object System.Collections.ArrayList
    $inString = $false
    $escaped = $false
    $stringStart = -1
    $stringIsKey = $false
    for ($index = 0; $index -lt $Json.Length; $index++) {
        $character = $Json[$index]
        if ($inString) {
            if ($escaped) {
                $escaped = $false
            }
            elseif ($character -eq '\') {
                $escaped = $true
            }
            elseif ($character -eq '"') {
                $inString = $false
                if ($stringIsKey) {
                    $literal = $Json.Substring($stringStart, $index - $stringStart + 1)
                    try {
                        $decodedArray = ConvertFrom-Json -InputObject ("[" + $literal + "]") -ErrorAction Stop
                        $decoded = @($decodedArray)[0]
                    }
                    catch {
                        throw "Automation JSON contains an invalid property name."
                    }
                    if (-not ($decoded -is [string])) {
                        throw "Automation JSON contains an invalid property name."
                    }
                    $container = $containers[$containers.Count - 1]
                    if (-not $container.Keys.Add([string]$decoded)) {
                        throw "Automation JSON contains a duplicate property name."
                    }
                    $container.ExpectKey = $false
                }
                $stringIsKey = $false
            }
            continue
        }
        if ($character -eq '"') {
            $inString = $true
            $stringStart = $index
            $stringIsKey = ($containers.Count -gt 0 -and $containers[$containers.Count - 1].Kind -eq "object" -and $containers[$containers.Count - 1].ExpectKey)
            continue
        }
        if ($character -eq '{') {
            $container = [pscustomobject]@{
                Kind = "object"
                ExpectKey = $true
                Keys = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
            }
            $null = $containers.Add($container)
            continue
        }
        if ($character -eq '[') {
            $null = $containers.Add([pscustomobject]@{ Kind = "array"; ExpectKey = $false; Keys = $null })
            continue
        }
        if ($character -eq '}' -or $character -eq ']') {
            if ($containers.Count -gt 0) {
                $containers.RemoveAt($containers.Count - 1)
            }
            continue
        }
        if ($character -eq ',' -and $containers.Count -gt 0) {
            $container = $containers[$containers.Count - 1]
            if ($container.Kind -eq "object") {
                $container.ExpectKey = $true
            }
        }
    }
}

function Assert-MihoExactTopLevelJsonKeysV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Json,
        [Parameter(Mandatory = $true)][string[]]$ExpectedKeys
    )

    $actual = @(Get-MihoTopLevelJsonKeysV1 -Json $Json)
    if ($actual.Count -ne $ExpectedKeys.Count) {
        throw "Automation JSON fields are invalid, unknown, or duplicated."
    }
    foreach ($expected in $ExpectedKeys) {
        if (@($actual | Where-Object { [string]::Equals([string]$_, $expected, [System.StringComparison]::Ordinal) }).Count -ne 1) {
            throw "Automation JSON fields are invalid, unknown, or duplicated."
        }
    }
}

function Resolve-MihoDesktopWorkspaceV1 {
    param(
        [Parameter(Mandatory = $true)][string]$DefaultWorkspace,
        [Parameter(Mandatory = $true)][string]$SettingsPath
    )

    $default = Resolve-MihoExistingDirectoryV1 -Path $DefaultWorkspace -Label "Default workspace"
    $settingsFull = [System.IO.Path]::GetFullPath($SettingsPath)
    if (-not (Test-MihoPathBelowV1 -Path $settingsFull -Parent $default)) {
        throw "Desktop settings must be stored below the default workspace."
    }
    if (-not (Test-Path -LiteralPath $settingsFull)) {
        return $default
    }
    $settingsFile = Resolve-MihoExistingFileV1 -Path $settingsFull -Label "Desktop settings"
    $metadata = Get-Item -LiteralPath $settingsFile -Force -ErrorAction Stop
    if ($metadata.Length -gt $script:MihoDesktopSettingsMaximumBytesV1) {
        throw "Desktop settings exceed the supported size."
    }
    $bytes = [System.IO.File]::ReadAllBytes($settingsFile)
    if ($bytes.Length -gt $script:MihoDesktopSettingsMaximumBytesV1) {
        throw "Desktop settings exceed the supported size."
    }
    try {
        $utf8 = New-Object System.Text.UTF8Encoding($false, $true)
        $json = $utf8.GetString($bytes)
        $settings = $json | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw "Desktop settings are not strict UTF-8 JSON."
    }
    if ($null -eq $settings -or $settings -isnot [pscustomobject]) {
        throw "Desktop settings must be a JSON object."
    }
    $keys = @(Get-MihoTopLevelJsonKeysV1 -Json $json)
    $expectedKeys = @("schema_version", "selected_workspace", "revision")
    if ($keys.Count -ne $expectedKeys.Count) {
        throw "Desktop settings fields are invalid or duplicated."
    }
    foreach ($expectedKey in $expectedKeys) {
        $matches = @($keys | Where-Object { [string]::Equals([string]$_, $expectedKey, [System.StringComparison]::Ordinal) })
        if ($matches.Count -ne 1 -or $null -eq $settings.PSObject.Properties[$expectedKey]) {
            throw "Desktop settings fields are invalid or duplicated."
        }
    }
    foreach ($actualKey in $keys) {
        $known = @($expectedKeys | Where-Object { [string]::Equals([string]$_, [string]$actualKey, [System.StringComparison]::Ordinal) })
        if ($known.Count -ne 1) {
            throw "Desktop settings fields are invalid or duplicated."
        }
    }
    if ([string]$settings.schema_version -ne $script:MihoDesktopSettingsSchemaV1 -or
        -not ($settings.selected_workspace -is [string]) -or
        [string]::IsNullOrWhiteSpace([string]$settings.selected_workspace) -or
        -not ($settings.revision -is [int] -or $settings.revision -is [long]) -or
        [int64]$settings.revision -lt 1) {
        throw "Desktop settings values are invalid."
    }
    if (-not [System.IO.Path]::IsPathRooted([string]$settings.selected_workspace)) {
        throw "Desktop settings workspace must be absolute."
    }
    return Resolve-MihoExistingDirectoryV1 -Path ([string]$settings.selected_workspace) -Label "Selected workspace"
}

function Select-MihoInstallWorkspaceOverrideV1 {
    param(
        [string]$ExplicitWorkspace,
        [string]$EnvironmentWorkspace
    )

    if (-not [string]::IsNullOrWhiteSpace($ExplicitWorkspace)) {
        return $ExplicitWorkspace
    }
    if (-not [string]::IsNullOrWhiteSpace($EnvironmentWorkspace)) {
        return $EnvironmentWorkspace
    }
    return ""
}

function Resolve-MihoConfigRelativeV1 {
    param([Parameter(Mandatory = $true)][string]$Config)

    if ([string]::IsNullOrWhiteSpace($Config) -or [System.IO.Path]::IsPathRooted($Config)) {
        throw "Config must be a non-empty workspace-relative path."
    }
    $normalized = $Config.Replace("/", "\")
    $parts = $normalized.Split(@("\"), [System.StringSplitOptions]::RemoveEmptyEntries)
    if ($parts.Count -eq 0) {
        throw "Config must be a normal workspace-relative path."
    }
    foreach ($part in $parts) {
        if ($part -eq "." -or $part -eq "..") {
            throw "Config must not contain dot path components."
        }
    }
    return [string]::Join("\", $parts)
}

function Get-MihoCurrentSidV1 {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    if ($null -eq $identity -or $null -eq $identity.User) {
        throw "The current Windows SID is unavailable."
    }
    return $identity.User.Value
}

function Get-MihoTaskIdentityV1 {
    param([Parameter(Mandatory = $true)][string]$OwnerSid)

    $suffix = (Get-MihoSha256TextV1 -Text $OwnerSid).Substring(0, 16)
    return [pscustomobject][ordered]@{
        OwnerSid = $OwnerSid
        SidHash = $suffix
        TaskName = "$($script:MihoCanonicalTaskPrefixV1)-$suffix"
        TaskPath = $script:MihoTaskPathV1
    }
}

function Get-MihoAutomationPathsV1 {
    param([string]$AutomationRoot)

    if ([string]::IsNullOrWhiteSpace($AutomationRoot)) {
        if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
            throw "LOCALAPPDATA is unavailable."
        }
        $AutomationRoot = Join-Path $env:LOCALAPPDATA "com.miho.endgame.automation"
    }
    $root = [System.IO.Path]::GetFullPath($AutomationRoot)
    Assert-MihoNoReparseChainV1 -Path $root
    $rootCreated = $false
    if (-not (Test-Path -LiteralPath $root)) {
        New-Item -ItemType Directory -Path $root -Force -ErrorAction Stop | Out-Null
        $rootCreated = $true
    }
    $root = Resolve-MihoExistingDirectoryV1 -Path $root -Label "Automation root"
    $generations = Join-Path $root "generations"
    if (-not (Test-Path -LiteralPath $generations)) {
        if (-not $rootCreated) {
            throw "Existing automation root lacks its generations directory; explicit migration is required."
        }
        New-Item -ItemType Directory -Path $generations -ErrorAction Stop | Out-Null
    }
    $generations = Resolve-MihoExistingDirectoryV1 -Path $generations -Label "Automation generations root"
    return [pscustomobject][ordered]@{
        Root = $root
        Generations = $generations
        Manifest = Join-Path $root "automation-owner-v1.json"
        Journal = Join-Path $root "automation-switch-journal-v1.json"
        Authority = Join-Path $root "automation-authority-v1.json"
        Unbound = Join-Path $root "automation-unbound-v1.json"
        ClaimJournal = Join-Path $root "automation-owner-claim-journal-v1.json"
        ClaimIntent = $root + ".claim-intent-v1.json"
        Lock = Join-Path $root ".automation-switch-v1.lock"
        RootCreated = $rootCreated
    }
}

function Write-MihoAtomicBytesCoreV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][byte[]]$Bytes
    )

    $full = [System.IO.Path]::GetFullPath($Path)
    $parent = Split-Path -Parent $full
    Assert-MihoNoReparseChainV1 -Path $parent
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        throw "Atomic write parent is unavailable: $parent"
    }
    if (Test-Path -LiteralPath $full) {
        Assert-MihoNoReparseChainV1 -Path $full
        $existing = Get-Item -LiteralPath $full -Force -ErrorAction Stop
        if ($existing.PSIsContainer) {
            throw "Atomic write target is a directory: $full"
        }
    }
    $nonce = [guid]::NewGuid().ToString("N")
    $temporary = Join-Path $parent (".{0}.{1}.tmp" -f ([System.IO.Path]::GetFileName($full)), $nonce)
    $backup = Join-Path $parent (".{0}.{1}.bak" -f ([System.IO.Path]::GetFileName($full)), $nonce)
    try {
        $stream = New-Object System.IO.FileStream(
            $temporary,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None,
            4096,
            [System.IO.FileOptions]::WriteThrough
        )
        try {
            $stream.Write($Bytes, 0, $Bytes.Length)
            $stream.Flush($true)
        }
        finally {
            $stream.Dispose()
        }
        if (Test-Path -LiteralPath $full) {
            [System.IO.File]::Replace($temporary, $full, $backup, $true)
            Remove-Item -LiteralPath $backup -Force -ErrorAction Stop
        }
        else {
            [System.IO.File]::Move($temporary, $full)
        }
        $actual = [System.IO.File]::ReadAllBytes($full)
        if ((Get-MihoSha256BytesV1 -Bytes $actual) -ne (Get-MihoSha256BytesV1 -Bytes $Bytes)) {
            throw "Atomic write verification failed: $full"
        }
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        }
        if (Test-Path -LiteralPath $backup) {
            Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
        }
    }
}

function Write-MihoAtomicBytesV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][byte[]]$Bytes,
        [Parameter(Mandatory = $true)][string]$Purpose,
        [hashtable]$FileHooks
    )

    if ($null -ne $FileHooks -and $FileHooks.ContainsKey("WriteAtomicFile")) {
        & $FileHooks["WriteAtomicFile"] $Path $Bytes $Purpose
        return
    }
    Write-MihoAtomicBytesCoreV1 -Path $Path -Bytes $Bytes
}

function Remove-MihoFileV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Purpose,
        [hashtable]$FileHooks
    )

    if ($null -ne $FileHooks -and $FileHooks.ContainsKey("RemoveFile")) {
        & $FileHooks["RemoveFile"] $Path $Purpose
        return
    }
    if (Test-Path -LiteralPath $Path) {
        Assert-MihoNoReparseChainV1 -Path $Path
        Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
    }
}

function ConvertTo-MihoJsonBytesV1 {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [int]$Depth = 12
    )

    $json = ($Object | ConvertTo-Json -Depth $Depth -Compress) + [char]10
    return (Get-MihoUtf8V1).GetBytes($json)
}

function ConvertFrom-MihoJsonTextV1 {
    param([Parameter(Mandatory = $true)][string]$Json)

    # PowerShell 7.5+ converts ISO-8601-looking JSON strings to DateTime by
    # default, while Windows PowerShell 5.1 preserves them as strings.  The
    # automation formats require identical, type-strict parsing in both hosts.
    $command = Get-Command ConvertFrom-Json -ErrorAction Stop
    if ($command.Parameters.ContainsKey("DateKind")) {
        return ConvertFrom-Json -InputObject $Json -DateKind String -ErrorAction Stop
    }
    return ConvertFrom-Json -InputObject $Json -ErrorAction Stop
}

function Read-MihoJsonFileV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [int64]$MaximumBytes = $script:MihoManifestMaximumBytesV1,
        [string[]]$ExpectedKeys = @()
    )

    if ($MaximumBytes -le 0) {
        throw "Automation JSON maximum size is invalid."
    }
    Assert-MihoNoReparseChainV1 -Path $Path
    $metadata = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if ($metadata.PSIsContainer) {
        throw "Automation JSON path is not a normal file: $Path"
    }
    if ([int64]$metadata.Length -gt $MaximumBytes) {
        throw "Automation JSON exceeds its supported size: $Path"
    }
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ([int64]$bytes.Length -gt $MaximumBytes) {
        throw "Automation JSON exceeds its supported size: $Path"
    }
    try {
        $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
        $json = $strictUtf8.GetString($bytes)
        Assert-MihoJsonObjectKeysUniqueV1 -Json $json
        $object = ConvertFrom-MihoJsonTextV1 -Json $json
    }
    catch {
        throw "Automation JSON is not strict, unique-key UTF-8 JSON: $Path"
    }
    if ($null -eq $object -or $object -isnot [pscustomobject]) {
        throw "Automation JSON must contain one top-level object: $Path"
    }
    if ($ExpectedKeys.Count -gt 0) {
        Assert-MihoExactTopLevelJsonKeysV1 -Json $json -ExpectedKeys $ExpectedKeys
    }
    return [pscustomobject][ordered]@{
        Bytes = $bytes
        Object = $object
        Json = $json
    }
}

function Test-MihoCanonicalUuidV1 {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)

    try {
        $parsed = [guid]::Parse($Value)
        return $parsed.ToString("D") -ceq $Value
    }
    catch { return $false }
}

function New-MihoExpectedOwnerV1 {
    param(
        [Parameter(Mandatory = $true)][string]$OwnerKind,
        [Parameter(Mandatory = $true)][string]$OwnerInstanceId
    )

    if ($OwnerKind -cnotin @("installed", "portable", "manual") -or
        -not (Test-MihoCanonicalUuidV1 -Value $OwnerInstanceId)) {
        throw "Expected automation owner kind or instance id is invalid."
    }
    return [pscustomobject][ordered]@{
        Kind = $OwnerKind
        InstanceId = $OwnerInstanceId
    }
}

function Resolve-MihoPrepareHandoffPathV1 {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path) -or -not [System.IO.Path]::IsPathRooted($Path)) {
        throw "Prepare handoff receipt path must be absolute."
    }
    $full = [System.IO.Path]::GetFullPath($Path)
    $parent = Split-Path -Parent $full
    if ([string]::IsNullOrWhiteSpace($parent) -or -not (Test-Path -LiteralPath $parent -PathType Container)) {
        throw "Prepare handoff receipt parent is unavailable."
    }
    Assert-MihoNoReparseChainV1 -Path $parent
    if (Test-Path -LiteralPath $full) {
        Assert-MihoNoReparseChainV1 -Path $full
        $item = Get-Item -LiteralPath $full -Force -ErrorAction Stop
        if ($item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Prepare handoff receipt is not a normal file."
        }
    }
    return $full
}

function New-MihoPrepareHandoffReceiptV1 {
    param(
        [Parameter(Mandatory = $true)][string]$CallerNonce,
        [Parameter(Mandatory = $true)][string]$TransactionToken,
        [Parameter(Mandatory = $true)]$Owner,
        [Parameter(Mandatory = $true)][int64]$CoordinatorPid,
        [Parameter(Mandatory = $true)][string]$Phase,
        [Parameter(Mandatory = $true)][string]$Generation,
        [Parameter(Mandatory = $true)][string]$ExeSha256,
        [Parameter(Mandatory = $true)][string]$Workspace
    )

    if ($CallerNonce -cnotmatch '^[0-9a-f]{32}$' -or $TransactionToken -cnotmatch '^[0-9a-f]{32}$' -or
        -not (Test-MihoCanonicalUuidV1 -Value ([string]$Owner.Epoch)) -or $CoordinatorPid -le 0 -or
        $Phase -cne "candidate-removed" -or [string]::IsNullOrWhiteSpace($Generation) -or
        $ExeSha256 -cnotmatch '^[0-9a-f]{64}$' -or -not [System.IO.Path]::IsPathRooted($Workspace)) {
        throw "Prepare handoff receipt evidence is invalid."
    }
    return [pscustomobject][ordered]@{
        schema = $script:MihoPrepareHandoffSchemaV1
        caller_nonce = $CallerNonce
        transaction_token = $TransactionToken
        owner_kind = [string]$Owner.Kind
        owner_instance_id = [string]$Owner.InstanceId
        owner_epoch = [string]$Owner.Epoch
        coordinator_pid = $CoordinatorPid
        phase = $Phase
        generation = $Generation
        exe_sha256 = $ExeSha256
        workspace_sha256 = Get-MihoSha256TextV1 -Text (Get-MihoNormalizedFullPathV1 -Path $Workspace)
    }
}

function Write-MihoPrepareHandoffReceiptV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Receipt,
        [hashtable]$FileHooks
    )

    $full = Resolve-MihoPrepareHandoffPathV1 -Path $Path
    if (Test-Path -LiteralPath $full) { throw "Prepare handoff receipt path already exists." }
    $bytes = ConvertTo-MihoJsonBytesV1 -Object $Receipt
    try {
        Write-MihoAtomicBytesV1 -Path $full -Bytes $bytes -Purpose "prepare-handoff-receipt" -FileHooks $FileHooks
    }
    catch {
        if (-not (Test-Path -LiteralPath $full) -or
            (Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($full))) -cne (Get-MihoSha256BytesV1 -Bytes $bytes)) {
            throw
        }
    }
    if (-not (Test-Path -LiteralPath $full) -or
        (Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($full))) -cne (Get-MihoSha256BytesV1 -Bytes $bytes)) {
        throw "Prepare handoff receipt write could not be verified."
    }
    return [pscustomobject][ordered]@{ Path = $full; Bytes = $bytes; Object = $Receipt }
}

function Read-MihoPrepareHandoffReceiptV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$CallerNonce,
        [Parameter(Mandatory = $true)]$ExpectedOwner,
        [Parameter(Mandatory = $true)][int64]$CoordinatorPid
    )

    if ($CallerNonce -cnotmatch '^[0-9a-f]{32}$' -or $CoordinatorPid -le 0) {
        throw "Prepare handoff caller nonce or coordinator pid is invalid."
    }
    $full = Resolve-MihoPrepareHandoffPathV1 -Path $Path
    if (-not (Test-Path -LiteralPath $full)) { throw "Prepare handoff receipt is unavailable." }
    $record = Read-MihoJsonFileV1 -Path $full -MaximumBytes $script:MihoOwnerStateMaximumBytesV1 -ExpectedKeys @(
        "schema", "caller_nonce", "transaction_token", "owner_kind", "owner_instance_id", "owner_epoch", "coordinator_pid", "phase",
        "generation", "exe_sha256", "workspace_sha256"
    )
    $receipt = $record.Object
    foreach ($name in @("schema", "caller_nonce", "transaction_token", "owner_kind", "owner_instance_id", "owner_epoch", "phase", "generation", "exe_sha256", "workspace_sha256")) {
        if (-not ($receipt.$name -is [string])) { throw "Prepare handoff receipt values are invalid." }
    }
    if (-not ($receipt.coordinator_pid -is [int] -or $receipt.coordinator_pid -is [long]) -or
        [string]$receipt.schema -cne $script:MihoPrepareHandoffSchemaV1 -or
        [string]$receipt.caller_nonce -cne $CallerNonce -or [string]$receipt.transaction_token -cnotmatch '^[0-9a-f]{32}$' -or
        [string]$receipt.owner_kind -cne $ExpectedOwner.Kind -or [string]$receipt.owner_instance_id -cne $ExpectedOwner.InstanceId -or
        -not (Test-MihoCanonicalUuidV1 -Value ([string]$receipt.owner_epoch)) -or
        [int64]$receipt.coordinator_pid -ne $CoordinatorPid -or [string]$receipt.phase -cnotin @("candidate-removed", "committed", "rolled-back") -or
        [string]::IsNullOrWhiteSpace([string]$receipt.generation) -or [string]$receipt.exe_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        [string]$receipt.workspace_sha256 -cnotmatch '^[0-9a-f]{64}$') {
        throw "Prepare handoff receipt is foreign or corrupt."
    }
    return [pscustomobject][ordered]@{ Path = $full; Bytes = $record.Bytes; Object = $receipt }
}

function Set-MihoPrepareHandoffTerminalPhaseV1 {
    param(
        [Parameter(Mandatory = $true)]$Record,
        [Parameter(Mandatory = $true)][ValidateSet("committed", "rolled-back")][string]$Phase,
        [hashtable]$FileHooks
    )

    $current = [string]$Record.Object.phase
    if ($current -ceq $Phase) { return $Record }
    if ($current -cne "candidate-removed") {
        throw "Prepare handoff receipt is already terminal with a conflicting outcome."
    }
    $updated = [pscustomobject][ordered]@{
        schema = [string]$Record.Object.schema
        caller_nonce = [string]$Record.Object.caller_nonce
        transaction_token = [string]$Record.Object.transaction_token
        owner_kind = [string]$Record.Object.owner_kind
        owner_instance_id = [string]$Record.Object.owner_instance_id
        owner_epoch = [string]$Record.Object.owner_epoch
        coordinator_pid = [int64]$Record.Object.coordinator_pid
        phase = $Phase
        generation = [string]$Record.Object.generation
        exe_sha256 = [string]$Record.Object.exe_sha256
        workspace_sha256 = [string]$Record.Object.workspace_sha256
    }
    $bytes = ConvertTo-MihoJsonBytesV1 -Object $updated
    try { Write-MihoAtomicBytesV1 -Path $Record.Path -Bytes $bytes -Purpose "prepare-handoff-terminal" -FileHooks $FileHooks }
    catch {
        if (-not (Test-Path -LiteralPath $Record.Path) -or
            (Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($Record.Path))) -cne (Get-MihoSha256BytesV1 -Bytes $bytes)) { throw }
    }
    if ((Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($Record.Path))) -cne (Get-MihoSha256BytesV1 -Bytes $bytes)) {
        throw "Prepare handoff terminal phase write could not be verified."
    }
    return [pscustomobject][ordered]@{ Path = $Record.Path; Bytes = $bytes; Object = $updated }
}

function Test-MihoInstalledStateMatchesHandoffV1 {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)]$Owner,
        [Parameter(Mandatory = $true)]$Handoff
    )

    return ($Owner.Epoch -ceq [string]$Handoff.Object.owner_epoch -and
        [string]$State.Generation.Sha256 -ceq [string]$Handoff.Object.exe_sha256 -and
        [string]$State.Manifest.generation -ceq [string]$Handoff.Object.generation -and
        (Get-MihoSha256TextV1 -Text (Get-MihoNormalizedFullPathV1 -Path ([string]$State.Workspace))) -ceq [string]$Handoff.Object.workspace_sha256)
}

function New-MihoClaimIntentRecordV1 {
    param(
        [Parameter(Mandatory = $true)]$ExpectedOwner,
        [Parameter(Mandatory = $true)][string]$OwnerEpoch,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)][string]$AutomationRoot,
        [Parameter(Mandatory = $true)][bool]$RootWasAbsent
    )

    if (-not (Test-MihoCanonicalUuidV1 -Value $OwnerEpoch)) {
        throw "Automation owner claim intent epoch is invalid."
    }
    return [pscustomobject][ordered]@{
        schema = $script:MihoAutomationClaimIntentSchemaV1
        owner_kind = $ExpectedOwner.Kind
        owner_instance_id = $ExpectedOwner.InstanceId
        owner_epoch = $OwnerEpoch
        owner_sid = $Identity.OwnerSid
        task_name = $Identity.TaskName
        task_path = $Identity.TaskPath
        automation_root = [System.IO.Path]::GetFullPath($AutomationRoot)
        root_was_absent = $RootWasAbsent
    }
}

function Read-MihoClaimIntentV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)][string]$AutomationRoot
    )

    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $record = Read-MihoJsonFileV1 -Path $Path -MaximumBytes $script:MihoOwnerStateMaximumBytesV1 -ExpectedKeys @(
        "schema", "owner_kind", "owner_instance_id", "owner_epoch", "owner_sid",
        "task_name", "task_path", "automation_root", "root_was_absent"
    )
    $intent = $record.Object
    Assert-MihoOwnerTripletV1 -Object $intent -Label "Automation owner claim intent"
    foreach ($name in @("schema", "owner_sid", "task_name", "task_path", "automation_root")) {
        if (-not ($intent.$name -is [string])) { throw "Automation owner claim intent values are invalid." }
    }
    if (-not ($intent.root_was_absent -is [bool]) -or
        [string]$intent.schema -cne $script:MihoAutomationClaimIntentSchemaV1 -or
        -not [string]::Equals([string]$intent.owner_sid, $Identity.OwnerSid, [System.StringComparison]::OrdinalIgnoreCase) -or
        [string]$intent.task_name -cne $Identity.TaskName -or [string]$intent.task_path -cne $Identity.TaskPath -or
        -not (Test-MihoPathEqualV1 -Left ([string]$intent.automation_root) -Right $AutomationRoot)) {
        throw "Automation owner claim intent identity is foreign or corrupt."
    }
    return $record
}

function Get-MihoExpectedClaimIntentV1 {
    param(
        [Parameter(Mandatory = $true)]$Coordinator,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$ExpectedOwner
    )

    $record = Read-MihoClaimIntentV1 -Path $Coordinator.ClaimIntent -Identity $Identity -AutomationRoot $Coordinator.Root
    if ($null -eq $record) { return $null }
    if ([string]$record.Object.owner_kind -cne $ExpectedOwner.Kind -or
        [string]$record.Object.owner_instance_id -cne $ExpectedOwner.InstanceId) {
        throw "Automation owner claim intent is reserved by a different owner instance."
    }
    return $record
}

function Write-MihoClaimIntentV1 {
    param(
        [Parameter(Mandatory = $true)]$Coordinator,
        [Parameter(Mandatory = $true)][byte[]]$Bytes,
        [hashtable]$FileHooks
    )

    if (Test-Path -LiteralPath $Coordinator.ClaimIntent) {
        throw "Automation owner claim intent already exists and will not be overwritten."
    }
    Write-MihoAtomicBytesV1 -Path $Coordinator.ClaimIntent -Bytes $Bytes -Purpose "claim-intent" -FileHooks $FileHooks
    if (-not (Test-Path -LiteralPath $Coordinator.ClaimIntent) -or
        (Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($Coordinator.ClaimIntent))) -cne (Get-MihoSha256BytesV1 -Bytes $Bytes)) {
        throw "Automation owner claim intent write could not be verified."
    }
}

function Remove-MihoExpectedClaimIntentV1 {
    param(
        [Parameter(Mandatory = $true)]$Coordinator,
        [Parameter(Mandatory = $true)][byte[]]$ExpectedBytes,
        [hashtable]$FileHooks
    )

    if (-not (Test-Path -LiteralPath $Coordinator.ClaimIntent)) { return }
    $actual = [System.IO.File]::ReadAllBytes($Coordinator.ClaimIntent)
    if ((Get-MihoSha256BytesV1 -Bytes $actual) -cne (Get-MihoSha256BytesV1 -Bytes $ExpectedBytes)) {
        throw "Automation owner claim intent drifted; refusing mutation."
    }
    Remove-MihoFileV1 -Path $Coordinator.ClaimIntent -Purpose "claim-intent-cleanup" -FileHooks $FileHooks
}

function Assert-MihoNoPendingClaimIntentV1 {
    param(
        [Parameter(Mandatory = $true)]$Coordinator,
        [Parameter(Mandatory = $true)]$Identity
    )

    $record = Read-MihoClaimIntentV1 -Path $Coordinator.ClaimIntent -Identity $Identity -AutomationRoot $Coordinator.Root
    if ($null -ne $record) {
        throw "Automation owner claim is pending explicit same-owner Claim recovery."
    }
}

function New-MihoReleaseIntentRecordV1 {
    param(
        [Parameter(Mandatory = $true)]$Owner,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)][string]$AutomationRoot,
        [Parameter(Mandatory = $true)][string]$AuthoritySha256,
        [Parameter(Mandatory = $true)][string]$UnboundSha256,
        [object[]]$RollbackReceipts = @()
    )

    if ($AuthoritySha256 -cnotmatch '^[0-9a-f]{64}$' -or $UnboundSha256 -cnotmatch '^[0-9a-f]{64}$') {
        throw "Automation owner release hashes are invalid."
    }
    if (@($RollbackReceipts).Count -gt $script:MihoReleaseReceiptMaximumCountV1) {
        throw "Automation owner release has too many rollback receipts."
    }
    $seenTokens = @{}
    foreach ($receipt in @($RollbackReceipts)) {
        Assert-MihoObjectExactPropertyNamesV1 -Object $receipt -ExpectedNames @("transaction_token", "receipt_sha256") -Label "Automation owner release rollback receipt"
        if (-not ($receipt.transaction_token -is [string]) -or -not ($receipt.receipt_sha256 -is [string]) -or
            [string]$receipt.transaction_token -cnotmatch '^[0-9a-f]{32}$' -or
            [string]$receipt.receipt_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
            $seenTokens.ContainsKey([string]$receipt.transaction_token)) {
            throw "Automation owner release rollback receipt evidence is invalid."
        }
        $seenTokens[[string]$receipt.transaction_token] = $true
    }
    return [pscustomobject][ordered]@{
        schema = $script:MihoAutomationReleaseIntentSchemaV1
        owner_kind = $Owner.Kind
        owner_instance_id = $Owner.InstanceId
        owner_epoch = $Owner.Epoch
        owner_sid = $Identity.OwnerSid
        task_name = $Identity.TaskName
        task_path = $Identity.TaskPath
        automation_root = [System.IO.Path]::GetFullPath($AutomationRoot)
        authority_sha256 = $AuthoritySha256
        unbound_sha256 = $UnboundSha256
        rollback_receipt_count = @($RollbackReceipts).Count
        rollback_receipts = @($RollbackReceipts)
    }
}

function Read-MihoReleaseIntentV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)][string]$AutomationRoot
    )

    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $record = Read-MihoJsonFileV1 -Path $Path -MaximumBytes $script:MihoReleaseIntentMaximumBytesV1 -ExpectedKeys @(
        "schema", "owner_kind", "owner_instance_id", "owner_epoch", "owner_sid", "task_name", "task_path",
        "automation_root", "authority_sha256", "unbound_sha256", "rollback_receipt_count", "rollback_receipts"
    )
    $intent = $record.Object
    Assert-MihoOwnerTripletV1 -Object $intent -Label "Automation owner release intent"
    foreach ($name in @("schema", "owner_sid", "task_name", "task_path", "automation_root", "authority_sha256", "unbound_sha256")) {
        if (-not ($intent.$name -is [string])) { throw "Automation owner release intent values are invalid." }
    }
    if (-not ($intent.rollback_receipt_count -is [int] -or $intent.rollback_receipt_count -is [long]) -or
        [int64]$intent.rollback_receipt_count -lt 0 -or
        [int64]$intent.rollback_receipt_count -gt $script:MihoReleaseReceiptMaximumCountV1 -or
        [string]$intent.schema -cne $script:MihoAutomationReleaseIntentSchemaV1 -or
        -not [string]::Equals([string]$intent.owner_sid, $Identity.OwnerSid, [System.StringComparison]::OrdinalIgnoreCase) -or
        [string]$intent.task_name -cne $Identity.TaskName -or [string]$intent.task_path -cne $Identity.TaskPath -or
        -not (Test-MihoPathEqualV1 -Left ([string]$intent.automation_root) -Right $AutomationRoot) -or
        [string]$intent.authority_sha256 -cnotmatch '^[0-9a-f]{64}$' -or [string]$intent.unbound_sha256 -cnotmatch '^[0-9a-f]{64}$') {
        throw "Automation owner release intent is foreign or corrupt."
    }
    $rollbackReceipts = @($intent.rollback_receipts)
    if ($rollbackReceipts.Count -ne [int64]$intent.rollback_receipt_count) {
        throw "Automation owner release intent rollback receipt count is invalid."
    }
    $seenTokens = @{}
    foreach ($receipt in $rollbackReceipts) {
        Assert-MihoObjectExactPropertyNamesV1 -Object $receipt -ExpectedNames @("transaction_token", "receipt_sha256") -Label "Automation owner release intent rollback receipt"
        if (-not ($receipt.transaction_token -is [string]) -or -not ($receipt.receipt_sha256 -is [string]) -or
            [string]$receipt.transaction_token -cnotmatch '^[0-9a-f]{32}$' -or
            [string]$receipt.receipt_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
            $seenTokens.ContainsKey([string]$receipt.transaction_token)) {
            throw "Automation owner release intent rollback receipt evidence is invalid."
        }
        $seenTokens[[string]$receipt.transaction_token] = $true
    }
    return $record
}

function Write-MihoReleaseIntentV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][byte[]]$Bytes,
        [hashtable]$FileHooks
    )

    if ($Bytes.Length -gt $script:MihoReleaseIntentMaximumBytesV1) {
        throw "Automation owner release intent exceeds its supported size."
    }
    if (Test-Path -LiteralPath $Path) { throw "Automation owner release intent already exists." }
    try { Write-MihoAtomicBytesV1 -Path $Path -Bytes $Bytes -Purpose "release-intent" -FileHooks $FileHooks }
    catch {
        if (-not (Test-Path -LiteralPath $Path) -or
            (Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($Path))) -cne (Get-MihoSha256BytesV1 -Bytes $Bytes)) { throw }
    }
    if (-not (Test-Path -LiteralPath $Path) -or
        (Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($Path))) -cne (Get-MihoSha256BytesV1 -Bytes $Bytes)) {
        throw "Automation owner release intent write could not be verified."
    }
}

function Remove-MihoExpectedReleaseIntentV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][byte[]]$ExpectedBytes,
        [hashtable]$FileHooks
    )

    if (-not (Test-Path -LiteralPath $Path)) { return }
    if ((Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($Path))) -cne (Get-MihoSha256BytesV1 -Bytes $ExpectedBytes)) {
        throw "Automation owner release intent drifted."
    }
    try { Remove-MihoFileV1 -Path $Path -Purpose "release-intent-cleanup" -FileHooks $FileHooks }
    catch { if (Test-Path -LiteralPath $Path) { throw } }
}

function Assert-MihoNoPendingReleaseIntentV1 {
    param([Parameter(Mandatory = $true)]$Coordinator)

    if (Test-Path -LiteralPath $Coordinator.ReleaseIntent) {
        throw "Automation owner release is pending explicit same-owner ReleaseClaim recovery."
    }
}

function Assert-MihoOwnerTripletV1 {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Label
    )

    foreach ($name in @("owner_kind", "owner_instance_id", "owner_epoch")) {
        if (-not ($Object.$name -is [string])) { throw "$Label owner values are invalid." }
    }
    if ([string]$Object.owner_kind -cnotin @("installed", "portable", "manual") -or
        -not (Test-MihoCanonicalUuidV1 -Value ([string]$Object.owner_instance_id)) -or
        -not (Test-MihoCanonicalUuidV1 -Value ([string]$Object.owner_epoch))) {
        throw "$Label owner values are invalid."
    }
}

function New-MihoAuthorityRecordV1 {
    param(
        [Parameter(Mandatory = $true)]$ExpectedOwner,
        [Parameter(Mandatory = $true)][string]$OwnerEpoch,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Paths
    )

    if (-not (Test-MihoCanonicalUuidV1 -Value $OwnerEpoch)) { throw "Automation owner epoch is invalid." }
    return [pscustomobject][ordered]@{
        schema = $script:MihoAutomationAuthoritySchemaV1
        owner_kind = $ExpectedOwner.Kind
        owner_instance_id = $ExpectedOwner.InstanceId
        owner_epoch = $OwnerEpoch
        owner_sid = $Identity.OwnerSid
        task_name = $Identity.TaskName
        task_path = $Identity.TaskPath
        automation_root = $Paths.Root
    }
}

function New-MihoUnboundRecordV1 {
    param(
        [Parameter(Mandatory = $true)]$Owner,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Paths,
        [AllowEmptyString()][string]$PriorInstallId = "",
        [AllowEmptyString()][string]$PriorManifestSha256 = ""
    )

    if ((-not [string]::IsNullOrEmpty($PriorInstallId) -and -not (Test-MihoCanonicalUuidV1 -Value $PriorInstallId)) -or
        (-not [string]::IsNullOrEmpty($PriorManifestSha256) -and $PriorManifestSha256 -cnotmatch '^[0-9a-f]{64}$') -or
        ([string]::IsNullOrEmpty($PriorInstallId) -xor [string]::IsNullOrEmpty($PriorManifestSha256))) {
        throw "Automation unbound prior-state evidence is invalid."
    }
    return [pscustomobject][ordered]@{
        schema = $script:MihoAutomationUnboundSchemaV1
        owner_kind = $Owner.Kind
        owner_instance_id = $Owner.InstanceId
        owner_epoch = $Owner.Epoch
        owner_sid = $Identity.OwnerSid
        task_name = $Identity.TaskName
        task_path = $Identity.TaskPath
        automation_root = $Paths.Root
        prior_install_id = $PriorInstallId
        prior_manifest_sha256 = $PriorManifestSha256
    }
}

function Read-MihoAuthorityV1 {
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity
    )

    if (-not (Test-Path -LiteralPath $Paths.Authority)) { return $null }
    $record = Read-MihoJsonFileV1 -Path $Paths.Authority -MaximumBytes $script:MihoOwnerStateMaximumBytesV1 -ExpectedKeys @(
        "schema", "owner_kind", "owner_instance_id", "owner_epoch", "owner_sid",
        "task_name", "task_path", "automation_root"
    )
    $authority = $record.Object
    Assert-MihoOwnerTripletV1 -Object $authority -Label "Automation authority"
    foreach ($name in @("schema", "owner_sid", "task_name", "task_path", "automation_root")) {
        if (-not ($authority.$name -is [string])) { throw "Automation authority values are invalid." }
    }
    if ([string]$authority.schema -cne $script:MihoAutomationAuthoritySchemaV1 -or
        -not [string]::Equals([string]$authority.owner_sid, $Identity.OwnerSid, [System.StringComparison]::OrdinalIgnoreCase) -or
        [string]$authority.task_name -cne $Identity.TaskName -or [string]$authority.task_path -cne $Identity.TaskPath -or
        -not (Test-MihoPathEqualV1 -Left ([string]$authority.automation_root) -Right $Paths.Root)) {
        throw "Automation authority identity is foreign or corrupt."
    }
    return $record
}

function Read-MihoUnboundV1 {
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity
    )

    if (-not (Test-Path -LiteralPath $Paths.Unbound)) { return $null }
    $record = Read-MihoJsonFileV1 -Path $Paths.Unbound -MaximumBytes $script:MihoOwnerStateMaximumBytesV1 -ExpectedKeys @(
        "schema", "owner_kind", "owner_instance_id", "owner_epoch", "owner_sid",
        "task_name", "task_path", "automation_root", "prior_install_id", "prior_manifest_sha256"
    )
    $unbound = $record.Object
    Assert-MihoOwnerTripletV1 -Object $unbound -Label "Automation unbound receipt"
    foreach ($name in @("schema", "owner_sid", "task_name", "task_path", "automation_root", "prior_install_id", "prior_manifest_sha256")) {
        if (-not ($unbound.$name -is [string])) { throw "Automation unbound receipt values are invalid." }
    }
    if ([string]$unbound.schema -cne $script:MihoAutomationUnboundSchemaV1 -or
        -not [string]::Equals([string]$unbound.owner_sid, $Identity.OwnerSid, [System.StringComparison]::OrdinalIgnoreCase) -or
        [string]$unbound.task_name -cne $Identity.TaskName -or [string]$unbound.task_path -cne $Identity.TaskPath -or
        -not (Test-MihoPathEqualV1 -Left ([string]$unbound.automation_root) -Right $Paths.Root) -or
        (([string]::IsNullOrEmpty([string]$unbound.prior_install_id)) -xor ([string]::IsNullOrEmpty([string]$unbound.prior_manifest_sha256))) -or
        (-not [string]::IsNullOrEmpty([string]$unbound.prior_install_id) -and -not (Test-MihoCanonicalUuidV1 -Value ([string]$unbound.prior_install_id))) -or
        (-not [string]::IsNullOrEmpty([string]$unbound.prior_manifest_sha256) -and [string]$unbound.prior_manifest_sha256 -cnotmatch '^[0-9a-f]{64}$')) {
        throw "Automation unbound receipt identity is foreign or corrupt."
    }
    return $record
}

function Get-MihoOwnerContextV1 {
    param(
        [Parameter(Mandatory = $true)]$ExpectedOwner,
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity
    )

    $record = Read-MihoAuthorityV1 -Paths $Paths -Identity $Identity
    if ($null -eq $record) { throw "Automation authority is missing; explicit owner Claim or migration is required." }
    $authority = $record.Object
    if ([string]$authority.owner_kind -cne $ExpectedOwner.Kind -or [string]$authority.owner_instance_id -cne $ExpectedOwner.InstanceId) {
        throw "Automation authority belongs to a different owner instance."
    }
    return [pscustomobject][ordered]@{
        Kind = [string]$authority.owner_kind
        InstanceId = [string]$authority.owner_instance_id
        Epoch = [string]$authority.owner_epoch
        AuthorityBytes = $record.Bytes
    }
}

function Test-MihoOwnerTripletMatchesV1 {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)]$Owner
    )

    return ([string]$Object.owner_kind -ceq $Owner.Kind -and
        [string]$Object.owner_instance_id -ceq $Owner.InstanceId -and
        [string]$Object.owner_epoch -ceq $Owner.Epoch)
}

function Get-MihoClaimJournalEmbeddedBytesV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)][ValidateSet("authority", "unbound")][string]$Kind
    )

    $existed = [bool]$Journal.("old_" + $Kind + "_existed")
    $encoded = [string]$Journal.("old_" + $Kind + "_bytes_base64")
    $expectedHash = [string]$Journal.("old_" + $Kind + "_sha256")
    if (-not $existed) {
        if (-not [string]::IsNullOrEmpty($encoded) -or -not [string]::IsNullOrEmpty($expectedHash)) {
            throw "Automation owner claim journal has contradictory old $Kind evidence."
        }
        return $null
    }
    $bytes = ConvertFrom-MihoBase64V1 -Text $encoded
    if ($bytes.Length -gt $script:MihoOwnerStateMaximumBytesV1 -or
        $expectedHash -cnotmatch '^[0-9a-f]{64}$' -or
        (Get-MihoSha256BytesV1 -Bytes $bytes) -cne $expectedHash) {
        throw "Automation owner claim journal old $Kind evidence is corrupt."
    }
    return $bytes
}

function Assert-MihoEmbeddedAuthorityV1 {
    param(
        [Parameter(Mandatory = $true)][byte[]]$Bytes,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Paths
    )

    $object = ConvertFrom-MihoStrictJsonBytesV1 -Bytes $Bytes -MaximumBytes $script:MihoOwnerStateMaximumBytesV1
    Assert-MihoObjectExactPropertyNamesV1 -Object $object -ExpectedNames @(
        "schema", "owner_kind", "owner_instance_id", "owner_epoch", "owner_sid",
        "task_name", "task_path", "automation_root"
    ) -Label "Embedded automation authority"
    Assert-MihoOwnerTripletV1 -Object $object -Label "Embedded automation authority"
    if ([string]$object.schema -cne $script:MihoAutomationAuthoritySchemaV1 -or
        -not [string]::Equals([string]$object.owner_sid, $Identity.OwnerSid, [System.StringComparison]::OrdinalIgnoreCase) -or
        [string]$object.task_name -cne $Identity.TaskName -or [string]$object.task_path -cne $Identity.TaskPath -or
        -not (Test-MihoPathEqualV1 -Left ([string]$object.automation_root) -Right $Paths.Root)) {
        throw "Embedded automation authority is foreign or corrupt."
    }
    return $object
}

function Assert-MihoEmbeddedUnboundV1 {
    param(
        [Parameter(Mandatory = $true)][byte[]]$Bytes,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Paths
    )

    $object = ConvertFrom-MihoStrictJsonBytesV1 -Bytes $Bytes -MaximumBytes $script:MihoOwnerStateMaximumBytesV1
    Assert-MihoObjectExactPropertyNamesV1 -Object $object -ExpectedNames @(
        "schema", "owner_kind", "owner_instance_id", "owner_epoch", "owner_sid",
        "task_name", "task_path", "automation_root", "prior_install_id", "prior_manifest_sha256"
    ) -Label "Embedded automation unbound receipt"
    Assert-MihoOwnerTripletV1 -Object $object -Label "Embedded automation unbound receipt"
    if ([string]$object.schema -cne $script:MihoAutomationUnboundSchemaV1 -or
        -not [string]::Equals([string]$object.owner_sid, $Identity.OwnerSid, [System.StringComparison]::OrdinalIgnoreCase) -or
        [string]$object.task_name -cne $Identity.TaskName -or [string]$object.task_path -cne $Identity.TaskPath -or
        -not (Test-MihoPathEqualV1 -Left ([string]$object.automation_root) -Right $Paths.Root) -or
        (([string]::IsNullOrEmpty([string]$object.prior_install_id)) -xor ([string]::IsNullOrEmpty([string]$object.prior_manifest_sha256)) -or
        (-not [string]::IsNullOrEmpty([string]$object.prior_install_id) -and -not (Test-MihoCanonicalUuidV1 -Value ([string]$object.prior_install_id))) -or
        (-not [string]::IsNullOrEmpty([string]$object.prior_manifest_sha256) -and [string]$object.prior_manifest_sha256 -cnotmatch '^[0-9a-f]{64}$'))) {
        throw "Embedded automation unbound receipt is foreign or corrupt."
    }
    return $object
}

function New-MihoClaimJournalV1 {
    param(
        [Parameter(Mandatory = $true)]$ExpectedOwner,
        [Parameter(Mandatory = $true)][string]$OwnerEpoch,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Paths,
        [byte[]]$OldAuthorityBytes,
        [byte[]]$OldUnboundBytes,
        [Parameter(Mandatory = $true)][byte[]]$NewAuthorityBytes,
        [Parameter(Mandatory = $true)][byte[]]$NewUnboundBytes
    )

    return [pscustomobject][ordered]@{
        schema = $script:MihoAutomationClaimJournalSchemaV1
        phase = "prepared"
        owner_sid = $Identity.OwnerSid
        task_name = $Identity.TaskName
        task_path = $Identity.TaskPath
        automation_root = $Paths.Root
        owner_kind = $ExpectedOwner.Kind
        owner_instance_id = $ExpectedOwner.InstanceId
        owner_epoch = $OwnerEpoch
        old_authority_existed = $null -ne $OldAuthorityBytes
        old_authority_bytes_base64 = if ($null -eq $OldAuthorityBytes) { "" } else { ConvertTo-MihoBase64V1 -Bytes $OldAuthorityBytes }
        old_authority_sha256 = if ($null -eq $OldAuthorityBytes) { "" } else { Get-MihoSha256BytesV1 -Bytes $OldAuthorityBytes }
        old_unbound_existed = $null -ne $OldUnboundBytes
        old_unbound_bytes_base64 = if ($null -eq $OldUnboundBytes) { "" } else { ConvertTo-MihoBase64V1 -Bytes $OldUnboundBytes }
        old_unbound_sha256 = if ($null -eq $OldUnboundBytes) { "" } else { Get-MihoSha256BytesV1 -Bytes $OldUnboundBytes }
        new_authority_sha256 = Get-MihoSha256BytesV1 -Bytes $NewAuthorityBytes
        new_unbound_sha256 = Get-MihoSha256BytesV1 -Bytes $NewUnboundBytes
    }
}

function Write-MihoClaimJournalV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)]$Paths,
        [hashtable]$FileHooks
    )

    Write-MihoAtomicBytesV1 -Path $Paths.ClaimJournal -Bytes (ConvertTo-MihoJsonBytesV1 -Object $Journal) -Purpose "claim-journal" -FileHooks $FileHooks
}

function Read-MihoClaimJournalV1 {
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$ExpectedOwner
    )

    $record = Read-MihoJsonFileV1 -Path $Paths.ClaimJournal -MaximumBytes $script:MihoOwnerStateMaximumBytesV1 -ExpectedKeys @(
        "schema", "phase", "owner_sid", "task_name", "task_path", "automation_root",
        "owner_kind", "owner_instance_id", "owner_epoch", "old_authority_existed",
        "old_authority_bytes_base64", "old_authority_sha256", "old_unbound_existed",
        "old_unbound_bytes_base64", "old_unbound_sha256", "new_authority_sha256", "new_unbound_sha256"
    )
    $journal = $record.Object
    foreach ($name in @(
        "schema", "phase", "owner_sid", "task_name", "task_path", "automation_root", "owner_kind",
        "owner_instance_id", "owner_epoch", "old_authority_bytes_base64", "old_authority_sha256",
        "old_unbound_bytes_base64", "old_unbound_sha256", "new_authority_sha256", "new_unbound_sha256"
    )) {
        if (-not ($journal.$name -is [string])) { throw "Automation owner claim journal values are invalid." }
    }
    if (-not ($journal.old_authority_existed -is [bool]) -or -not ($journal.old_unbound_existed -is [bool]) -or
        [string]$journal.schema -cne $script:MihoAutomationClaimJournalSchemaV1 -or
        [string]$journal.phase -cnotin @("prepared", "authority-replaced", "unbound-replaced", "committed") -or
        -not [string]::Equals([string]$journal.owner_sid, $Identity.OwnerSid, [System.StringComparison]::OrdinalIgnoreCase) -or
        [string]$journal.task_name -cne $Identity.TaskName -or [string]$journal.task_path -cne $Identity.TaskPath -or
        -not (Test-MihoPathEqualV1 -Left ([string]$journal.automation_root) -Right $Paths.Root) -or
        [string]$journal.owner_kind -cne $ExpectedOwner.Kind -or [string]$journal.owner_instance_id -cne $ExpectedOwner.InstanceId -or
        -not (Test-MihoCanonicalUuidV1 -Value ([string]$journal.owner_epoch)) -or
        [string]$journal.new_authority_sha256 -cnotmatch '^[0-9a-f]{64}$' -or [string]$journal.new_unbound_sha256 -cnotmatch '^[0-9a-f]{64}$') {
        throw "Automation owner claim journal identity or phase is invalid."
    }
    $oldAuthority = Get-MihoClaimJournalEmbeddedBytesV1 -Journal $journal -Kind "authority"
    $oldUnbound = Get-MihoClaimJournalEmbeddedBytesV1 -Journal $journal -Kind "unbound"
    if ($null -ne $oldAuthority) { $null = Assert-MihoEmbeddedAuthorityV1 -Bytes $oldAuthority -Identity $Identity -Paths $Paths }
    if ($null -ne $oldUnbound) { $null = Assert-MihoEmbeddedUnboundV1 -Bytes $oldUnbound -Identity $Identity -Paths $Paths }
    return [pscustomobject][ordered]@{
        Journal = $journal
        OldAuthorityBytes = $oldAuthority
        OldUnboundBytes = $oldUnbound
    }
}

function Assert-MihoClaimRootCleanV1 {
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)][hashtable]$Adapter,
        [switch]$AllowClaimJournal
    )

    if ($null -ne (Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($Identity.TaskName)) -or
        (Test-Path -LiteralPath $Paths.Manifest) -or (Test-Path -LiteralPath $Paths.Journal)) {
        throw "Automation owner claim requires no task, manifest, or switch journal."
    }
    if (-not (Test-Path -LiteralPath $Paths.Generations)) { throw "Automation owner claim lacks its generations directory." }
    if (@(Get-ChildItem -LiteralPath $Paths.Generations -Force -ErrorAction Stop).Count -ne 0) {
        throw "Automation owner claim requires an empty generations directory."
    }
    $allowed = @("generations", ".automation-switch-v1.lock", "automation-authority-v1.json", "automation-unbound-v1.json")
    if ($AllowClaimJournal) { $allowed += "automation-owner-claim-journal-v1.json" }
    foreach ($entry in @(Get-ChildItem -LiteralPath $Paths.Root -Force -ErrorAction Stop)) {
        if ([string]$entry.Name -cnotin $allowed) { throw "Automation owner claim found unknown root content: $($entry.Name)" }
        if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Automation owner claim found a reparse entry." }
    }
}

function Assert-MihoOwnedUnboundRootV1 {
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Owner
    )

    foreach ($entry in @(Get-ChildItem -LiteralPath $Paths.Generations -Force -ErrorAction Stop)) {
        if (-not $entry.PSIsContainer -or [string]$entry.Name -cnotmatch '^\.staging-[0-9a-f]{32}$' -or
            ($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Unbound automation root contains a final or unknown generation."
        }
    }
    $fixed = @("generations", ".automation-switch-v1.lock", "automation-authority-v1.json", "automation-unbound-v1.json")
    foreach ($entry in @(Get-ChildItem -LiteralPath $Paths.Root -Force -ErrorAction Stop)) {
        if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Unbound automation root contains a reparse entry." }
        if ([string]$entry.Name -cin $fixed) { continue }
        if (-not $entry.PSIsContainer -and [string]$entry.Name -cmatch '^rollback-receipt-[0-9a-f]{32}\.json$') { continue }
        if ($entry.PSIsContainer -and [string]$entry.Name -cmatch '^bootstrap-transaction-[0-9a-f]{32}$') { continue }
        throw "Unbound automation root contains unknown content: $($entry.Name)"
    }
}

function Repair-MihoOwnerClaimJournalCoreV1 {
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$ExpectedOwner,
        [Parameter(Mandatory = $true)][hashtable]$Adapter,
        [hashtable]$FileHooks
    )

    if (-not (Test-Path -LiteralPath $Paths.ClaimJournal)) {
        return [pscustomobject][ordered]@{ recovered = $false; committed = $false; fresh_root_rolled_back = $false }
    }
    $evidence = Read-MihoClaimJournalV1 -Paths $Paths -Identity $Identity -ExpectedOwner $ExpectedOwner
    $journal = $evidence.Journal
    $newOwner = [pscustomobject][ordered]@{ Kind = [string]$journal.owner_kind; InstanceId = [string]$journal.owner_instance_id; Epoch = [string]$journal.owner_epoch }
    $newAuthorityBytes = ConvertTo-MihoJsonBytesV1 -Object (New-MihoAuthorityRecordV1 -ExpectedOwner $ExpectedOwner -OwnerEpoch $newOwner.Epoch -Identity $Identity -Paths $Paths)
    $newUnboundBytes = ConvertTo-MihoJsonBytesV1 -Object (New-MihoUnboundRecordV1 -Owner $newOwner -Identity $Identity -Paths $Paths)
    if ((Get-MihoSha256BytesV1 -Bytes $newAuthorityBytes) -cne [string]$journal.new_authority_sha256 -or
        (Get-MihoSha256BytesV1 -Bytes $newUnboundBytes) -cne [string]$journal.new_unbound_sha256) {
        throw "Automation owner claim journal new-state evidence is corrupt."
    }
    foreach ($pair in @(
        [pscustomobject]@{ Path = $Paths.Authority; Old = $evidence.OldAuthorityBytes; New = $newAuthorityBytes; Label = "authority" },
        [pscustomobject]@{ Path = $Paths.Unbound; Old = $evidence.OldUnboundBytes; New = $newUnboundBytes; Label = "unbound receipt" }
    )) {
        if (Test-Path -LiteralPath $pair.Path) {
            $actualHash = Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($pair.Path))
            $allowedHashes = @((Get-MihoSha256BytesV1 -Bytes $pair.New))
            if ($null -ne $pair.Old) { $allowedHashes += (Get-MihoSha256BytesV1 -Bytes $pair.Old) }
            if ($actualHash -cnotin $allowedHashes) { throw "Automation owner claim $($pair.Label) drifted during recovery." }
        }
    }
    if ([string]$journal.phase -ceq "committed") {
        foreach ($pair in @(
            [pscustomobject]@{ Path = $Paths.Authority; Bytes = $newAuthorityBytes },
            [pscustomobject]@{ Path = $Paths.Unbound; Bytes = $newUnboundBytes }
        )) {
            if (-not (Test-Path -LiteralPath $pair.Path) -or
                (Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($pair.Path))) -cne (Get-MihoSha256BytesV1 -Bytes $pair.Bytes)) {
                throw "Committed automation owner claim is incomplete."
            }
        }
        Assert-MihoClaimRootCleanV1 -Paths $Paths -Identity $Identity -Adapter $Adapter -AllowClaimJournal
        Remove-MihoFileV1 -Path $Paths.ClaimJournal -Purpose "claim-journal-commit-cleanup" -FileHooks $FileHooks
        return [pscustomobject][ordered]@{ recovered = $true; committed = $true; fresh_root_rolled_back = $false; owner_epoch = $newOwner.Epoch }
    }
    foreach ($pair in @(
        [pscustomobject]@{ Path = $Paths.Unbound; Old = $evidence.OldUnboundBytes; New = $newUnboundBytes; Purpose = "claim-unbound-rollback" },
        [pscustomobject]@{ Path = $Paths.Authority; Old = $evidence.OldAuthorityBytes; New = $newAuthorityBytes; Purpose = "claim-authority-rollback" }
    )) {
        if ($null -ne $pair.Old) {
            Write-MihoAtomicBytesV1 -Path $pair.Path -Bytes $pair.Old -Purpose $pair.Purpose -FileHooks $FileHooks
        }
        elseif (Test-Path -LiteralPath $pair.Path) {
            $actualHash = Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($pair.Path))
            if ($actualHash -cne (Get-MihoSha256BytesV1 -Bytes $pair.New)) { throw "Automation owner claim rollback encountered foreign state." }
            Remove-MihoFileV1 -Path $pair.Path -Purpose $pair.Purpose -FileHooks $FileHooks
        }
    }
    Remove-MihoFileV1 -Path $Paths.ClaimJournal -Purpose "claim-journal-rollback-cleanup" -FileHooks $FileHooks
    return [pscustomobject][ordered]@{
        recovered = $true
        committed = $false
        fresh_root_rolled_back = ($null -eq $evidence.OldAuthorityBytes -and $null -eq $evidence.OldUnboundBytes)
    }
}

function Claim-MihoAutomationOwnerV1 {
    param(
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerKind,
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerInstanceId,
        [string]$AutomationRoot,
        [hashtable]$Adapter,
        [hashtable]$FileHooks
    )

    $expectedOwner = New-MihoExpectedOwnerV1 -OwnerKind $ExpectedOwnerKind -OwnerInstanceId $ExpectedOwnerInstanceId
    $identity = Get-MihoTaskIdentityV1 -OwnerSid (Get-MihoCurrentSidV1)
    $coordinator = Enter-MihoAutomationCoordinatorV1 -AutomationRoot $AutomationRoot
    try {
        Assert-MihoNoPendingReleaseIntentV1 -Coordinator $coordinator
        if ($null -eq $Adapter) { $Adapter = New-MihoRealAdapterV1 }
        $rootExisted = Test-Path -LiteralPath $coordinator.Root
        $intentRecord = Get-MihoExpectedClaimIntentV1 -Coordinator $coordinator -Identity $identity -ExpectedOwner $expectedOwner
        $intentRecovered = $null -ne $intentRecord

        # A fresh root must never become visible before its durable sibling
        # intent.  The intent is the only authority to resume a kill in this
        # window; foreign or malformed intents are never replaced.
        if (-not $rootExisted -and $null -eq $intentRecord) {
            $epoch = [guid]::NewGuid().ToString("D").ToLowerInvariant()
            $intent = New-MihoClaimIntentRecordV1 -ExpectedOwner $expectedOwner -OwnerEpoch $epoch -Identity $identity -AutomationRoot $coordinator.Root -RootWasAbsent $true
            $intentBytes = ConvertTo-MihoJsonBytesV1 -Object $intent
            Write-MihoClaimIntentV1 -Coordinator $coordinator -Bytes $intentBytes -FileHooks $FileHooks
            $intentRecord = [pscustomobject][ordered]@{ Bytes = $intentBytes; Object = $intent }
        }

        $paths = Get-MihoAutomationPathsV1 -AutomationRoot $coordinator.Root
        $mutex = Enter-MihoAutomationMutexV1 -Paths $paths
        try {
            if (Test-Path -LiteralPath $paths.Journal) { throw "Automation owner claim is blocked by an active switch journal." }

            if (Test-Path -LiteralPath $paths.ClaimJournal) {
                if ($null -eq $intentRecord) {
                    throw "Automation owner claim journal lacks its durable sibling intent."
                }
                $claimEvidence = Read-MihoClaimJournalV1 -Paths $paths -Identity $identity -ExpectedOwner $expectedOwner
                if ([string]$claimEvidence.Journal.owner_epoch -cne [string]$intentRecord.Object.owner_epoch) {
                    throw "Automation owner claim journal and sibling intent disagree."
                }
                $repair = Repair-MihoOwnerClaimJournalCoreV1 -Paths $paths -Identity $identity -ExpectedOwner $expectedOwner -Adapter $Adapter -FileHooks $FileHooks
                if ($repair.committed) {
                    Remove-MihoExpectedClaimIntentV1 -Coordinator $coordinator -ExpectedBytes $intentRecord.Bytes -FileHooks $FileHooks
                    return [pscustomobject][ordered]@{
                        schema = "miho-automation-owner-claim-result-v1"
                        owner_kind = $expectedOwner.Kind
                        owner_instance_id = $expectedOwner.InstanceId
                        owner_epoch = [string]$repair.owner_epoch
                        claimed = $true
                        recovered = $true
                        root_was_absent = [bool]$intentRecord.Object.root_was_absent
                        claim_created_new_owner = [bool]$intentRecord.Object.root_was_absent
                    }
                }
                $intentRecovered = $true
            }

            $oldAuthority = Read-MihoAuthorityV1 -Paths $paths -Identity $identity
            $oldUnbound = Read-MihoUnboundV1 -Paths $paths -Identity $identity

            # The claim journal is deleted before the sibling intent.  A kill
            # in that one-way window is completed only when both strict owner
            # records exactly match the intent epoch.
            if ($null -ne $intentRecord -and $null -ne $oldAuthority -and $null -ne $oldUnbound -and
                (Test-MihoOwnerTripletMatchesV1 -Object $oldAuthority.Object -Owner ([pscustomobject]@{ Kind = [string]$intentRecord.Object.owner_kind; InstanceId = [string]$intentRecord.Object.owner_instance_id; Epoch = [string]$intentRecord.Object.owner_epoch })) -and
                (Test-MihoOwnerTripletMatchesV1 -Object $oldUnbound.Object -Owner ([pscustomobject]@{ Kind = [string]$intentRecord.Object.owner_kind; InstanceId = [string]$intentRecord.Object.owner_instance_id; Epoch = [string]$intentRecord.Object.owner_epoch }))) {
                Assert-MihoClaimRootCleanV1 -Paths $paths -Identity $identity -Adapter $Adapter
                Remove-MihoExpectedClaimIntentV1 -Coordinator $coordinator -ExpectedBytes $intentRecord.Bytes -FileHooks $FileHooks
                return [pscustomobject][ordered]@{
                    schema = "miho-automation-owner-claim-result-v1"
                    owner_kind = $expectedOwner.Kind
                    owner_instance_id = $expectedOwner.InstanceId
                    owner_epoch = [string]$intentRecord.Object.owner_epoch
                    claimed = $true
                    recovered = $true
                    root_was_absent = [bool]$intentRecord.Object.root_was_absent
                    claim_created_new_owner = [bool]$intentRecord.Object.root_was_absent
                }
            }

            if ($null -eq $oldAuthority) {
                if ($null -ne $oldUnbound -or $null -eq $intentRecord) {
                    throw "Existing automation root has no authority; explicit legacy migration is required."
                }
            }
            else {
                if ($null -eq $oldUnbound) {
                    if ([string]$oldAuthority.Object.owner_kind -cne $expectedOwner.Kind -or
                        [string]$oldAuthority.Object.owner_instance_id -cne $expectedOwner.InstanceId) {
                        throw "Automation authority belongs to a different owner instance; implicit migration is unavailable."
                    }
                    $binding = Test-MihoDesktopAutomationBindingV1 `
                        -AutomationRoot $paths.Root `
                        -ExpectedOwnerKind $expectedOwner.Kind `
                        -ExpectedOwnerInstanceId $expectedOwner.InstanceId `
                        -CallerHoldsSwitchLease $true `
                        -Adapter $Adapter
                    if ([string]$binding.status -cne "active") {
                        throw "Active or ambiguously bound automation authority cannot be claimed."
                    }
                    return [pscustomobject][ordered]@{
                        schema = "miho-automation-owner-claim-result-v1"
                        owner_kind = $expectedOwner.Kind
                        owner_instance_id = $expectedOwner.InstanceId
                        owner_epoch = [string]$oldAuthority.Object.owner_epoch
                        claimed = $true
                        recovered = $false
                        root_was_absent = $false
                        claim_created_new_owner = $false
                    }
                }
                if ([string]$oldAuthority.Object.owner_kind -cne $expectedOwner.Kind -or
                    [string]$oldAuthority.Object.owner_instance_id -cne $expectedOwner.InstanceId) {
                    throw "Automation authority belongs to a different owner instance; implicit migration is unavailable."
                }
                if ([string]$oldAuthority.Object.owner_kind -cne [string]$oldUnbound.Object.owner_kind -or
                    [string]$oldAuthority.Object.owner_instance_id -cne [string]$oldUnbound.Object.owner_instance_id -or
                    [string]$oldAuthority.Object.owner_epoch -cne [string]$oldUnbound.Object.owner_epoch) {
                    throw "Automation authority and unbound receipt disagree."
                }
            }
            Assert-MihoClaimRootCleanV1 -Paths $paths -Identity $identity -Adapter $Adapter

            # Existing clean-unbound roots are inspected before reservation so
            # a rejected migration attempt cannot leave a new sibling intent.
            if ($null -eq $intentRecord) {
                $epoch = [guid]::NewGuid().ToString("D").ToLowerInvariant()
                $intent = New-MihoClaimIntentRecordV1 -ExpectedOwner $expectedOwner -OwnerEpoch $epoch -Identity $identity -AutomationRoot $coordinator.Root -RootWasAbsent $false
                $intentBytes = ConvertTo-MihoJsonBytesV1 -Object $intent
                Write-MihoClaimIntentV1 -Coordinator $coordinator -Bytes $intentBytes -FileHooks $FileHooks
                $intentRecord = [pscustomobject][ordered]@{ Bytes = $intentBytes; Object = $intent }
            }
            $epoch = [string]$intentRecord.Object.owner_epoch
            $newOwner = [pscustomobject][ordered]@{ Kind = $expectedOwner.Kind; InstanceId = $expectedOwner.InstanceId; Epoch = $epoch }
            $authorityBytes = ConvertTo-MihoJsonBytesV1 -Object (New-MihoAuthorityRecordV1 -ExpectedOwner $expectedOwner -OwnerEpoch $epoch -Identity $identity -Paths $paths)
            $unboundBytes = ConvertTo-MihoJsonBytesV1 -Object (New-MihoUnboundRecordV1 -Owner $newOwner -Identity $identity -Paths $paths)
            $journal = New-MihoClaimJournalV1 -ExpectedOwner $expectedOwner -OwnerEpoch $epoch -Identity $identity -Paths $paths -OldAuthorityBytes $(if ($null -eq $oldAuthority) { $null } else { $oldAuthority.Bytes }) -OldUnboundBytes $(if ($null -eq $oldUnbound) { $null } else { $oldUnbound.Bytes }) -NewAuthorityBytes $authorityBytes -NewUnboundBytes $unboundBytes
            try {
                Write-MihoClaimJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
                Write-MihoAtomicBytesV1 -Path $paths.Authority -Bytes $authorityBytes -Purpose "claim-authority" -FileHooks $FileHooks
                $journal.phase = "authority-replaced"
                Write-MihoClaimJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
                Write-MihoAtomicBytesV1 -Path $paths.Unbound -Bytes $unboundBytes -Purpose "claim-unbound" -FileHooks $FileHooks
                $journal.phase = "unbound-replaced"
                Write-MihoClaimJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
                $journal.phase = "committed"
                Write-MihoClaimJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
                Remove-MihoFileV1 -Path $paths.ClaimJournal -Purpose "claim-journal-commit-cleanup" -FileHooks $FileHooks
                Remove-MihoExpectedClaimIntentV1 -Coordinator $coordinator -ExpectedBytes $intentRecord.Bytes -FileHooks $FileHooks
            }
            catch {
                $primary = $_
                try {
                    $repair = Repair-MihoOwnerClaimJournalCoreV1 -Paths $paths -Identity $identity -ExpectedOwner $expectedOwner -Adapter $Adapter -FileHooks $FileHooks
                    if ($repair.committed) {
                        Remove-MihoExpectedClaimIntentV1 -Coordinator $coordinator -ExpectedBytes $intentRecord.Bytes -FileHooks $FileHooks
                        return [pscustomobject][ordered]@{
                            schema = "miho-automation-owner-claim-result-v1"
                            owner_kind = $expectedOwner.Kind
                            owner_instance_id = $expectedOwner.InstanceId
                            owner_epoch = [string]$repair.owner_epoch
                            claimed = $true
                            recovered = $true
                            root_was_absent = [bool]$intentRecord.Object.root_was_absent
                            claim_created_new_owner = [bool]$intentRecord.Object.root_was_absent
                        }
                    }
                    throw "__MIHO_CLAIM_ROLLED_BACK__ Automation owner claim failed and was rolled back. Primary: $($primary.Exception.Message)"
                }
                catch {
                    if ($_.Exception.Message -like "__MIHO_CLAIM_ROLLED_BACK__*") { throw $_.Exception.Message.Substring("__MIHO_CLAIM_ROLLED_BACK__ ".Length) }
                    throw "Automation owner claim failed and rollback is pending. Primary: $($primary.Exception.Message) Rollback: $($_.Exception.Message)"
                }
            }
            return [pscustomobject][ordered]@{
                schema = "miho-automation-owner-claim-result-v1"
                owner_kind = $expectedOwner.Kind
                owner_instance_id = $expectedOwner.InstanceId
                owner_epoch = $epoch
                claimed = $true
                recovered = [bool]$intentRecovered
                root_was_absent = [bool]$intentRecord.Object.root_was_absent
                claim_created_new_owner = [bool]$intentRecord.Object.root_was_absent
            }
        }
        finally { Exit-MihoAutomationMutexV1 -Mutex $mutex }
    }
    finally { Exit-MihoAutomationCoordinatorV1 -Coordinator $coordinator }
}

function Assert-MihoReleaseOwnedFileV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256
    )

    if (-not (Test-Path -LiteralPath $Path)) { return }
    Assert-MihoNoReparseChainV1 -Path $Path
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if ($item.PSIsContainer -or (Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($Path))) -cne $ExpectedSha256) {
        throw "Automation owner release encountered drifted state."
    }
}

function Remove-MihoReleaseOwnedFileV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256,
        [Parameter(Mandatory = $true)][string]$Purpose,
        [hashtable]$FileHooks
    )

    Assert-MihoReleaseOwnedFileV1 -Path $Path -ExpectedSha256 $ExpectedSha256
    if (-not (Test-Path -LiteralPath $Path)) { return }
    try { Remove-MihoFileV1 -Path $Path -Purpose $Purpose -FileHooks $FileHooks }
    catch { if (Test-Path -LiteralPath $Path) { throw } }
}

function Invoke-MihoReleaseCheckpointV1 {
    param(
        [hashtable]$FileHooks,
        [Parameter(Mandatory = $true)][string]$Stage
    )

    if ($null -ne $FileHooks -and $FileHooks.ContainsKey("ReleaseCheckpoint")) {
        & $FileHooks["ReleaseCheckpoint"] $Stage
    }
}

function Reserve-MihoAutomationOwnerReleaseV1 {
    param(
        [Parameter(Mandatory = $true)]$Coordinator,
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Owner,
        [Parameter(Mandatory = $true)][byte[]]$ExpectedUnboundBytes,
        $ExistingIntent,
        [hashtable]$FileHooks
    )

    $authorityRecord = Read-MihoAuthorityV1 -Paths $Paths -Identity $Identity
    if ($null -eq $authorityRecord -or -not (Test-MihoOwnerTripletMatchesV1 -Object $authorityRecord.Object -Owner $Owner)) {
        throw "Automation owner release reservation lacks its exact authority epoch."
    }
    $authoritySha256 = Get-MihoSha256BytesV1 -Bytes $authorityRecord.Bytes
    $unboundSha256 = Get-MihoSha256BytesV1 -Bytes $ExpectedUnboundBytes
    if ($null -ne $ExistingIntent) {
        if (-not (Test-MihoOwnerTripletMatchesV1 -Object $ExistingIntent.Object -Owner $Owner) -or
            [string]$ExistingIntent.Object.authority_sha256 -cne $authoritySha256 -or
            [string]$ExistingIntent.Object.unbound_sha256 -cne $unboundSha256) {
            throw "Pending automation owner release reservation belongs to another owner epoch or state."
        }
        return [pscustomobject][ordered]@{ Record = $ExistingIntent; Created = $false }
    }

    $rollbackReceipts = New-Object System.Collections.ArrayList
    foreach ($entry in @(Get-ChildItem -LiteralPath $Paths.Root -Force -File -ErrorAction Stop | Sort-Object Name)) {
        if ([string]$entry.Name -cnotmatch '^rollback-receipt-([0-9a-f]{32})\.json$') { continue }
        $token = [string]$Matches[1]
        $receipt = Get-MihoRollbackReceiptV1 -TransactionToken $token -Paths $Paths -Identity $Identity -Owner $Owner
        if ($null -eq $receipt -or -not (Test-MihoPathEqualV1 -Left $receipt.Path -Right $entry.FullName) -or
            -not [string]::IsNullOrEmpty([string]$receipt.Object.retained_bootstrap_transaction)) {
            throw "Automation owner release reservation found a nonterminal rollback receipt."
        }
        $null = $rollbackReceipts.Add([pscustomobject][ordered]@{
            transaction_token = $token
            receipt_sha256 = Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($receipt.Path))
        })
    }
    $intent = New-MihoReleaseIntentRecordV1 `
        -Owner $Owner `
        -Identity $Identity `
        -AutomationRoot $Paths.Root `
        -AuthoritySha256 $authoritySha256 `
        -UnboundSha256 $unboundSha256 `
        -RollbackReceipts @($rollbackReceipts)
    $intentBytes = ConvertTo-MihoJsonBytesV1 -Object $intent
    Write-MihoReleaseIntentV1 -Path $Coordinator.ReleaseIntent -Bytes $intentBytes -FileHooks $FileHooks
    return [pscustomobject][ordered]@{
        Record = [pscustomobject][ordered]@{ Bytes = $intentBytes; Object = $intent }
        Created = $true
    }
}

function Release-MihoAutomationOwnerClaimV1 {
    param(
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerKind,
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerInstanceId,
        [string]$AutomationRoot,
        [hashtable]$Adapter,
        [hashtable]$FileHooks,
        $CallerCoordinator
    )

    $expectedOwner = New-MihoExpectedOwnerV1 -OwnerKind $ExpectedOwnerKind -OwnerInstanceId $ExpectedOwnerInstanceId
    $identity = Get-MihoTaskIdentityV1 -OwnerSid (Get-MihoCurrentSidV1)
    $ownsCoordinator = $null -eq $CallerCoordinator
    if ($ownsCoordinator) {
        $coordinator = Enter-MihoAutomationCoordinatorV1 -AutomationRoot $AutomationRoot
    }
    else {
        Assert-MihoAutomationCoordinatorLeaseV1 -Coordinator $CallerCoordinator -AutomationRoot $AutomationRoot
        $coordinator = $CallerCoordinator
    }
    try {
        if (Test-Path -LiteralPath $coordinator.ClaimIntent) {
            throw "Automation owner Claim must be recovered before ReleaseClaim."
        }
        $intentRecord = Read-MihoReleaseIntentV1 -Path $coordinator.ReleaseIntent -Identity $identity -AutomationRoot $coordinator.Root
        $recovered = $null -ne $intentRecord
        if ($null -ne $intentRecord -and
            ([string]$intentRecord.Object.owner_kind -cne $expectedOwner.Kind -or
             [string]$intentRecord.Object.owner_instance_id -cne $expectedOwner.InstanceId)) {
            throw "Automation owner release intent belongs to a different owner instance."
        }
        if (-not (Test-Path -LiteralPath $coordinator.Root)) {
            if ($null -eq $intentRecord) {
                return [pscustomobject][ordered]@{
                    schema = "miho-automation-owner-release-result-v1"
                    owner_kind = $expectedOwner.Kind
                    owner_instance_id = $expectedOwner.InstanceId
                    released = $false
                    already_absent = $true
                    recovered = $false
                }
            }
            Remove-MihoExpectedReleaseIntentV1 -Path $coordinator.ReleaseIntent -ExpectedBytes $intentRecord.Bytes -FileHooks $FileHooks
            return [pscustomobject][ordered]@{
                schema = "miho-automation-owner-release-result-v1"
                owner_kind = $expectedOwner.Kind
                owner_instance_id = $expectedOwner.InstanceId
                released = $true
                already_absent = $false
                recovered = $true
            }
        }

        if ($null -eq $Adapter) { $Adapter = New-MihoRealAdapterV1 }
        $root = Resolve-MihoExistingDirectoryV1 -Path $coordinator.Root -Label "Automation root"
        $paths = [pscustomobject][ordered]@{
            Root = $root
            Generations = Join-Path $root "generations"
            Manifest = Join-Path $root "automation-owner-v1.json"
            Journal = Join-Path $root "automation-switch-journal-v1.json"
            Authority = Join-Path $root "automation-authority-v1.json"
            Unbound = Join-Path $root "automation-unbound-v1.json"
            ClaimJournal = Join-Path $root "automation-owner-claim-journal-v1.json"
            ClaimIntent = $coordinator.ClaimIntent
            Lock = Join-Path $root ".automation-switch-v1.lock"
            RootCreated = $false
        }
        $mutex = $null
        try {
            if (Test-Path -LiteralPath $paths.Lock) {
                $mutex = Enter-MihoAutomationMutexV1 -Paths $paths
            }
            elseif ($null -eq $intentRecord) {
                throw "Automation owner release requires the existing switch lock."
            }

            if ($null -eq (Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($identity.TaskName))) {
                # Expected clean-unbound state.
            }
            else { throw "Automation owner release refuses an existing canonical task." }

            $intentRollbackReceipts = @{}
            if ($null -ne $intentRecord) {
                foreach ($receipt in @($intentRecord.Object.rollback_receipts)) {
                    $intentRollbackReceipts[[string]$receipt.transaction_token] = $receipt
                }
            }
            $rollbackReceiptEntries = New-Object System.Collections.ArrayList
            $allowed = @("generations", ".automation-switch-v1.lock", "automation-authority-v1.json", "automation-unbound-v1.json")
            foreach ($entry in @(Get-ChildItem -LiteralPath $root -Force -ErrorAction Stop)) {
                if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                    throw "Automation owner release found non-clean root state."
                }
                if ([string]$entry.Name -cin $allowed) { continue }
                if (-not $entry.PSIsContainer -and [string]$entry.Name -cmatch '^rollback-receipt-([0-9a-f]{32})\.json$') {
                    $token = [string]$Matches[1]
                    if ($null -ne $intentRecord -and -not $intentRollbackReceipts.ContainsKey($token)) {
                        throw "Automation owner release found an unreserved rollback receipt."
                    }
                    $null = $rollbackReceiptEntries.Add([pscustomobject][ordered]@{ Token = $token; Path = $entry.FullName })
                    continue
                }
                throw "Automation owner release found non-clean root state."
            }
            if (Test-Path -LiteralPath $paths.Generations) {
                $generations = Resolve-MihoExistingDirectoryV1 -Path $paths.Generations -Label "Automation generations root"
                if (@(Get-ChildItem -LiteralPath $generations -Force -ErrorAction Stop).Count -ne 0) {
                    throw "Automation owner release requires empty generations."
                }
            }
            elseif ($null -eq $intentRecord) { throw "Automation owner release lacks generations state." }

            if ($null -eq $intentRecord) {
                $authorityRecord = Read-MihoAuthorityV1 -Paths $paths -Identity $identity
                $unboundRecord = Read-MihoUnboundV1 -Paths $paths -Identity $identity
                if ($null -eq $authorityRecord -or $null -eq $unboundRecord) {
                    throw "Automation owner release requires exact authority and unbound receipts."
                }
                $owner = [pscustomobject][ordered]@{
                    Kind = [string]$authorityRecord.Object.owner_kind
                    InstanceId = [string]$authorityRecord.Object.owner_instance_id
                    Epoch = [string]$authorityRecord.Object.owner_epoch
                }
                if ($owner.Kind -cne $expectedOwner.Kind -or $owner.InstanceId -cne $expectedOwner.InstanceId -or
                    -not (Test-MihoOwnerTripletMatchesV1 -Object $unboundRecord.Object -Owner $owner)) {
                    throw "Automation owner release authority is foreign or inconsistent."
                }
                $rollbackReceipts = New-Object System.Collections.ArrayList
                foreach ($entry in @($rollbackReceiptEntries)) {
                    $receipt = Get-MihoRollbackReceiptV1 -TransactionToken $entry.Token -Paths $paths -Identity $identity -Owner $owner
                    if ($null -eq $receipt -or -not (Test-MihoPathEqualV1 -Left $receipt.Path -Right $entry.Path) -or
                        -not [string]::IsNullOrEmpty([string]$receipt.Object.retained_bootstrap_transaction)) {
                        throw "Automation owner release rollback receipt is not terminal or exact."
                    }
                    $null = $rollbackReceipts.Add([pscustomobject][ordered]@{
                        transaction_token = $entry.Token
                        receipt_sha256 = Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($receipt.Path))
                    })
                }
                $intent = New-MihoReleaseIntentRecordV1 `
                    -Owner $owner `
                    -Identity $identity `
                    -AutomationRoot $root `
                    -AuthoritySha256 (Get-MihoSha256BytesV1 -Bytes $authorityRecord.Bytes) `
                    -UnboundSha256 (Get-MihoSha256BytesV1 -Bytes $unboundRecord.Bytes) `
                    -RollbackReceipts @($rollbackReceipts)
                $intentBytes = ConvertTo-MihoJsonBytesV1 -Object $intent
                Write-MihoReleaseIntentV1 -Path $coordinator.ReleaseIntent -Bytes $intentBytes -FileHooks $FileHooks
                $intentRecord = [pscustomobject][ordered]@{ Bytes = $intentBytes; Object = $intent }
                Invoke-MihoReleaseCheckpointV1 -FileHooks $FileHooks -Stage "intent-written"
            }

            $fixedReleaseFiles = @(
                [pscustomobject]@{ Path = $paths.Authority; Hash = [string]$intentRecord.Object.authority_sha256; Purpose = "release-authority" },
                [pscustomobject]@{ Path = $paths.Unbound; Hash = [string]$intentRecord.Object.unbound_sha256; Purpose = "release-unbound" }
            )
            $rollbackReleaseFiles = New-Object System.Collections.ArrayList
            foreach ($receipt in @($intentRecord.Object.rollback_receipts)) {
                $null = $rollbackReleaseFiles.Add([pscustomobject]@{
                    Path = Join-Path $root ("rollback-receipt-" + [string]$receipt.transaction_token + ".json")
                    Hash = [string]$receipt.receipt_sha256
                    Purpose = "release-rollback-receipt"
                })
            }
            $allReleaseFiles = @($fixedReleaseFiles) + @($rollbackReleaseFiles)
            foreach ($pair in $allReleaseFiles) {
                Assert-MihoReleaseOwnedFileV1 -Path $pair.Path -ExpectedSha256 $pair.Hash
            }
            foreach ($pair in $fixedReleaseFiles) {
                Remove-MihoReleaseOwnedFileV1 -Path $pair.Path -ExpectedSha256 $pair.Hash -Purpose $pair.Purpose -FileHooks $FileHooks
                Invoke-MihoReleaseCheckpointV1 -FileHooks $FileHooks -Stage ($pair.Purpose + "-removed")
            }
            foreach ($pair in @($rollbackReleaseFiles)) {
                Remove-MihoReleaseOwnedFileV1 -Path $pair.Path -ExpectedSha256 $pair.Hash -Purpose $pair.Purpose -FileHooks $FileHooks
            }
            Invoke-MihoReleaseCheckpointV1 -FileHooks $FileHooks -Stage "rollback-receipts-removed"
        }
        finally { Exit-MihoAutomationMutexV1 -Mutex $mutex }

        if (Test-Path -LiteralPath $paths.Generations) {
            try { Remove-MihoDirectoryV1 -Path $paths.Generations -Purpose "release-generations" -FileHooks $FileHooks }
            catch { if (Test-Path -LiteralPath $paths.Generations) { throw } }
        }
        Invoke-MihoReleaseCheckpointV1 -FileHooks $FileHooks -Stage "generations-removed"
        if (Test-Path -LiteralPath $paths.Lock) {
            Assert-MihoNoReparseChainV1 -Path $paths.Lock
            $lockItem = Get-Item -LiteralPath $paths.Lock -Force -ErrorAction Stop
            if ($lockItem.PSIsContainer -or [int64]$lockItem.Length -ne 0) { throw "Automation release switch lock drifted." }
            try { Remove-MihoFileV1 -Path $paths.Lock -Purpose "release-switch-lock" -FileHooks $FileHooks }
            catch { if (Test-Path -LiteralPath $paths.Lock) { throw } }
        }
        Invoke-MihoReleaseCheckpointV1 -FileHooks $FileHooks -Stage "switch-lock-removed"
        if (@(Get-ChildItem -LiteralPath $root -Force -ErrorAction Stop).Count -ne 0) {
            throw "Automation owner release root is not empty after exact cleanup."
        }
        try { Remove-MihoDirectoryV1 -Path $root -Purpose "release-root" -FileHooks $FileHooks }
        catch { if (Test-Path -LiteralPath $root) { throw } }
        Invoke-MihoReleaseCheckpointV1 -FileHooks $FileHooks -Stage "root-removed"
        Remove-MihoExpectedReleaseIntentV1 -Path $coordinator.ReleaseIntent -ExpectedBytes $intentRecord.Bytes -FileHooks $FileHooks
        Invoke-MihoReleaseCheckpointV1 -FileHooks $FileHooks -Stage "intent-removed"
        return [pscustomobject][ordered]@{
            schema = "miho-automation-owner-release-result-v1"
            owner_kind = $expectedOwner.Kind
            owner_instance_id = $expectedOwner.InstanceId
            released = $true
            already_absent = $false
            recovered = [bool]$recovered
        }
    }
    finally {
        if ($ownsCoordinator) { Exit-MihoAutomationCoordinatorV1 -Coordinator $coordinator }
    }
}

function ConvertFrom-MihoHealthJsonV1 {
    param([Parameter(Mandatory = $true)][string]$Json)

    if ($Json.Length -gt $script:MihoHealthMaximumCharactersV1) {
        throw "miho update health output exceeds its supported size."
    }
    try {
        Assert-MihoJsonObjectKeysUniqueV1 -Json $Json
        $health = $Json | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw "miho update health did not return strict unique-key JSON."
    }
    if ($null -eq $health -or $health -isnot [pscustomobject]) {
        throw "miho update health must return one JSON object."
    }
    Assert-MihoExactTopLevelJsonKeysV1 -Json $Json -ExpectedKeys @(
        "schema_version", "healthy", "attempt_id", "checked_games"
    )
    if (-not ($health.schema_version -is [string]) -or $health.schema_version -cne $script:MihoHealthSchemaV1) {
        throw "miho update health returned an unexpected schema."
    }
    if (-not ($health.healthy -is [bool]) -or -not $health.healthy) {
        throw "miho update health did not prove a Boolean healthy=true."
    }
    if (-not ($health.attempt_id -is [string]) -or [string]$health.attempt_id -notmatch '^[A-Za-z0-9_-]{1,96}$') {
        throw "miho update health returned an invalid attempt id."
    }
    if (-not ($health.checked_games -is [System.Array])) {
        throw "miho update health returned an invalid checked-games array."
    }
    $games = @($health.checked_games)
    if ($games.Count -ne 2 -or -not ($games[0] -is [string]) -or -not ($games[1] -is [string]) -or
        @($games | Where-Object { $_ -ceq "hsr" }).Count -ne 1 -or
        @($games | Where-Object { $_ -ceq "zzz" }).Count -ne 1) {
        throw "miho update health did not check exactly HSR and ZZZ."
    }
    return $health
}

function ConvertFrom-MihoBootstrapTransactionJsonV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Json,
        [Parameter(Mandatory = $true)][ValidateSet("begin", "verify", "rollback", "commit", "discard", "finalize")][string]$ExpectedOperation,
        [ValidateSet("", "commit", "discard")][string]$ExpectedCompletedOperation = ""
    )

    if ($Json.Length -gt $script:MihoHealthMaximumCharactersV1) {
        throw "miho workspace bootstrap transaction output exceeds its supported size."
    }
    try {
        Assert-MihoJsonObjectKeysUniqueV1 -Json $Json
        $receipt = $Json | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw "miho workspace bootstrap transaction did not return strict unique-key JSON."
    }
    $expectedKeys = @(
        "schema_version", "operation", "files_verified", "files_restored",
        "files_removed", "transaction_cleaned"
    )
    if ($ExpectedOperation -eq "begin") {
        $expectedKeys += "bootstrap"
    }
    elseif ($ExpectedOperation -eq "finalize") {
        $expectedKeys += @("completed_operation", "completion_marker_removed")
    }
    Assert-MihoExactTopLevelJsonKeysV1 -Json $Json -ExpectedKeys $expectedKeys
    $verifiedCountValid = if ($ExpectedOperation -eq "finalize") {
        ($receipt.files_verified -is [int] -or $receipt.files_verified -is [long]) -and [int64]$receipt.files_verified -in @(0, $script:MihoBootstrapTransactionFileCountV1)
    }
    else {
        ($receipt.files_verified -is [int] -or $receipt.files_verified -is [long]) -and [int64]$receipt.files_verified -eq $script:MihoBootstrapTransactionFileCountV1
    }
    if ($null -eq $receipt -or $receipt -isnot [pscustomobject] -or
        -not ($receipt.schema_version -is [string]) -or [string]$receipt.schema_version -cne $script:MihoBootstrapTransactionReceiptSchemaV1 -or
        -not ($receipt.operation -is [string]) -or [string]$receipt.operation -cne $ExpectedOperation -or
        -not $verifiedCountValid -or
        -not ($receipt.files_restored -is [int] -or $receipt.files_restored -is [long]) -or [int64]$receipt.files_restored -lt 0 -or [int64]$receipt.files_restored -gt $script:MihoBootstrapTransactionFileCountV1 -or
        -not ($receipt.files_removed -is [int] -or $receipt.files_removed -is [long]) -or [int64]$receipt.files_removed -lt 0 -or [int64]$receipt.files_removed -gt $script:MihoBootstrapTransactionFileCountV1 -or
        -not ($receipt.transaction_cleaned -is [bool])) {
        throw "miho workspace bootstrap transaction receipt values are invalid."
    }
    if ($ExpectedOperation -eq "begin") {
        if ($receipt.transaction_cleaned -or $null -eq $receipt.bootstrap -or $receipt.bootstrap -isnot [pscustomobject]) {
            throw "miho workspace bootstrap begin receipt is invalid."
        }
        Assert-MihoObjectExactPropertyNamesV1 -Object $receipt.bootstrap -ExpectedNames @(
            "schema_version", "installed", "upgraded", "preserved", "unchanged", "state_updated"
        ) -Label "miho workspace bootstrap receipt"
        if (-not ($receipt.bootstrap.schema_version -is [string]) -or [string]$receipt.bootstrap.schema_version -cne "miho-release-bootstrap-receipt-v1" -or
            -not ($receipt.bootstrap.state_updated -is [bool])) {
            throw "miho workspace bootstrap begin receipt values are invalid."
        }
        foreach ($name in @("installed", "upgraded", "preserved", "unchanged")) {
            if (-not ($receipt.bootstrap.$name -is [System.Array]) -or @($receipt.bootstrap.$name | Where-Object { $_ -isnot [string] }).Count -ne 0) {
                throw "miho workspace bootstrap begin receipt classifications are invalid."
            }
        }
    }
    elseif ($ExpectedOperation -eq "commit" -or $ExpectedOperation -eq "discard") {
        if (-not $receipt.transaction_cleaned) {
            throw "miho workspace bootstrap cleanup did not durably complete its transaction."
        }
    }
    elseif ($ExpectedOperation -eq "finalize") {
        if ($ExpectedCompletedOperation -cnotin @("commit", "discard") -or
            -not ($receipt.completed_operation -is [string]) -or [string]$receipt.completed_operation -cne $ExpectedCompletedOperation -or
            -not ($receipt.completion_marker_removed -is [bool]) -or -not $receipt.transaction_cleaned -or
            [int64]$receipt.files_restored -ne 0 -or [int64]$receipt.files_removed -ne 0 -or
            (($receipt.completion_marker_removed -and [int64]$receipt.files_verified -ne $script:MihoBootstrapTransactionFileCountV1) -or
            (-not $receipt.completion_marker_removed -and [int64]$receipt.files_verified -ne 0))) {
            throw "miho workspace bootstrap finalize receipt is invalid."
        }
    }
    elseif ($receipt.transaction_cleaned) {
        throw "miho workspace bootstrap transaction was unexpectedly cleaned."
    }
    return $receipt
}

function Normalize-MihoLogonTypeV1 {
    param([AllowEmptyString()][string]$Value)

    if ($Value -eq "Interactive" -or $Value -eq "InteractiveToken") {
        return "InteractiveToken"
    }
    return $Value
}

function Normalize-MihoRunLevelV1 {
    param([AllowEmptyString()][string]$Value)

    if ($Value -eq "LeastPrivilege" -or $Value -eq "Limited") {
        return "Limited"
    }
    if ($Value -eq "HighestAvailable" -or $Value -eq "Highest") {
        return "Highest"
    }
    return $Value
}

function ConvertTo-MihoFingerprintFieldV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value
    )

    $length = (Get-MihoUtf8V1).GetByteCount($Value)
    return $Name + ":" + $length + ":" + $Value
}

function Get-MihoNormalizedActionFingerprintV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Execute,
        [Parameter(Mandatory = $true)][string]$Arguments,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$OwnerSid,
        [Parameter(Mandatory = $true)][string]$LogonType,
        [Parameter(Mandatory = $true)][string]$RunLevel,
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$InstallId
    )

    $fields = @(
        ConvertTo-MihoFingerprintFieldV1 -Name "schema" -Value $script:MihoActionFingerprintSchemaV1
        ConvertTo-MihoFingerprintFieldV1 -Name "execute" -Value ([System.IO.Path]::GetFullPath($Execute).ToLowerInvariant())
        ConvertTo-MihoFingerprintFieldV1 -Name "arguments" -Value $Arguments
        ConvertTo-MihoFingerprintFieldV1 -Name "working_directory" -Value ([System.IO.Path]::GetFullPath($WorkingDirectory).TrimEnd("\", "/").ToLowerInvariant())
        ConvertTo-MihoFingerprintFieldV1 -Name "owner_sid" -Value $OwnerSid.ToUpperInvariant()
        ConvertTo-MihoFingerprintFieldV1 -Name "logon_type" -Value (Normalize-MihoLogonTypeV1 -Value $LogonType)
        ConvertTo-MihoFingerprintFieldV1 -Name "run_level" -Value (Normalize-MihoRunLevelV1 -Value $RunLevel)
        ConvertTo-MihoFingerprintFieldV1 -Name "source" -Value $Source
        ConvertTo-MihoFingerprintFieldV1 -Name "install_id" -Value $InstallId.ToLowerInvariant()
    )
    return Get-MihoSha256TextV1 -Text ([string]::Join([char]10, $fields))
}

function ConvertTo-MihoXmlEscapedV1 {
    param([AllowEmptyString()][string]$Value)

    if ($null -eq $Value) {
        return ""
    }
    return [System.Security.SecurityElement]::Escape($Value)
}

function Get-MihoNextStartBoundaryV1 {
    param([Parameter(Mandatory = $true)][string]$At)

    if ($At -notmatch "^(?:[01][0-9]|2[0-3]):[0-5][0-9]$") {
        throw "At must use 24-hour HH:mm format."
    }
    $hour = [int]$At.Substring(0, 2)
    $minute = [int]$At.Substring(3, 2)
    $now = Get-Date
    $boundary = Get-Date -Year $now.Year -Month $now.Month -Day $now.Day -Hour $hour -Minute $minute -Second 0
    if ($boundary -le $now) {
        $boundary = $boundary.AddDays(1)
    }
    return $boundary.ToString("yyyy-MM-ddTHH:mm:ss")
}

function New-MihoTaskSpecV1 {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][string]$Execute,
        [Parameter(Mandatory = $true)][string]$Arguments,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$OwnerSid,
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$InstallId,
        [ValidateSet("None", "Daily")][string]$TriggerKind = "None",
        [string]$At = "09:30",
        [string]$Description = $script:MihoDescriptionV1,
        [bool]$ReplaceExisting = $false
    )

    if (-not [System.IO.Path]::IsPathRooted($Execute) -or -not [System.IO.Path]::IsPathRooted($WorkingDirectory)) {
        throw "Task Execute and WorkingDirectory must be absolute."
    }
    if ($TriggerKind -eq "Daily") {
        $null = Get-MihoNextStartBoundaryV1 -At $At
    }
    return [pscustomobject][ordered]@{
        TaskName = $TaskName
        TaskPath = $script:MihoTaskPathV1
        Execute = [System.IO.Path]::GetFullPath($Execute)
        Arguments = $Arguments
        WorkingDirectory = [System.IO.Path]::GetFullPath($WorkingDirectory)
        OwnerSid = $OwnerSid
        LogonType = "InteractiveToken"
        RunLevel = "Limited"
        Source = $Source
        InstallId = $InstallId
        TriggerKind = $TriggerKind
        At = $At
        Description = $Description
        MultipleInstancesPolicy = "IgnoreNew"
        StartWhenAvailable = $true
        ExecutionTimeLimit = "PT2H"
        Enabled = $true
        Hidden = $false
        AllowStartOnDemand = $true
        ReplaceExisting = $ReplaceExisting
    }
}

function New-MihoTaskXmlV1 {
    param([Parameter(Mandatory = $true)]$Spec)

    $taskName = ConvertTo-MihoXmlEscapedV1 -Value $Spec.TaskName
    $owner = ConvertTo-MihoXmlEscapedV1 -Value $Spec.OwnerSid
    $source = ConvertTo-MihoXmlEscapedV1 -Value $Spec.Source
    $description = ConvertTo-MihoXmlEscapedV1 -Value $Spec.Description
    $execute = ConvertTo-MihoXmlEscapedV1 -Value $Spec.Execute
    $arguments = ConvertTo-MihoXmlEscapedV1 -Value $Spec.Arguments
    $workingDirectory = ConvertTo-MihoXmlEscapedV1 -Value $Spec.WorkingDirectory
    $triggerXml = ""
    if ($Spec.TriggerKind -eq "Daily") {
        $boundary = Get-MihoNextStartBoundaryV1 -At $Spec.At
        $triggerXml = @"
    <CalendarTrigger>
      <StartBoundary>$boundary</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
"@
    }
    return @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>$description</Description>
    <URI>\$taskName</URI>
    <Source>$source</Source>
  </RegistrationInfo>
  <Triggers>
$triggerXml  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$owner</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$execute</Command>
      <Arguments>$arguments</Arguments>
      <WorkingDirectory>$workingDirectory</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@
}

function Get-MihoXmlNodeTextV1 {
    param(
        [Parameter(Mandatory = $true)][System.Xml.XmlDocument]$Document,
        [Parameter(Mandatory = $true)][System.Xml.XmlNamespaceManager]$Namespaces,
        [Parameter(Mandatory = $true)][string]$XPath,
        [AllowEmptyString()][string]$Default = ""
    )

    $node = $Document.SelectSingleNode($XPath, $Namespaces)
    if ($null -eq $node) {
        return $Default
    }
    return $node.InnerText
}

function Convert-MihoTaskXmlToSnapshotV1 {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][string]$Xml,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Sddl
    )

    try {
        [xml]$document = $Xml
    }
    catch {
        throw "Scheduled task XML is invalid for '$TaskName'."
    }
    $namespaces = New-Object System.Xml.XmlNamespaceManager($document.NameTable)
    $namespaces.AddNamespace("t", "http://schemas.microsoft.com/windows/2004/02/mit/task")
    $actions = $document.SelectNodes("/t:Task/t:Actions/*", $namespaces)
    $principals = $document.SelectNodes("/t:Task/t:Principals/t:Principal", $namespaces)
    $triggers = $document.SelectNodes("/t:Task/t:Triggers/*", $namespaces)
    $startBoundary = Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:Triggers/t:CalendarTrigger/t:StartBoundary"
    $at = ""
    if ($startBoundary -match "T([0-9]{2}:[0-9]{2})") {
        $at = $Matches[1]
    }
    return [pscustomobject][ordered]@{
        TaskName = $TaskName
        TaskPath = $script:MihoTaskPathV1
        RawXml = $Xml
        Sddl = $Sddl
        ActionCount = $actions.Count
        PrincipalCount = $principals.Count
        TriggerCount = $triggers.Count
        Execute = Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:Actions/t:Exec/t:Command"
        Arguments = Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:Actions/t:Exec/t:Arguments"
        WorkingDirectory = Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:Actions/t:Exec/t:WorkingDirectory"
        OwnerSid = Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:Principals/t:Principal/t:UserId"
        LogonType = Normalize-MihoLogonTypeV1 -Value (Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:Principals/t:Principal/t:LogonType")
        RunLevel = Normalize-MihoRunLevelV1 -Value (Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:Principals/t:Principal/t:RunLevel" -Default "LeastPrivilege")
        Source = Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:RegistrationInfo/t:Source"
        Description = Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:RegistrationInfo/t:Description"
        MultipleInstancesPolicy = Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:Settings/t:MultipleInstancesPolicy"
        StartWhenAvailable = (Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:Settings/t:StartWhenAvailable") -eq "true"
        ExecutionTimeLimit = Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:Settings/t:ExecutionTimeLimit"
        Enabled = (Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:Settings/t:Enabled" -Default "true") -eq "true"
        Hidden = (Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:Settings/t:Hidden" -Default "false") -eq "true"
        AllowStartOnDemand = (Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:Settings/t:AllowStartOnDemand" -Default "true") -eq "true"
        CalendarDaysInterval = Get-MihoXmlNodeTextV1 -Document $document -Namespaces $namespaces -XPath "/t:Task/t:Triggers/t:CalendarTrigger/t:ScheduleByDay/t:DaysInterval"
        At = $at
    }
}

function Get-MihoSnapshotActionFingerprintV1 {
    param(
        [Parameter(Mandatory = $true)]$Snapshot,
        [Parameter(Mandatory = $true)][string]$InstallId
    )

    $parameters = @{
        Execute = $Snapshot.Execute
        Arguments = $Snapshot.Arguments
        WorkingDirectory = $Snapshot.WorkingDirectory
        OwnerSid = $Snapshot.OwnerSid
        LogonType = $Snapshot.LogonType
        RunLevel = $Snapshot.RunLevel
        Source = $Snapshot.Source
        InstallId = $InstallId
    }
    return Get-MihoNormalizedActionFingerprintV1 @parameters
}

function Test-MihoTaskMatchesSpecV1 {
    param(
        [Parameter(Mandatory = $true)]$Snapshot,
        [Parameter(Mandatory = $true)]$Spec
    )

    if ($Snapshot.ActionCount -ne 1 -or $Snapshot.PrincipalCount -ne 1) { return $false }
    if (-not [string]::Equals($Snapshot.TaskName, $Spec.TaskName, [System.StringComparison]::Ordinal)) { return $false }
    if (-not (Test-MihoPathEqualV1 -Left $Snapshot.Execute -Right $Spec.Execute)) { return $false }
    if (-not [string]::Equals($Snapshot.Arguments, $Spec.Arguments, [System.StringComparison]::Ordinal)) { return $false }
    if (-not (Test-MihoPathEqualV1 -Left $Snapshot.WorkingDirectory -Right $Spec.WorkingDirectory)) { return $false }
    if (-not [string]::Equals($Snapshot.OwnerSid, $Spec.OwnerSid, [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
    if ((Normalize-MihoLogonTypeV1 -Value $Snapshot.LogonType) -ne "InteractiveToken") { return $false }
    if ((Normalize-MihoRunLevelV1 -Value $Snapshot.RunLevel) -ne "Limited") { return $false }
    if (-not [string]::Equals($Snapshot.Source, $Spec.Source, [System.StringComparison]::Ordinal)) { return $false }
    if (-not [string]::Equals($Snapshot.Description, $Spec.Description, [System.StringComparison]::Ordinal)) { return $false }
    if ($Snapshot.MultipleInstancesPolicy -ne "IgnoreNew" -or -not $Snapshot.StartWhenAvailable) { return $false }
    if ($Snapshot.ExecutionTimeLimit -ne "PT2H" -or -not $Snapshot.Enabled -or $Snapshot.Hidden -or -not $Snapshot.AllowStartOnDemand) { return $false }
    if ($Spec.TriggerKind -eq "None") {
        return ($Snapshot.TriggerCount -eq 0)
    }
    return ($Snapshot.TriggerCount -eq 1 -and $Snapshot.CalendarDaysInterval -eq "1" -and $Snapshot.At -eq $Spec.At)
}

function ConvertTo-MihoWindowsArgumentV1 {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Argument)

    if ($Argument.Length -gt 0 -and $Argument -notmatch '[\s"]') {
        return $Argument
    }
    $builder = New-Object System.Text.StringBuilder
    $null = $builder.Append('"')
    $slashes = 0
    foreach ($character in $Argument.ToCharArray()) {
        if ($character -eq "\") {
            $slashes += 1
            continue
        }
        if ($character -eq '"') {
            $null = $builder.Append("\" * (($slashes * 2) + 1))
            $null = $builder.Append('"')
            $slashes = 0
            continue
        }
        if ($slashes -gt 0) {
            $null = $builder.Append("\" * $slashes)
            $slashes = 0
        }
        $null = $builder.Append($character)
    }
    if ($slashes -gt 0) {
        $null = $builder.Append("\" * ($slashes * 2))
    }
    $null = $builder.Append('"')
    return $builder.ToString()
}

function Invoke-MihoProcessCoreV1 {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][object[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [int]$TimeoutSeconds = 7200
    )

    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $FilePath
    $start.Arguments = [string]::Join(" ", @($Arguments | ForEach-Object { ConvertTo-MihoWindowsArgumentV1 -Argument ([string]$_) }))
    $start.WorkingDirectory = $WorkingDirectory
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.CreateNoWindow = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) {
            throw "Native process did not start: $FilePath"
        }
        $stdout = New-Object System.IO.MemoryStream
        $stderr = New-Object System.IO.MemoryStream
        $stdoutBuffer = New-Object byte[] $script:MihoProcessReadBufferBytesV1
        $stderrBuffer = New-Object byte[] $script:MihoProcessReadBufferBytesV1
        $stdoutTask = $process.StandardOutput.BaseStream.ReadAsync($stdoutBuffer, 0, $stdoutBuffer.Length)
        $stderrTask = $process.StandardError.BaseStream.ReadAsync($stderrBuffer, 0, $stderrBuffer.Length)
        $stdoutDone = $false
        $stderrDone = $false
        $timer = [System.Diagnostics.Stopwatch]::StartNew()
        try {
            while (-not ($stdoutDone -and $stderrDone -and $process.HasExited)) {
                foreach ($streamName in @("stdout", "stderr")) {
                    if ($streamName -eq "stdout") {
                        if ($stdoutDone -or -not $stdoutTask.IsCompleted) { continue }
                        $count = $stdoutTask.GetAwaiter().GetResult()
                        if ($count -eq 0) {
                            $stdoutDone = $true
                            continue
                        }
                        if ($stdout.Length + $count -gt $script:MihoProcessOutputMaximumBytesV1) {
                            try { $process.Kill() } catch {}
                            throw "Native process stdout exceeded its supported size: $FilePath"
                        }
                        $stdout.Write($stdoutBuffer, 0, $count)
                        $stdoutTask = $process.StandardOutput.BaseStream.ReadAsync($stdoutBuffer, 0, $stdoutBuffer.Length)
                    }
                    else {
                        if ($stderrDone -or -not $stderrTask.IsCompleted) { continue }
                        $count = $stderrTask.GetAwaiter().GetResult()
                        if ($count -eq 0) {
                            $stderrDone = $true
                            continue
                        }
                        if ($stderr.Length + $count -gt $script:MihoProcessOutputMaximumBytesV1) {
                            try { $process.Kill() } catch {}
                            throw "Native process stderr exceeded its supported size: $FilePath"
                        }
                        $stderr.Write($stderrBuffer, 0, $count)
                        $stderrTask = $process.StandardError.BaseStream.ReadAsync($stderrBuffer, 0, $stderrBuffer.Length)
                    }
                }
                if ($timer.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
                    try { $process.Kill() } catch {}
                    throw "Native process timed out: $FilePath"
                }
                if (-not ($stdoutDone -and $stderrDone -and $process.HasExited)) {
                    [System.Threading.Thread]::Sleep(10)
                }
            }
            $process.WaitForExit()
            try {
                $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
                $stdoutText = $strictUtf8.GetString($stdout.ToArray())
                $stderrText = $strictUtf8.GetString($stderr.ToArray())
            }
            catch {
                throw "Native process output is not strict UTF-8: $FilePath"
            }
        }
        finally {
            $timer.Stop()
            $stdout.Dispose()
            $stderr.Dispose()
        }
        return [pscustomobject][ordered]@{
            ExitCode = $process.ExitCode
            StdOut = $stdoutText
            StdErr = $stderrText
        }
    }
    finally {
        $process.Dispose()
    }
}

function Get-MihoTaskSddlCoreV1 {
    param([Parameter(Mandatory = $true)][string]$TaskName)

    $service = New-Object -ComObject "Schedule.Service"
    $service.Connect()
    $folder = $service.GetFolder($script:MihoTaskPathV1)
    $task = $folder.GetTask($TaskName)
    return [string]$task.GetSecurityDescriptor(7)
}

function Set-MihoTaskSddlCoreV1 {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][string]$Sddl
    )

    $service = New-Object -ComObject "Schedule.Service"
    $service.Connect()
    $folder = $service.GetFolder($script:MihoTaskPathV1)
    $task = $folder.GetTask($TaskName)
    $task.SetSecurityDescriptor($Sddl, 0)
}

function Get-MihoTaskSnapshotCoreV1 {
    param([Parameter(Mandatory = $true)][string]$TaskName)

    $task = Get-ScheduledTask -TaskName $TaskName -TaskPath $script:MihoTaskPathV1 -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        return $null
    }
    if (@($task).Count -ne 1) {
        throw "Scheduled task identity is ambiguous: $TaskName"
    }
    $xml = Export-ScheduledTask -TaskName $TaskName -TaskPath $script:MihoTaskPathV1 -ErrorAction Stop
    $sddl = Get-MihoTaskSddlCoreV1 -TaskName $TaskName
    if ([string]::IsNullOrWhiteSpace($sddl)) {
        throw "Scheduled task SDDL is unavailable: $TaskName"
    }
    return Convert-MihoTaskXmlToSnapshotV1 -TaskName $TaskName -Xml $xml -Sddl $sddl
}

function Register-MihoTaskCoreV1 {
    param([Parameter(Mandatory = $true)]$Spec)

    $existing = Get-ScheduledTask -TaskName $Spec.TaskName -TaskPath $script:MihoTaskPathV1 -ErrorAction SilentlyContinue
    if ($null -ne $existing -and -not $Spec.ReplaceExisting) {
        throw "Scheduled task already exists: $($Spec.TaskName)"
    }
    $xml = New-MihoTaskXmlV1 -Spec $Spec
    if ($Spec.ReplaceExisting) {
        Register-ScheduledTask -TaskName $Spec.TaskName -TaskPath $script:MihoTaskPathV1 -Xml $xml -Force -ErrorAction Stop | Out-Null
    }
    else {
        Register-ScheduledTask -TaskName $Spec.TaskName -TaskPath $script:MihoTaskPathV1 -Xml $xml -ErrorAction Stop | Out-Null
    }
}

function Remove-MihoTaskCoreV1 {
    param([Parameter(Mandatory = $true)][string]$TaskName)

    $task = Get-ScheduledTask -TaskName $TaskName -TaskPath $script:MihoTaskPathV1 -ErrorAction SilentlyContinue
    if ($null -ne $task) {
        Unregister-ScheduledTask -TaskName $TaskName -TaskPath $script:MihoTaskPathV1 -Confirm:$false -ErrorAction Stop
    }
}

function Restore-MihoTaskCoreV1 {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][string]$Xml,
        [Parameter(Mandatory = $true)][string]$Sddl
    )

    Register-ScheduledTask -TaskName $TaskName -TaskPath $script:MihoTaskPathV1 -Xml $Xml -Force -ErrorAction Stop | Out-Null
    $restored = Get-MihoTaskSnapshotCoreV1 -TaskName $TaskName
    $expectedFingerprint = Get-MihoSddlSemanticFingerprintV1 -Sddl $Sddl
    if ($null -eq $restored -or (Get-MihoSddlSemanticFingerprintV1 -Sddl $restored.Sddl) -ne $expectedFingerprint) {
        Set-MihoTaskSddlCoreV1 -TaskName $TaskName -Sddl $Sddl
        $restored = Get-MihoTaskSnapshotCoreV1 -TaskName $TaskName
    }
    if ($null -eq $restored -or (Get-MihoSddlSemanticFingerprintV1 -Sddl $restored.Sddl) -ne $expectedFingerprint) {
        throw "Scheduled task SDDL restoration could not be verified: $TaskName"
    }
}

function Invoke-MihoTaskRunCoreV1 {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [int]$TimeoutSeconds = 7200
    )

    $task = Get-ScheduledTask -TaskName $TaskName -TaskPath $script:MihoTaskPathV1 -ErrorAction Stop
    $before = Get-ScheduledTaskInfo -InputObject $task -ErrorAction Stop
    $started = [DateTime]::UtcNow
    Start-ScheduledTask -InputObject $task -ErrorAction Stop
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 250
        $currentTask = Get-ScheduledTask -TaskName $TaskName -TaskPath $script:MihoTaskPathV1 -ErrorAction Stop
        $info = Get-ScheduledTaskInfo -InputObject $currentTask -ErrorAction Stop
        $newRun = $info.LastRunTime -gt $before.LastRunTime
        $state = [string]$currentTask.State
        if ($newRun -and $state -eq "Ready") {
            return [pscustomobject][ordered]@{
                TaskName = $TaskName
                RunToken = "$TaskName@$($info.LastRunTime.ToUniversalTime().Ticks)"
                StartedAtUtc = $started.ToString("o")
                Completed = $true
                ExitCode = [int64]$info.LastTaskResult
            }
        }
        if ($state -ne "Ready" -and $state -ne "Running" -and $state -ne "Queued") {
            throw "Candidate scheduled task entered an unknown non-terminal state: $TaskName ($state)"
        }
    }
    try {
        Stop-MihoTaskCoreV1 -TaskName $TaskName -TimeoutSeconds 30
    }
    catch {
        throw "Candidate scheduled task timed out and did not quiesce: $TaskName"
    }
    throw "Candidate scheduled task timed out: $TaskName"
}

function Stop-MihoTaskCoreV1 {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [int]$TimeoutSeconds = 30
    )

    $task = Get-ScheduledTask -TaskName $TaskName -TaskPath $script:MihoTaskPathV1 -ErrorAction Stop
    $state = [string]$task.State
    if ($state -eq "Running" -or $state -eq "Queued") {
        Stop-ScheduledTask -InputObject $task -ErrorAction Stop
    }
    elseif ($state -ne "Ready" -and $state -ne "Disabled") {
        throw "Scheduled task has an unknown non-quiescent state: $TaskName ($state)"
    }
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $task = Get-ScheduledTask -TaskName $TaskName -TaskPath $script:MihoTaskPathV1 -ErrorAction Stop
        $state = [string]$task.State
        if ($state -eq "Ready" -or $state -eq "Disabled") {
            return
        }
        if ($state -ne "Running" -and $state -ne "Queued") {
            throw "Scheduled task entered an unknown state while quiescing: $TaskName ($state)"
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Scheduled task did not quiesce: $TaskName"
}

function New-MihoRealAdapterV1 {
    return @{
        GetTask = { param($name) Get-MihoTaskSnapshotCoreV1 -TaskName $name }
        RegisterTask = { param($spec) Register-MihoTaskCoreV1 -Spec $spec }
        RemoveTask = { param($name) Remove-MihoTaskCoreV1 -TaskName $name }
        RestoreTask = { param($name, $xml, $sddl) Restore-MihoTaskCoreV1 -TaskName $name -Xml $xml -Sddl $sddl }
        RunTask = { param($name, $timeout) Invoke-MihoTaskRunCoreV1 -TaskName $name -TimeoutSeconds $timeout }
        DisableTask = { param($name) Disable-ScheduledTask -TaskName $name -TaskPath $script:MihoTaskPathV1 -ErrorAction Stop | Out-Null }
        StopTask = { param($name, $timeout) Stop-MihoTaskCoreV1 -TaskName $name -TimeoutSeconds $timeout }
        InvokeProcess = {
            param($request)
            Invoke-MihoProcessCoreV1 -FilePath $request.FilePath -Arguments $request.Arguments -WorkingDirectory $request.WorkingDirectory -TimeoutSeconds $request.TimeoutSeconds
        }
    }
}

function Invoke-MihoAdapterV1 {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Adapter,
        [Parameter(Mandatory = $true)][string]$Operation,
        [object[]]$Arguments = @()
    )

    if (-not $Adapter.ContainsKey($Operation) -or $null -eq $Adapter[$Operation]) {
        throw "Automation adapter operation is unavailable: $Operation"
    }
    return & $Adapter[$Operation] @Arguments
}

function Resolve-MihoAutomationRootV1 {
    param([string]$AutomationRoot)

    if ([string]::IsNullOrWhiteSpace($AutomationRoot)) {
        if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw "LOCALAPPDATA is unavailable." }
        $AutomationRoot = Join-Path $env:LOCALAPPDATA "com.miho.endgame.automation"
    }
    return [System.IO.Path]::GetFullPath($AutomationRoot)
}

function Enter-MihoAutomationCoordinatorV1 {
    param([string]$AutomationRoot)

    $root = Resolve-MihoAutomationRootV1 -AutomationRoot $AutomationRoot
    $parent = Split-Path -Parent $root
    if ([string]::IsNullOrWhiteSpace($parent) -or -not (Test-Path -LiteralPath $parent -PathType Container)) {
        throw "Automation coordinator parent is unavailable."
    }
    Assert-MihoNoReparseChainV1 -Path $parent
    $lock = $root + ".coordinator-v1.lock"
    if (Test-Path -LiteralPath $lock) {
        Assert-MihoNoReparseChainV1 -Path $lock
        $item = Get-Item -LiteralPath $lock -Force -ErrorAction Stop
        if ($item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Automation coordinator lock is not a normal file."
        }
    }
    try {
        $stream = [System.IO.File]::Open(
            $lock,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
    }
    catch [System.IO.IOException] {
        throw "Another Miho automation owner coordinator is active."
    }
    return [pscustomobject][ordered]@{
        Root = $root
        Lock = $lock
        ClaimIntent = $root + ".claim-intent-v1.json"
        ReleaseIntent = $root + ".release-intent-v1.json"
        Stream = $stream
    }
}

function Exit-MihoAutomationCoordinatorV1 {
    param($Coordinator)

    if ($null -ne $Coordinator -and $null -ne $Coordinator.Stream) { $Coordinator.Stream.Dispose() }
}

function Assert-MihoAutomationCoordinatorLeaseV1 {
    param(
        [Parameter(Mandatory = $true)]$Coordinator,
        [string]$AutomationRoot
    )

    $expectedRoot = Resolve-MihoAutomationRootV1 -AutomationRoot $AutomationRoot
    $expectedLock = $expectedRoot + ".coordinator-v1.lock"
    if ($null -eq $Coordinator.Root -or $null -eq $Coordinator.Lock -or $null -eq $Coordinator.Stream -or
        -not (Test-MihoPathEqualV1 -Left ([string]$Coordinator.Root) -Right $expectedRoot) -or
        -not (Test-MihoPathEqualV1 -Left ([string]$Coordinator.Lock) -Right $expectedLock) -or
        $Coordinator.Stream -isnot [System.IO.FileStream] -or -not $Coordinator.Stream.CanWrite) {
        throw "Caller-provided automation coordinator lease is invalid or belongs to another root."
    }
}

function Enter-MihoAutomationMutexV1 {
    param([Parameter(Mandatory = $true)]$Paths)

    # This file lease is the cross-session authority. A Local\ named mutex is
    # scoped to one logon session, while the task name and LocalAppData owner
    # state are shared by the same SID across console/RDP sessions.
    Assert-MihoNoReparseChainV1 -Path $Paths.Root
    if (Test-Path -LiteralPath $Paths.Lock) {
        $lockItem = Get-Item -LiteralPath $Paths.Lock -Force -ErrorAction Stop
        if ($lockItem.PSIsContainer -or ($lockItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Automation transaction lock is not a normal file."
        }
    }
    try {
        return [System.IO.File]::Open(
            $Paths.Lock,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
    }
    catch [System.IO.IOException] {
        throw "Another Miho automation transaction is active."
    }
}

function Exit-MihoAutomationMutexV1 {
    param($Mutex)

    if ($null -ne $Mutex) {
        $Mutex.Dispose()
    }
}

function New-MihoUpdateActionArgumentsV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Workspace,
        [Parameter(Mandatory = $true)][string]$ConfigRelative,
        [string]$AttemptId = ""
    )

    if ($Workspace.Contains('"') -or $ConfigRelative.Contains('"')) {
        throw "Task paths must not contain quote characters."
    }
    $arguments = 'update run --workspace "' + $Workspace + '" --config "' + $ConfigRelative + '"'
    if (-not [string]::IsNullOrWhiteSpace($AttemptId)) {
        if ($AttemptId -cnotmatch '^[A-Za-z0-9_-]{1,96}$') {
            throw "Candidate attempt id is invalid."
        }
        $arguments += ' --attempt-id "' + $AttemptId + '"'
    }
    return $arguments
}

function Invoke-MihoCheckedProcessV1 {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Adapter,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][object[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Label,
        [int]$TimeoutSeconds = 7200
    )

    $request = [pscustomobject][ordered]@{
        FilePath = $FilePath
        Arguments = [object[]]$Arguments
        WorkingDirectory = $WorkingDirectory
        TimeoutSeconds = $TimeoutSeconds
    }
    $result = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "InvokeProcess" -Arguments @($request)
    if ($null -eq $result -or -not (Test-MihoObjectPropertyV1 -Object $result -Name "ExitCode")) {
        throw "$Label returned no trustworthy exit result."
    }
    if ([int64]$result.ExitCode -ne 0) {
        $stderr = ""
        if (Test-MihoObjectPropertyV1 -Object $result -Name "StdErr") {
            $stderr = ([string]$result.StdErr).Trim()
        }
        if ($stderr.Length -gt 500) {
            $stderr = $stderr.Substring(0, 500)
        }
        throw "$Label failed with exit code $($result.ExitCode): $stderr"
    }
    return $result
}

function Assert-MihoBootstrapTransactionPathV1 {
    param(
        [Parameter(Mandatory = $true)][string]$TransactionPath,
        [Parameter(Mandatory = $true)]$Paths
    )

    if (-not [System.IO.Path]::IsPathRooted($TransactionPath)) {
        throw "Bootstrap transaction path must be absolute."
    }
    $full = [System.IO.Path]::GetFullPath($TransactionPath)
    $name = [System.IO.Path]::GetFileName($full)
    if (-not (Test-MihoPathEqualV1 -Left (Split-Path -Parent $full) -Right $Paths.Root) -or
        $name -cnotmatch '^bootstrap-transaction-[0-9a-f]{32}$') {
        throw "Bootstrap transaction path is not an exact automation child."
    }
    Assert-MihoNoReparseChainV1 -Path $full
    if (Test-Path -LiteralPath $full) {
        $item = Get-Item -LiteralPath $full -Force -ErrorAction Stop
        if (-not $item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Bootstrap transaction path is not a normal directory."
        }
    }
    return $full
}

function Invoke-MihoBootstrapTransactionV1 {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Adapter,
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string]$Workspace,
        [Parameter(Mandatory = $true)][string]$TransactionPath,
        [Parameter(Mandatory = $true)][ValidateSet("begin", "verify", "rollback", "commit", "discard", "finalize")][string]$Operation,
        [ValidateSet("", "commit", "discard")][string]$CompletedOperation = "",
        [int]$TimeoutSeconds = 7200
    )

    if (($Operation -eq "finalize") -xor ($CompletedOperation -in @("commit", "discard"))) {
        throw "Bootstrap transaction finalize operation binding is invalid."
    }
    $arguments = @("workspace", "bootstrap-transaction", $Operation, "--workspace", $Workspace, "--transaction", $TransactionPath)
    if ($Operation -eq "finalize") { $arguments += @("--completed-operation", $CompletedOperation) }
    $result = Invoke-MihoCheckedProcessV1 `
        -Adapter $Adapter `
        -FilePath $Executable `
        -Arguments $arguments `
        -WorkingDirectory $Workspace `
        -Label "miho workspace bootstrap transaction $Operation" `
        -TimeoutSeconds $TimeoutSeconds
    $receipt = ConvertFrom-MihoBootstrapTransactionJsonV1 -Json ([string]$result.StdOut).Trim() -ExpectedOperation $Operation -ExpectedCompletedOperation $CompletedOperation
    if ($Operation -in @("commit", "discard", "finalize")) {
        if (Test-Path -LiteralPath $TransactionPath) {
            throw "Bootstrap transaction commit left its evidence directory."
        }
    }
    else {
        $null = Resolve-MihoExistingDirectoryV1 -Path $TransactionPath -Label "Bootstrap transaction evidence"
    }
    return $receipt
}

function Get-MihoHealthyAttemptBeforeCandidateV1 {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Adapter,
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string]$Workspace,
        [Parameter(Mandatory = $true)][string]$ConfigRelative,
        [int]$TimeoutSeconds = 7200
    )

    $request = [pscustomobject][ordered]@{
        FilePath = $Executable
        Arguments = [object[]]@("update", "health", "--workspace", $Workspace, "--config", $ConfigRelative)
        WorkingDirectory = $Workspace
        TimeoutSeconds = $TimeoutSeconds
    }
    $result = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "InvokeProcess" -Arguments @($request)
    if ($null -eq $result -or -not (Test-MihoObjectPropertyV1 -Object $result -Name "ExitCode")) {
        throw "Pre-candidate miho update health returned no trustworthy exit result."
    }
    if ([int64]$result.ExitCode -ne 0) {
        return ""
    }
    if (-not (Test-MihoObjectPropertyV1 -Object $result -Name "StdOut")) {
        throw "Pre-candidate miho update health returned no output."
    }
    $health = ConvertFrom-MihoHealthJsonV1 -Json ([string]$result.StdOut).Trim()
    return [string]$health.attempt_id
}

function Invoke-MihoGenerationCheckpointV1 {
    param(
        [hashtable]$FileHooks,
        [Parameter(Mandatory = $true)][string]$Stage,
        [Parameter(Mandatory = $true)][string]$Path
    )

    if ($null -ne $FileHooks -and $FileHooks.ContainsKey("GenerationCheckpoint")) {
        & $FileHooks["GenerationCheckpoint"] $Stage $Path
    }
}

function Copy-MihoFileDurableV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    $input = $null
    $output = $null
    try {
        $input = New-Object System.IO.FileStream(
            $Source,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::Read,
            81920,
            [System.IO.FileOptions]::SequentialScan
        )
        $output = New-Object System.IO.FileStream(
            $Destination,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None,
            81920,
            [System.IO.FileOptions]::WriteThrough
        )
        $input.CopyTo($output, 81920)
        $output.Flush($true)
    }
    finally {
        if ($null -ne $output) { $output.Dispose() }
        if ($null -ne $input) { $input.Dispose() }
    }
}

function Get-MihoGenerationV1 {
    param(
        [Parameter(Mandatory = $true)][string]$SourceCli,
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)][hashtable]$Adapter,
        [Parameter(Mandatory = $true)][string]$Workspace,
        [int]$TimeoutSeconds = 120,
        [switch]$DeferPublish,
        [hashtable]$FileHooks
    )

    $versionResult = Invoke-MihoCheckedProcessV1 -Adapter $Adapter -FilePath $SourceCli -Arguments @("--version") -WorkingDirectory $Workspace -Label "miho version probe" -TimeoutSeconds $TimeoutSeconds
    $version = ([string]$versionResult.StdOut).Trim()
    if ([string]::IsNullOrWhiteSpace($version) -or $version.Contains([char]10) -or $version.Contains([char]13)) {
        throw "miho version output is invalid."
    }
    $versionSlug = [regex]::Replace($version.ToLowerInvariant(), "[^a-z0-9._-]+", "-").Trim("-")
    if ([string]::IsNullOrWhiteSpace($versionSlug)) {
        throw "miho version output cannot form a generation name."
    }
    if ($versionSlug.Length -gt 64) {
        $versionSlug = $versionSlug.Substring(0, 64).TrimEnd("-")
    }
    $sourceHash = Get-MihoFileSha256V1 -Path $SourceCli
    $generation = "$versionSlug-$sourceHash"
    $generationDirectory = Join-Path $Paths.Generations $generation
    $destination = Join-Path $generationDirectory "miho.exe"
    $created = $false
    $stagingDirectory = ""
    if (Test-Path -LiteralPath $generationDirectory) {
        $exact = Assert-MihoExactGenerationDirectoryV1 -Directory $generationDirectory -Sha256 $sourceHash -Paths $Paths
        $generationDirectory = $exact.Directory
        $destination = $exact.Executable
    }
    else {
        $stagingDirectory = Join-Path $Paths.Generations (".staging-" + [guid]::NewGuid().ToString("N"))
        if (-not (Test-MihoPathBelowV1 -Path $stagingDirectory -Parent $Paths.Generations) -or
            -not (Test-MihoPathEqualV1 -Left (Split-Path -Parent $stagingDirectory) -Right $Paths.Generations)) {
            throw "Generation staging path is not an exact automation child."
        }
        $stagingCreated = $false
        try {
            New-Item -ItemType Directory -Path $stagingDirectory -ErrorAction Stop | Out-Null
            $stagingCreated = $true
            Invoke-MihoGenerationCheckpointV1 -FileHooks $FileHooks -Stage "staging-created" -Path $stagingDirectory
            $stagedExecutable = Join-Path $stagingDirectory "miho.exe"
            Copy-MihoFileDurableV1 -Source $SourceCli -Destination $stagedExecutable
            if ((Get-MihoFileSha256V1 -Path $stagedExecutable) -cne $sourceHash) {
                throw "Copied CLI hash mismatch."
            }
            Invoke-MihoGenerationCheckpointV1 -FileHooks $FileHooks -Stage "staging-copied" -Path $stagingDirectory
            if (-not $DeferPublish) {
                Move-MihoDirectoryV1 -Source $stagingDirectory -Destination $generationDirectory -Purpose "generation-publish" -FileHooks $FileHooks
                $stagingCreated = $false
                Invoke-MihoGenerationCheckpointV1 -FileHooks $FileHooks -Stage "generation-published" -Path $generationDirectory
                $exact = Assert-MihoExactGenerationDirectoryV1 -Directory $generationDirectory -Sha256 $sourceHash -Paths $Paths
                $generationDirectory = $exact.Directory
                $destination = $exact.Executable
                $stagingDirectory = ""
            }
        }
        catch {
            $primary = $_
            if ($stagingCreated) {
                try { Remove-MihoPrivateStagingGenerationV1 -Directory $stagingDirectory -Paths $Paths -FileHooks $FileHooks }
                catch { throw "Generation staging failed and cleanup could not be completed. Primary: $($primary.Exception.Message) Cleanup: $($_.Exception.Message)" }
            }
            throw $primary
        }
        $created = $true
    }
    return [pscustomobject][ordered]@{
        Version = $version
        Generation = $generation
        Directory = [System.IO.Path]::GetFullPath($generationDirectory)
        Executable = [System.IO.Path]::GetFullPath($destination)
        Sha256 = $sourceHash
        Created = $created
        StagingDirectory = if ($created -and $DeferPublish) { [System.IO.Path]::GetFullPath($stagingDirectory) } else { "" }
    }
}

function Remove-MihoPrivateStagingGenerationV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [Parameter(Mandatory = $true)]$Paths,
        [hashtable]$FileHooks
    )

    $full = [System.IO.Path]::GetFullPath($Directory)
    if ([System.IO.Path]::GetFileName($full) -cnotmatch '^\.staging-[0-9a-f]{32}$' -or
        -not (Test-MihoPathBelowV1 -Path $full -Parent $Paths.Generations) -or
        -not (Test-MihoPathEqualV1 -Left (Split-Path -Parent $full) -Right $Paths.Generations)) {
        throw "Private generation staging cleanup path is invalid."
    }
    if (-not (Test-Path -LiteralPath $full)) { return }
    $resolved = Resolve-MihoExistingDirectoryV1 -Path $full -Label "Private generation staging directory"
    $entries = @(Get-ChildItem -LiteralPath $resolved -Force -ErrorAction Stop)
    if ($entries.Count -gt 1 -or
        ($entries.Count -eq 1 -and ($entries[0].Name -cne "miho.exe" -or $entries[0].PSIsContainer -or
            ($entries[0].Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0))) {
        throw "Private generation staging cleanup found unknown contents."
    }
    if ($entries.Count -eq 1) {
        Remove-MihoFileV1 -Path $entries[0].FullName -Purpose "pre-journal-staging-executable-cleanup" -FileHooks $FileHooks
    }
    Remove-MihoDirectoryV1 -Path $resolved -Purpose "pre-journal-staging-cleanup" -FileHooks $FileHooks
}

function Publish-MihoGenerationV1 {
    param(
        [Parameter(Mandatory = $true)]$Generation,
        [Parameter(Mandatory = $true)]$Paths,
        [hashtable]$FileHooks
    )

    if (Test-Path -LiteralPath $Generation.Directory) {
        $exact = Assert-MihoExactGenerationDirectoryV1 -Directory $Generation.Directory -Sha256 $Generation.Sha256 -Paths $Paths
        return [pscustomobject][ordered]@{
            Version = $Generation.Version
            Generation = $Generation.Generation
            Directory = $exact.Directory
            Executable = $exact.Executable
            Sha256 = $exact.Sha256
            Created = $false
            StagingDirectory = ""
        }
    }
    $staging = [string]$Generation.StagingDirectory
    if ([string]::IsNullOrWhiteSpace($staging) -or
        [System.IO.Path]::GetFileName($staging) -cnotmatch '^\.staging-[0-9a-f]{32}$' -or
        -not (Test-MihoPathEqualV1 -Left (Split-Path -Parent $staging) -Right $Paths.Generations)) {
        throw "Deferred generation publication lacks an exact staging directory."
    }
    $null = Assert-MihoExactGenerationDirectoryV1 -Directory $staging -Sha256 $Generation.Sha256 -Paths $Paths
    Move-MihoDirectoryV1 -Source $staging -Destination $Generation.Directory -Purpose "generation-publish" -FileHooks $FileHooks
    Invoke-MihoGenerationCheckpointV1 -FileHooks $FileHooks -Stage "generation-published" -Path $Generation.Directory
    $exact = Assert-MihoExactGenerationDirectoryV1 -Directory $Generation.Directory -Sha256 $Generation.Sha256 -Paths $Paths
    return [pscustomobject][ordered]@{
        Version = $Generation.Version
        Generation = $Generation.Generation
        Directory = $exact.Directory
        Executable = $exact.Executable
        Sha256 = $exact.Sha256
        Created = $true
        StagingDirectory = ""
    }
}

function Assert-MihoGenerationOwnedV1 {
    param(
        [Parameter(Mandatory = $true)]$Manifest,
        [Parameter(Mandatory = $true)]$Paths,
        [switch]$RequireOnlyExecutable
    )

    $generation = [string](Get-MihoRequiredPropertyV1 -Object $Manifest -Name "generation")
    $directory = [string](Get-MihoRequiredPropertyV1 -Object $Manifest -Name "generation_path")
    $executable = [string](Get-MihoRequiredPropertyV1 -Object $Manifest -Name "exe_path")
    $hash = [string](Get-MihoRequiredPropertyV1 -Object $Manifest -Name "exe_sha256")
    $expectedDirectory = Join-Path $Paths.Generations $generation
    $expectedExecutable = Join-Path $expectedDirectory "miho.exe"
    if (-not (Test-MihoPathEqualV1 -Left $directory -Right $expectedDirectory) -or -not (Test-MihoPathEqualV1 -Left $executable -Right $expectedExecutable)) {
        throw "Manifest generation escapes the automation generations root."
    }
    if (-not (Test-MihoPathBelowV1 -Path $directory -Parent $Paths.Generations)) {
        throw "Manifest generation is not owned by this automation root."
    }
    $resolvedDirectory = Resolve-MihoExistingDirectoryV1 -Path $directory -Label "Owned CLI generation"
    $resolvedExecutable = Resolve-MihoExistingFileV1 -Path $executable -Label "Owned generation CLI"
    if ((Get-MihoFileSha256V1 -Path $resolvedExecutable) -ne $hash) {
        throw "Owned generation executable has drifted."
    }
    if ($RequireOnlyExecutable) {
        $entries = @(Get-ChildItem -LiteralPath $resolvedDirectory -Force -ErrorAction Stop)
        if ($entries.Count -ne 1 -or $entries[0].Name -ne "miho.exe" -or $entries[0].PSIsContainer) {
            throw "Owned generation contains unrecorded files."
        }
    }
    return [pscustomobject][ordered]@{
        Directory = $resolvedDirectory
        Executable = $resolvedExecutable
        Sha256 = $hash
    }
}

function Remove-MihoExactGenerationV1 {
    param(
        [Parameter(Mandatory = $true)]$Generation,
        [Parameter(Mandatory = $true)]$Paths,
        [string]$Purpose = "generation-cleanup",
        [switch]$CleanupStarted,
        [hashtable]$FileHooks
    )

    if (-not (Test-MihoPathBelowV1 -Path $Generation.Directory -Parent $Paths.Generations) -or -not (Test-MihoPathEqualV1 -Left (Split-Path -Parent $Generation.Directory) -Right $Paths.Generations)) {
        throw "Generation cleanup path is not an exact owned child."
    }
    if (-not (Test-Path -LiteralPath $Generation.Directory)) {
        return
    }
    $resolvedDirectory = Resolve-MihoExistingDirectoryV1 -Path $Generation.Directory -Label "Generation cleanup directory"
    $entries = @(Get-ChildItem -LiteralPath $resolvedDirectory -Force -ErrorAction Stop)
    if ($entries.Count -eq 0) {
        if (-not $CleanupStarted) {
            throw "Empty generation cleanup directory lacks a durable cleanup-started marker."
        }
        Remove-MihoDirectoryV1 -Path $resolvedDirectory -Purpose $Purpose -FileHooks $FileHooks
        return
    }
    $exact = Assert-MihoExactGenerationDirectoryV1 -Directory $Generation.Directory -Sha256 $Generation.Sha256 -Paths $Paths
    Remove-MihoFileV1 -Path $exact.Executable -Purpose "$Purpose-executable" -FileHooks $FileHooks
    Remove-MihoDirectoryV1 -Path $exact.Directory -Purpose $Purpose -FileHooks $FileHooks
}

function Assert-MihoExactGenerationDirectoryV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [Parameter(Mandatory = $true)][string]$Sha256,
        [Parameter(Mandatory = $true)]$Paths
    )

    if ($Sha256 -notmatch '^[0-9a-f]{64}$' -or
        -not (Test-MihoPathBelowV1 -Path $Directory -Parent $Paths.Generations) -or
        -not (Test-MihoPathEqualV1 -Left (Split-Path -Parent $Directory) -Right $Paths.Generations)) {
        throw "Generation evidence is not an exact owned child."
    }
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) {
        throw "Exact generation directory is not available."
    }
    $resolvedDirectory = Resolve-MihoExistingDirectoryV1 -Path $Directory -Label "Exact generation directory"
    $entries = @(Get-ChildItem -LiteralPath $resolvedDirectory -Force -ErrorAction Stop)
    if ($entries.Count -ne 1 -or $entries[0].Name -cne "miho.exe" -or $entries[0].PSIsContainer -or
        ($entries[0].Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Exact generation contains unrecorded or unsafe contents."
    }
    $executable = Resolve-MihoExistingFileV1 -Path (Join-Path $resolvedDirectory "miho.exe") -Label "Exact generation executable"
    if ((Get-MihoFileSha256V1 -Path $executable) -cne $Sha256) {
        throw "Exact generation executable has drifted."
    }
    return [pscustomobject][ordered]@{
        Directory = $resolvedDirectory
        Executable = $executable
        Sha256 = $Sha256
    }
}

function Get-MihoInstalledStateV1 {
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Owner,
        [Parameter(Mandatory = $true)][hashtable]$Adapter,
        [string]$ExpectedWorkspace,
        [string]$ExpectedConfigRelative
    )

    $task = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($Identity.TaskName)
    $manifestRecord = $null
    if (Test-Path -LiteralPath $Paths.Manifest) {
        $manifestRecord = Read-MihoJsonFileV1 -Path $Paths.Manifest -MaximumBytes $script:MihoManifestMaximumBytesV1
    }
    if ($null -ne $task) {
        if ((Normalize-MihoLogonTypeV1 -Value ([string]$task.LogonType)) -ne "InteractiveToken") {
            throw "Canonical task uses a password or non-interactive principal and will not be overwritten."
        }
        if ((Normalize-MihoRunLevelV1 -Value ([string]$task.RunLevel)) -ne "Limited") {
            throw "Canonical task uses highest privileges and will not be overwritten."
        }
    }
    if (($null -eq $task) -xor ($null -eq $manifestRecord)) {
        throw "Canonical task ownership is incomplete or drifted; preserving it unchanged."
    }
    $unboundRecord = Read-MihoUnboundV1 -Paths $Paths -Identity $Identity
    if ($null -eq $task) {
        if ($null -eq $unboundRecord -or -not (Test-MihoOwnerTripletMatchesV1 -Object $unboundRecord.Object -Owner $Owner)) {
            throw "Missing manifest is not a trustworthy never-installed state."
        }
        Assert-MihoOwnedUnboundRootV1 -Paths $Paths -Owner $Owner
        return $null
    }

    if ($null -ne $unboundRecord) { throw "Bound automation state unexpectedly retains an unbound receipt." }

    $manifest = $manifestRecord.Object
    Assert-MihoObjectExactPropertyNamesV1 -Object $manifest -ExpectedNames @(
        "schema", "owner_kind", "owner_instance_id", "owner_epoch", "owner_sid", "install_id",
        "task_name", "task_path", "canonical_workspace", "canonical_config", "config_relative",
        "generation", "version", "generation_path", "exe_path", "exe_sha256", "action_fingerprint",
        "task_xml_sha256", "task_sddl_sha256", "source", "schedule_at"
    ) -Label "Automation ownership manifest"
    Assert-MihoOwnerTripletV1 -Object $manifest -Label "Automation ownership manifest"
    if ([string](Get-MihoRequiredPropertyV1 -Object $manifest -Name "schema") -ne $script:MihoAutomationSchemaV1) {
        throw "Automation manifest schema is not owned by this installer."
    }
    if (-not (Test-MihoOwnerTripletMatchesV1 -Object $manifest -Owner $Owner)) {
        throw "Automation manifest belongs to a different owner authority or epoch."
    }
    $ownerSid = [string](Get-MihoRequiredPropertyV1 -Object $manifest -Name "owner_sid")
    $installId = [string](Get-MihoRequiredPropertyV1 -Object $manifest -Name "install_id")
    $taskName = [string](Get-MihoRequiredPropertyV1 -Object $manifest -Name "task_name")
    $taskPath = [string](Get-MihoRequiredPropertyV1 -Object $manifest -Name "task_path")
    if (-not [string]::Equals($ownerSid, $Identity.OwnerSid, [System.StringComparison]::OrdinalIgnoreCase) -or $taskName -ne $Identity.TaskName -or $taskPath -ne $Identity.TaskPath) {
        throw "Automation manifest owner or canonical task identity has drifted."
    }
    try {
        $parsedInstallId = [guid]::Parse($installId)
        if ($parsedInstallId.ToString("D") -ne $installId.ToLowerInvariant()) {
            throw "non-canonical"
        }
    }
    catch {
        throw "Automation manifest install-id is invalid."
    }
    $workspace = [string](Get-MihoRequiredPropertyV1 -Object $manifest -Name "canonical_workspace")
    $configRelative = [string](Get-MihoRequiredPropertyV1 -Object $manifest -Name "config_relative")
    $configPath = [string](Get-MihoRequiredPropertyV1 -Object $manifest -Name "canonical_config")
    if (-not [System.IO.Path]::IsPathRooted($workspace) -or -not [System.IO.Path]::IsPathRooted($configPath)) {
        throw "Automation manifest workspace/config is not canonical."
    }
    $expectedConfigPath = [System.IO.Path]::GetFullPath((Join-Path $workspace $configRelative))
    if (-not (Test-MihoPathEqualV1 -Left $configPath -Right $expectedConfigPath)) {
        throw "Automation manifest config path has drifted."
    }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedWorkspace) -and -not (Test-MihoPathEqualV1 -Left $workspace -Right $ExpectedWorkspace)) {
        throw "Canonical task belongs to a different workspace."
    }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedConfigRelative) -and $configRelative -ne $ExpectedConfigRelative) {
        throw "Canonical task belongs to a different config."
    }

    $source = [string](Get-MihoRequiredPropertyV1 -Object $manifest -Name "source")
    $expectedSource = "com.miho.endgame/automation-v1/$($Owner.Kind)/$($Owner.InstanceId)/$($Owner.Epoch)/$installId"
    if ($source -ne $expectedSource) {
        throw "Automation source marker has drifted."
    }
    $generationOwned = Assert-MihoGenerationOwnedV1 -Manifest $manifest -Paths $Paths -RequireOnlyExecutable
    $arguments = New-MihoUpdateActionArgumentsV1 -Workspace $workspace -ConfigRelative $configRelative
    $fingerprintParameters = @{
        Execute = $generationOwned.Executable
        Arguments = $arguments
        WorkingDirectory = $workspace
        OwnerSid = $ownerSid
        LogonType = "InteractiveToken"
        RunLevel = "Limited"
        Source = $source
        InstallId = $installId
    }
    $expectedFingerprint = Get-MihoNormalizedActionFingerprintV1 @fingerprintParameters
    if ([string](Get-MihoRequiredPropertyV1 -Object $manifest -Name "action_fingerprint") -ne $expectedFingerprint) {
        throw "Automation manifest action fingerprint has drifted."
    }
    if ((Get-MihoSnapshotActionFingerprintV1 -Snapshot $task -InstallId $installId) -ne $expectedFingerprint) {
        throw "Canonical task action or principal has drifted."
    }
    $scheduleAt = [string](Get-MihoRequiredPropertyV1 -Object $manifest -Name "schedule_at")
    $expectedSpec = New-MihoTaskSpecV1 -TaskName $Identity.TaskName -Execute $generationOwned.Executable -Arguments $arguments -WorkingDirectory $workspace -OwnerSid $ownerSid -Source $source -InstallId $installId -TriggerKind "Daily" -At $scheduleAt -ReplaceExisting $true
    if (-not (Test-MihoTaskMatchesSpecV1 -Snapshot $task -Spec $expectedSpec)) {
        throw "Canonical task definition has drifted."
    }
    if ([string](Get-MihoRequiredPropertyV1 -Object $manifest -Name "task_xml_sha256") -ne (Get-MihoSha256TextV1 -Text $task.RawXml)) {
        throw "Canonical task XML has drifted."
    }
    if ([string](Get-MihoRequiredPropertyV1 -Object $manifest -Name "task_sddl_sha256") -ne (Get-MihoSddlSemanticFingerprintV1 -Sddl $task.Sddl)) {
        throw "Canonical task SDDL has drifted."
    }
    return [pscustomobject][ordered]@{
        Task = $task
        Manifest = $manifest
        ManifestBytes = $manifestRecord.Bytes
        InstallId = $installId
        Workspace = $workspace
        ConfigRelative = $configRelative
        Generation = $generationOwned
    }
}

function New-MihoDesktopAutomationBindingResultV1 {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("absent", "active", "clean-unbound", "busy", "invalid", "conflict")]
        [string]$Status,
        [AllowEmptyString()][string]$ManifestSha256 = "",
        [AllowEmptyString()][string]$ExeSha256 = "",
        [AllowEmptyString()][string]$AuthoritySha256 = "",
        [AllowEmptyString()][string]$UnboundSha256 = "",
        [AllowEmptyString()][string]$TaskXmlSha256 = "",
        [AllowEmptyString()][string]$TaskSddlSha256 = ""
    )

    foreach ($hash in @($ManifestSha256, $ExeSha256, $AuthoritySha256, $UnboundSha256, $TaskXmlSha256, $TaskSddlSha256)) {
        if (-not [string]::IsNullOrEmpty($hash) -and $hash -cnotmatch '^[0-9a-f]{64}$') {
            throw "Desktop automation binding evidence hash is invalid."
        }
    }
    $activeHashes = @($ManifestSha256, $ExeSha256, $AuthoritySha256, $TaskXmlSha256, $TaskSddlSha256)
    if ($Status -ceq "active") {
        if (@($activeHashes | Where-Object { [string]::IsNullOrEmpty($_) }).Count -ne 0 -or
            -not [string]::IsNullOrEmpty($UnboundSha256)) {
            throw "Active desktop automation binding evidence is incomplete."
        }
    }
    elseif ($Status -ceq "clean-unbound") {
        if ([string]::IsNullOrEmpty($AuthoritySha256) -or [string]::IsNullOrEmpty($UnboundSha256) -or
            -not [string]::IsNullOrEmpty($ManifestSha256) -or -not [string]::IsNullOrEmpty($ExeSha256) -or
            -not [string]::IsNullOrEmpty($TaskXmlSha256) -or -not [string]::IsNullOrEmpty($TaskSddlSha256)) {
            throw "Clean-unbound desktop automation binding evidence is incomplete."
        }
    }
    elseif (@($ManifestSha256, $ExeSha256, $AuthoritySha256, $UnboundSha256, $TaskXmlSha256, $TaskSddlSha256 | Where-Object { -not [string]::IsNullOrEmpty($_) }).Count -ne 0) {
        throw "Non-terminal desktop automation binding status must not expose partial evidence."
    }
    return [pscustomobject][ordered]@{
        schema = "miho-desktop-automation-binding-v1"
        status = $Status
        manifest_sha256 = $ManifestSha256
        exe_sha256 = $ExeSha256
        authority_sha256 = $AuthoritySha256
        unbound_sha256 = $UnboundSha256
        task_xml_sha256 = $TaskXmlSha256
        task_sddl_sha256 = $TaskSddlSha256
    }
}

function Get-MihoAutomationPathsReadOnlyV1 {
    param([Parameter(Mandatory = $true)][string]$AutomationRoot)

    $root = [System.IO.Path]::GetFullPath($AutomationRoot)
    Assert-MihoNoReparseChainV1 -Path $root
    $root = Resolve-MihoExistingDirectoryV1 -Path $root -Label "Automation root"
    $generations = Resolve-MihoExistingDirectoryV1 -Path (Join-Path $root "generations") -Label "Automation generations root"
    return [pscustomobject][ordered]@{
        Root = $root
        Generations = $generations
        Manifest = Join-Path $root "automation-owner-v1.json"
        Journal = Join-Path $root "automation-switch-journal-v1.json"
        Authority = Join-Path $root "automation-authority-v1.json"
        Unbound = Join-Path $root "automation-unbound-v1.json"
        ClaimJournal = Join-Path $root "automation-owner-claim-journal-v1.json"
        ClaimIntent = $root + ".claim-intent-v1.json"
        Lock = Join-Path $root ".automation-switch-v1.lock"
        RootCreated = $false
    }
}

function Test-MihoDesktopAutomationBindingV1 {
    param(
        [string]$AutomationRoot,
        [AllowEmptyString()][string]$ExpectedOwnerKind = "",
        [AllowEmptyString()][string]$ExpectedOwnerInstanceId = "",
        [AllowEmptyString()][string]$ExpectedWorkspace = "",
        [Parameter(Mandatory = $true)][bool]$CallerHoldsSwitchLease,
        [hashtable]$Adapter
    )

    # The Desktop caller must already hold the sibling coordinator for the
    # whole call.  Once the root exists it must also hold the pre-existing
    # switch lock.  This probe never creates or opens either lease itself.
    $hasExpectedKind = -not [string]::IsNullOrEmpty($ExpectedOwnerKind)
    $hasExpectedInstance = -not [string]::IsNullOrEmpty($ExpectedOwnerInstanceId)
    if ($hasExpectedKind -xor $hasExpectedInstance) {
        throw "Expected desktop automation owner kind and instance id must be supplied together."
    }
    $expectedOwner = $null
    if ($hasExpectedKind) {
        $expectedOwner = New-MihoExpectedOwnerV1 -OwnerKind $ExpectedOwnerKind -OwnerInstanceId $ExpectedOwnerInstanceId
    }
    $expectedWorkspacePath = ""
    if (-not [string]::IsNullOrWhiteSpace($ExpectedWorkspace)) {
        if (-not [System.IO.Path]::IsPathRooted($ExpectedWorkspace)) {
            throw "Expected desktop automation workspace must be an absolute path."
        }
        $expectedWorkspacePath = [System.IO.Path]::GetFullPath($ExpectedWorkspace)
    }
    $root = Resolve-MihoAutomationRootV1 -AutomationRoot $AutomationRoot
    $parent = Split-Path -Parent $root
    if ([string]::IsNullOrWhiteSpace($parent) -or -not (Test-Path -LiteralPath $parent -PathType Container)) {
        return New-MihoDesktopAutomationBindingResultV1 -Status "invalid"
    }
    try { Assert-MihoNoReparseChainV1 -Path $parent }
    catch { return New-MihoDesktopAutomationBindingResultV1 -Status "invalid" }

    $identity = Get-MihoTaskIdentityV1 -OwnerSid (Get-MihoCurrentSidV1)
    $claimIntentPath = $root + ".claim-intent-v1.json"
    $releaseIntentPath = $root + ".release-intent-v1.json"
    $rootExists = Test-Path -LiteralPath $root
    $switchLockExists = $rootExists -and (Test-Path -LiteralPath (Join-Path $root ".automation-switch-v1.lock"))
    if ($switchLockExists -ne $CallerHoldsSwitchLease) {
        throw "Desktop automation switch lease declaration does not match switch lock existence."
    }

    $intentRecord = $null
    if (Test-Path -LiteralPath $claimIntentPath) {
        try {
            $intentRecord = Read-MihoClaimIntentV1 -Path $claimIntentPath -Identity $identity -AutomationRoot $root
        }
        catch { return New-MihoDesktopAutomationBindingResultV1 -Status "invalid" }
        if ($null -ne $expectedOwner -and
            ([string]$intentRecord.Object.owner_kind -cne $expectedOwner.Kind -or
             [string]$intentRecord.Object.owner_instance_id -cne $expectedOwner.InstanceId)) {
            return New-MihoDesktopAutomationBindingResultV1 -Status "conflict"
        }
    }
    $releaseIntentRecord = $null
    if (Test-Path -LiteralPath $releaseIntentPath) {
        try { $releaseIntentRecord = Read-MihoReleaseIntentV1 -Path $releaseIntentPath -Identity $identity -AutomationRoot $root }
        catch { return New-MihoDesktopAutomationBindingResultV1 -Status "invalid" }
        if ($null -ne $intentRecord) { return New-MihoDesktopAutomationBindingResultV1 -Status "invalid" }
        if ($null -ne $expectedOwner -and
            ([string]$releaseIntentRecord.Object.owner_kind -cne $expectedOwner.Kind -or
             [string]$releaseIntentRecord.Object.owner_instance_id -cne $expectedOwner.InstanceId)) {
            return New-MihoDesktopAutomationBindingResultV1 -Status "conflict"
        }
        return New-MihoDesktopAutomationBindingResultV1 -Status "busy"
    }

    if (-not $rootExists) {
        if ($null -ne $intentRecord) { return New-MihoDesktopAutomationBindingResultV1 -Status "busy" }
        return New-MihoDesktopAutomationBindingResultV1 -Status "absent"
    }
    if ($null -eq $Adapter) { $Adapter = New-MihoRealAdapterV1 }

    try {
        $paths = Get-MihoAutomationPathsReadOnlyV1 -AutomationRoot $root
        if (Test-Path -LiteralPath $paths.Lock) {
            Assert-MihoNoReparseChainV1 -Path $paths.Lock
            $lockItem = Get-Item -LiteralPath $paths.Lock -Force -ErrorAction Stop
            if ($lockItem.PSIsContainer -or ($lockItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Automation transaction lock is not a normal file."
            }
        }
        elseif ($null -eq $intentRecord) {
            throw "Existing automation root lacks its switch lock."
        }

        if ($null -ne $intentRecord) {
            if (Test-Path -LiteralPath $paths.Journal) {
                throw "Owner claim intent overlaps a switch journal."
            }
            $intentOwner = New-MihoExpectedOwnerV1 -OwnerKind ([string]$intentRecord.Object.owner_kind) -OwnerInstanceId ([string]$intentRecord.Object.owner_instance_id)
            if (Test-Path -LiteralPath $paths.ClaimJournal) {
                $claimEvidence = Read-MihoClaimJournalV1 -Paths $paths -Identity $identity -ExpectedOwner $intentOwner
                if ([string]$claimEvidence.Journal.owner_epoch -cne [string]$intentRecord.Object.owner_epoch) {
                    throw "Automation owner claim journal and intent epochs disagree."
                }
            }
            Assert-MihoClaimRootCleanV1 -Paths $paths -Identity $identity -Adapter $Adapter -AllowClaimJournal
            return New-MihoDesktopAutomationBindingResultV1 -Status "busy"
        }
        if (Test-Path -LiteralPath $paths.ClaimJournal) {
            throw "Automation owner claim journal lacks its sibling intent."
        }

        $authorityRecord = Read-MihoAuthorityV1 -Paths $paths -Identity $identity
        if ($null -eq $authorityRecord) { throw "Automation authority is missing." }
        $owner = [pscustomobject][ordered]@{
            Kind = [string]$authorityRecord.Object.owner_kind
            InstanceId = [string]$authorityRecord.Object.owner_instance_id
            Epoch = [string]$authorityRecord.Object.owner_epoch
            AuthorityBytes = $authorityRecord.Bytes
        }
        if ($null -ne $expectedOwner -and
            ($owner.Kind -cne $expectedOwner.Kind -or $owner.InstanceId -cne $expectedOwner.InstanceId)) {
            return New-MihoDesktopAutomationBindingResultV1 -Status "conflict"
        }

        if (Test-Path -LiteralPath $paths.Journal) {
            $journalRecord = Read-MihoJsonFileV1 -Path $paths.Journal -MaximumBytes $script:MihoJournalMaximumBytesV1
            Assert-MihoJournalIdentityV1 -Journal $journalRecord.Object -Identity $identity -Owner $owner -Paths $paths
            return New-MihoDesktopAutomationBindingResultV1 -Status "busy"
        }

        $state = Get-MihoInstalledStateV1 -Paths $paths -Identity $identity -Owner $owner -Adapter $Adapter
        $authoritySha256 = Get-MihoSha256BytesV1 -Bytes $authorityRecord.Bytes
        if ($null -eq $state) {
            $unboundRecord = Read-MihoUnboundV1 -Paths $paths -Identity $identity
            if ($null -eq $unboundRecord -or -not (Test-MihoOwnerTripletMatchesV1 -Object $unboundRecord.Object -Owner $owner)) {
                throw "Clean-unbound automation receipt is unavailable or mismatched."
            }
            return New-MihoDesktopAutomationBindingResultV1 `
                -Status "clean-unbound" `
                -AuthoritySha256 $authoritySha256 `
                -UnboundSha256 (Get-MihoSha256BytesV1 -Bytes $unboundRecord.Bytes)
        }
        $activeGenerationCount = 0
        foreach ($entry in @(Get-ChildItem -LiteralPath $paths.Generations -Force -ErrorAction Stop)) {
            if (Test-MihoPathEqualV1 -Left $entry.FullName -Right $state.Generation.Directory) {
                if (-not $entry.PSIsContainer -or
                    ($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                    throw "Active automation generation is not a normal directory."
                }
                $activeGenerationCount++
                continue
            }
            if (-not $entry.PSIsContainer -or
                [string]$entry.Name -cnotmatch '^\.staging-[0-9a-f]{32}$' -or
                ($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Active automation root contains a foreign generation sibling."
            }
        }
        if ($activeGenerationCount -ne 1) {
            throw "Active automation generation membership is incomplete or ambiguous."
        }
        if (-not [string]::IsNullOrEmpty($expectedWorkspacePath) -and
            -not (Test-MihoPathEqualV1 -Left $state.Workspace -Right $expectedWorkspacePath)) {
            return New-MihoDesktopAutomationBindingResultV1 -Status "conflict"
        }
        return New-MihoDesktopAutomationBindingResultV1 `
            -Status "active" `
            -ManifestSha256 (Get-MihoSha256BytesV1 -Bytes $state.ManifestBytes) `
            -ExeSha256 ([string]$state.Generation.Sha256) `
            -AuthoritySha256 $authoritySha256 `
            -TaskXmlSha256 (Get-MihoSha256TextV1 -Text ([string]$state.Task.RawXml)) `
            -TaskSddlSha256 (Get-MihoSddlSemanticFingerprintV1 -Sddl ([string]$state.Task.Sddl))
    }
    catch {
        return New-MihoDesktopAutomationBindingResultV1 -Status "invalid"
    }
}

function Move-MihoDirectoryV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$Purpose,
        [hashtable]$FileHooks
    )

    if ($null -ne $FileHooks -and $FileHooks.ContainsKey("MoveDirectory")) {
        & $FileHooks["MoveDirectory"] $Source $Destination $Purpose
        return
    }
    Assert-MihoNoReparseChainV1 -Path $Source
    if (Test-Path -LiteralPath $Destination) {
        throw "Directory move destination already exists: $Destination"
    }
    Move-Item -LiteralPath $Source -Destination $Destination -ErrorAction Stop
}

function Remove-MihoDirectoryV1 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Purpose,
        [hashtable]$FileHooks
    )

    if ($null -ne $FileHooks -and $FileHooks.ContainsKey("RemoveDirectory")) {
        & $FileHooks["RemoveDirectory"] $Path $Purpose
        return
    }
    if (Test-Path -LiteralPath $Path) {
        Assert-MihoNoReparseChainV1 -Path $Path
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        if (-not $item.PSIsContainer) {
            throw "Directory cleanup target is not a directory: $Path"
        }
        if (@(Get-ChildItem -LiteralPath $Path -Force -ErrorAction Stop).Count -ne 0) {
            throw "Directory cleanup refused non-empty contents: $Path"
        }
        Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
    }
}

function New-MihoJournalSpecRecordV1 {
    param([Parameter(Mandatory = $true)]$Spec)

    return [pscustomobject][ordered]@{
        task_name = $Spec.TaskName
        execute = $Spec.Execute
        arguments = $Spec.Arguments
        working_directory = $Spec.WorkingDirectory
        owner_sid = $Spec.OwnerSid
        source = $Spec.Source
        install_id = $Spec.InstallId
        trigger_kind = $Spec.TriggerKind
        schedule_at = $Spec.At
        description = $Spec.Description
    }
}

function ConvertFrom-MihoJournalSpecRecordV1 {
    param([Parameter(Mandatory = $true)]$Record)

    Assert-MihoObjectExactPropertyNamesV1 -Object $Record -ExpectedNames @(
        "task_name", "execute", "arguments", "working_directory", "owner_sid",
        "source", "install_id", "trigger_kind", "schedule_at", "description"
    ) -Label "Automation journal task specification"
    foreach ($name in @("task_name", "execute", "arguments", "working_directory", "owner_sid", "source", "install_id", "trigger_kind", "schedule_at", "description")) {
        if (-not ($Record.$name -is [string])) {
            throw "Automation journal task specification values are invalid."
        }
    }
    $parameters = @{
        TaskName = [string](Get-MihoRequiredPropertyV1 -Object $Record -Name "task_name")
        Execute = [string](Get-MihoRequiredPropertyV1 -Object $Record -Name "execute")
        Arguments = [string](Get-MihoRequiredPropertyV1 -Object $Record -Name "arguments")
        WorkingDirectory = [string](Get-MihoRequiredPropertyV1 -Object $Record -Name "working_directory")
        OwnerSid = [string](Get-MihoRequiredPropertyV1 -Object $Record -Name "owner_sid")
        Source = [string](Get-MihoRequiredPropertyV1 -Object $Record -Name "source")
        InstallId = [string](Get-MihoRequiredPropertyV1 -Object $Record -Name "install_id")
        TriggerKind = [string](Get-MihoRequiredPropertyV1 -Object $Record -Name "trigger_kind")
        At = [string](Get-MihoRequiredPropertyV1 -Object $Record -Name "schedule_at")
        Description = [string](Get-MihoRequiredPropertyV1 -Object $Record -Name "description")
        ReplaceExisting = $true
    }
    return New-MihoTaskSpecV1 @parameters
}

function New-MihoJournalV1 {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("install", "uninstall")][string]$Operation,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Owner,
        [Parameter(Mandatory = $true)]$Paths,
        $OldTask,
        [byte[]]$OldManifestBytes,
        $LegacyTask,
        $NewSpec,
        $CandidateSpec,
        [string]$TransactionToken = "",
        [string]$PrepareMode = "",
        [string]$PreparedAtUtc = "",
        [string]$PrepareExpiresAtUtc = "",
        [int64]$CoordinatorPid = 0,
        [string]$CoordinatorStartedAtUtc = "",
        [string]$ExpectedAttemptId = "",
        [bool]$NewGenerationCreated = $false,
        [string]$NewGenerationPath = "",
        [string]$NewGenerationStagingPath = "",
        [string]$NewGeneration = "",
        [string]$NewVersion = "",
        [string]$NewExeSha256 = "",
        [string]$BootstrapWorkspace = "",
        [string]$BootstrapConfigRelative = "",
        [string]$BootstrapCanonicalConfig = "",
        [string]$BootstrapTransactionPath = "",
        [string]$OriginalGenerationPath = "",
        [string]$QuarantinePath = ""
    )

    $oldTaskExisted = $null -ne $OldTask
    $oldTaskXml = ""
    $oldTaskSddl = ""
    $oldTaskXmlHash = ""
    $oldTaskSddlHash = ""
    if ($oldTaskExisted) {
        $oldTaskXmlBytes = (Get-MihoUtf8V1).GetBytes([string]$OldTask.RawXml)
        $oldTaskSddlBytes = (Get-MihoUtf8V1).GetBytes([string]$OldTask.Sddl)
        if ($oldTaskXmlBytes.Length -gt $script:MihoTaskXmlMaximumBytesV1 -or $oldTaskSddlBytes.Length -gt $script:MihoTaskSddlMaximumBytesV1) {
            throw "Canonical task evidence exceeds its supported size."
        }
        $oldTaskXml = ConvertTo-MihoBase64V1 -Bytes $oldTaskXmlBytes
        $oldTaskSddl = ConvertTo-MihoBase64V1 -Bytes $oldTaskSddlBytes
        $oldTaskXmlHash = Get-MihoSha256TextV1 -Text ([string]$OldTask.RawXml)
        $oldTaskSddlHash = Get-MihoSddlSemanticFingerprintV1 -Sddl ([string]$OldTask.Sddl)
    }
    $oldManifestExisted = $null -ne $OldManifestBytes
    $oldManifest = ""
    $oldManifestHash = ""
    if ($oldManifestExisted) {
        if ($OldManifestBytes.Length -gt $script:MihoManifestMaximumBytesV1) {
            throw "Ownership manifest evidence exceeds its supported size."
        }
        $oldManifest = ConvertTo-MihoBase64V1 -Bytes $OldManifestBytes
        $oldManifestHash = Get-MihoSha256BytesV1 -Bytes $OldManifestBytes
    }
    $legacyTaskAuthorized = $null -ne $LegacyTask
    $legacyTaskXml = ""
    $legacyTaskSddl = ""
    $legacyTaskXmlHash = ""
    $legacyTaskSddlHash = ""
    if ($legacyTaskAuthorized) {
        $legacyTaskXmlBytes = (Get-MihoUtf8V1).GetBytes([string]$LegacyTask.RawXml)
        $legacyTaskSddlBytes = (Get-MihoUtf8V1).GetBytes([string]$LegacyTask.Sddl)
        if ($legacyTaskXmlBytes.Length -gt $script:MihoTaskXmlMaximumBytesV1 -or $legacyTaskSddlBytes.Length -gt $script:MihoTaskSddlMaximumBytesV1) {
            throw "Legacy task evidence exceeds its supported size."
        }
        $legacyTaskXml = ConvertTo-MihoBase64V1 -Bytes $legacyTaskXmlBytes
        $legacyTaskSddl = ConvertTo-MihoBase64V1 -Bytes $legacyTaskSddlBytes
        $legacyTaskXmlHash = Get-MihoSha256TextV1 -Text ([string]$LegacyTask.RawXml)
        $legacyTaskSddlHash = Get-MihoSddlSemanticFingerprintV1 -Sddl ([string]$LegacyTask.Sddl)
    }
    $newSpecRecord = $null
    if ($null -ne $NewSpec) {
        $newSpecRecord = New-MihoJournalSpecRecordV1 -Spec $NewSpec
    }
    $candidateSpecRecord = $null
    if ($null -ne $CandidateSpec) {
        $candidateSpecRecord = New-MihoJournalSpecRecordV1 -Spec $CandidateSpec
    }
    return [pscustomobject][ordered]@{
        schema = $script:MihoJournalSchemaV1
        operation = $Operation
        phase = "prepared"
        owner_kind = $Owner.Kind
        owner_instance_id = $Owner.InstanceId
        owner_epoch = $Owner.Epoch
        owner_sid = $Identity.OwnerSid
        task_name = $Identity.TaskName
        task_path = $Identity.TaskPath
        automation_root = $Paths.Root
        old_task_existed = $oldTaskExisted
        old_task_xml_base64 = $oldTaskXml
        old_task_sddl_base64 = $oldTaskSddl
        old_task_xml_sha256 = $oldTaskXmlHash
        old_task_sddl_sha256 = $oldTaskSddlHash
        old_manifest_existed = $oldManifestExisted
        old_manifest_bytes_base64 = $oldManifest
        old_manifest_sha256 = $oldManifestHash
        legacy_task_authorized = $legacyTaskAuthorized
        legacy_task_xml_base64 = $legacyTaskXml
        legacy_task_sddl_base64 = $legacyTaskSddl
        legacy_task_xml_sha256 = $legacyTaskXmlHash
        legacy_task_sddl_sha256 = $legacyTaskSddlHash
        legacy_quiesced = $false
        legacy_removed = $false
        transaction_token = $TransactionToken
        prepare_mode = $PrepareMode
        prepared_at_utc = $PreparedAtUtc
        prepare_expires_at_utc = $PrepareExpiresAtUtc
        coordinator_pid = $CoordinatorPid
        coordinator_started_at_utc = $CoordinatorStartedAtUtc
        new_spec = $newSpecRecord
        candidate_spec = $candidateSpecRecord
        expected_attempt_id = $ExpectedAttemptId
        candidate_run_token = ""
        prior_health_attempt_id = ""
        health_attempt_id = ""
        new_manifest_sha256 = ""
        new_task_xml_sha256 = ""
        new_task_sddl_sha256 = ""
        new_generation_cleanup_started = $false
        retired_generation_cleanup_started = $false
        quarantine_generation_cleanup_started = $false
        new_generation_created = $NewGenerationCreated
        new_generation_path = $NewGenerationPath
        new_generation_staging_path = $NewGenerationStagingPath
        new_generation = $NewGeneration
        new_version = $NewVersion
        new_exe_sha256 = $NewExeSha256
        bootstrap_workspace = $BootstrapWorkspace
        bootstrap_config_relative = $BootstrapConfigRelative
        bootstrap_canonical_config = $BootstrapCanonicalConfig
        bootstrap_transaction_path = $BootstrapTransactionPath
        original_generation_path = $OriginalGenerationPath
        quarantine_path = $QuarantinePath
    }
}

function Write-MihoJournalV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)]$Paths,
        [hashtable]$FileHooks
    )

    $bytes = ConvertTo-MihoJsonBytesV1 -Object $Journal
    if ($bytes.Length -gt $script:MihoJournalMaximumBytesV1) {
        throw "Automation journal exceeds its supported size."
    }
    Write-MihoAtomicBytesV1 -Path $Paths.Journal -Bytes $bytes -Purpose "journal" -FileHooks $FileHooks
}

function Assert-MihoJournalIdentityV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Owner,
        [Parameter(Mandatory = $true)]$Paths
    )

    Assert-MihoObjectExactPropertyNamesV1 -Object $Journal -ExpectedNames @(
        "schema", "operation", "phase", "owner_kind", "owner_instance_id", "owner_epoch", "owner_sid", "task_name", "task_path", "automation_root",
        "old_task_existed", "old_task_xml_base64", "old_task_sddl_base64", "old_task_xml_sha256", "old_task_sddl_sha256",
        "old_manifest_existed", "old_manifest_bytes_base64", "old_manifest_sha256",
        "legacy_task_authorized", "legacy_task_xml_base64", "legacy_task_sddl_base64", "legacy_task_xml_sha256", "legacy_task_sddl_sha256", "legacy_quiesced", "legacy_removed",
        "transaction_token", "prepare_mode", "prepared_at_utc", "prepare_expires_at_utc", "coordinator_pid", "coordinator_started_at_utc",
        "new_spec", "candidate_spec", "expected_attempt_id", "candidate_run_token", "prior_health_attempt_id", "health_attempt_id",
        "new_manifest_sha256", "new_task_xml_sha256", "new_task_sddl_sha256",
        "new_generation_cleanup_started", "retired_generation_cleanup_started", "quarantine_generation_cleanup_started", "new_generation_created",
        "new_generation_path", "new_generation_staging_path", "new_generation", "new_version", "new_exe_sha256", "bootstrap_workspace",
        "bootstrap_config_relative", "bootstrap_canonical_config", "bootstrap_transaction_path",
        "original_generation_path", "quarantine_path"
    ) -Label "Automation journal"
    foreach ($name in @(
        "schema", "operation", "phase", "owner_kind", "owner_instance_id", "owner_epoch", "owner_sid", "task_name", "task_path", "automation_root",
        "old_task_xml_base64", "old_task_sddl_base64", "old_task_xml_sha256", "old_task_sddl_sha256",
        "old_manifest_bytes_base64", "old_manifest_sha256", "legacy_task_xml_base64", "legacy_task_sddl_base64", "legacy_task_xml_sha256", "legacy_task_sddl_sha256",
        "transaction_token", "prepare_mode", "prepared_at_utc", "prepare_expires_at_utc", "coordinator_started_at_utc", "expected_attempt_id", "candidate_run_token", "prior_health_attempt_id", "health_attempt_id",
        "new_manifest_sha256", "new_task_xml_sha256", "new_task_sddl_sha256", "new_generation_path", "new_generation_staging_path",
        "new_generation", "new_version", "new_exe_sha256", "bootstrap_workspace", "bootstrap_config_relative",
        "bootstrap_canonical_config", "bootstrap_transaction_path", "original_generation_path", "quarantine_path"
    )) {
        if (-not ($Journal.$name -is [string])) {
            throw "Automation journal values are invalid."
        }
    }
    if (-not ($Journal.old_task_existed -is [bool]) -or -not ($Journal.old_manifest_existed -is [bool]) -or
        -not ($Journal.legacy_task_authorized -is [bool]) -or -not ($Journal.legacy_quiesced -is [bool]) -or -not ($Journal.legacy_removed -is [bool]) -or
        -not ($Journal.new_generation_cleanup_started -is [bool]) -or
        -not ($Journal.retired_generation_cleanup_started -is [bool]) -or
        -not ($Journal.quarantine_generation_cleanup_started -is [bool]) -or
        -not ($Journal.new_generation_created -is [bool])) {
        throw "Automation journal existence flags are invalid."
    }
    if (-not [bool]$Journal.legacy_task_authorized -and
        (-not [string]::IsNullOrEmpty([string]$Journal.legacy_task_xml_base64) -or
        -not [string]::IsNullOrEmpty([string]$Journal.legacy_task_sddl_base64) -or
        -not [string]::IsNullOrEmpty([string]$Journal.legacy_task_xml_sha256) -or
        -not [string]::IsNullOrEmpty([string]$Journal.legacy_task_sddl_sha256) -or
        [bool]$Journal.legacy_quiesced -or [bool]$Journal.legacy_removed)) {
        throw "Automation journal legacy task evidence is contradictory."
    }
    if ([bool]$Journal.legacy_removed -and -not [bool]$Journal.legacy_quiesced) {
        throw "Automation journal removed legacy task without durable quiesce evidence."
    }
    if ([bool]$Journal.legacy_task_authorized) { $null = Get-MihoJournalLegacyTaskV1 -Journal $Journal }
    if (-not ($Journal.coordinator_pid -is [int] -or $Journal.coordinator_pid -is [long]) -or [int64]$Journal.coordinator_pid -lt 0) {
        throw "Automation journal coordinator pid is invalid."
    }
    if ([string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "schema") -ne $script:MihoJournalSchemaV1) {
        throw "Automation journal schema is foreign."
    }
    Assert-MihoOwnerTripletV1 -Object $Journal -Label "Automation journal"
    if (-not (Test-MihoOwnerTripletMatchesV1 -Object $Journal -Owner $Owner)) {
        throw "Automation journal belongs to a different owner authority or epoch."
    }
    if (-not [string]::Equals([string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "owner_sid"), $Identity.OwnerSid, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Automation journal owner SID is foreign."
    }
    if ([string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "task_name") -ne $Identity.TaskName -or [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "task_path") -ne $Identity.TaskPath) {
        throw "Automation journal task identity is foreign."
    }
    if (-not (Test-MihoPathEqualV1 -Left ([string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "automation_root")) -Right $Paths.Root)) {
        throw "Automation journal root is foreign."
    }
    $operation = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "operation")
    if ($operation -ne "install" -and $operation -ne "uninstall") {
        throw "Automation journal operation is invalid."
    }
    $phase = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "phase")
    $validPhases = if ($operation -eq "install") {
        @(
            "prepared", "old-quiesced", "bootstrap-begin-started", "bootstrap-begun",
            "candidate-registered", "candidate-ran", "candidate-healthy", "bootstrap-verified",
            "candidate-removed", "canonical-replaced", "committed", "bootstrap-commit-started",
            "bootstrap-committed", "bootstrap-rollback-completed", "bootstrap-discard-started",
            "bootstrap-discarded"
        )
    }
    else {
        @("prepared", "generation-quarantined", "committed")
    }
    if ($phase -cnotin $validPhases) {
        throw "Automation journal phase is invalid."
    }
    $newGenerationPath = [string]$Journal.new_generation_path
    $newGenerationStagingPath = [string]$Journal.new_generation_staging_path
    $newGeneration = [string]$Journal.new_generation
    $newExeSha256 = [string]$Journal.new_exe_sha256
    if ($operation -ceq "install") {
        $expectedGenerationPath = Join-Path $Paths.Generations $newGeneration
        if ([string]::IsNullOrWhiteSpace($newGeneration) -or $newGeneration -cmatch '^[.]' -or
            $newGeneration.Contains("\") -or $newGeneration.Contains("/") -or
            $newExeSha256 -cnotmatch '^[0-9a-f]{64}$' -or
            -not (Test-MihoPathEqualV1 -Left $newGenerationPath -Right $expectedGenerationPath) -or
            -not (Test-MihoPathBelowV1 -Path $newGenerationPath -Parent $Paths.Generations)) {
            throw "Automation journal generation identity is invalid."
        }
        if ([bool]$Journal.new_generation_created -xor -not [string]::IsNullOrEmpty($newGenerationStagingPath)) {
            throw "Automation journal generation creation and staging evidence disagree."
        }
        if (-not [string]::IsNullOrEmpty($newGenerationStagingPath) -and
            ([System.IO.Path]::GetFileName($newGenerationStagingPath) -cnotmatch '^\.staging-[0-9a-f]{32}$' -or
             -not (Test-MihoPathBelowV1 -Path $newGenerationStagingPath -Parent $Paths.Generations) -or
             -not (Test-MihoPathEqualV1 -Left (Split-Path -Parent $newGenerationStagingPath) -Right $Paths.Generations) -or
             (Test-MihoPathEqualV1 -Left $newGenerationStagingPath -Right $newGenerationPath))) {
            throw "Automation journal staging generation identity is invalid."
        }
        if (-not [bool]$Journal.new_generation_created) {
            $null = Assert-MihoExactGenerationDirectoryV1 `
                -Directory $newGenerationPath `
                -Sha256 $newExeSha256 `
                -Paths $Paths
        }
    }
    elseif ([bool]$Journal.new_generation_created -or -not [string]::IsNullOrEmpty($newGenerationStagingPath)) {
        throw "Uninstall journal unexpectedly contains generation staging evidence."
    }
}

function Get-MihoJournalOldTaskV1 {
    param([Parameter(Mandatory = $true)]$Journal)

    $oldTaskExisted = Get-MihoRequiredPropertyV1 -Object $Journal -Name "old_task_existed"
    if (-not ($oldTaskExisted -is [bool])) {
        throw "Automation journal old-task flag is invalid."
    }
    if (-not $oldTaskExisted) {
        return $null
    }
    $xmlBytes = ConvertFrom-MihoBase64V1 -Text ([string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "old_task_xml_base64"))
    $sddlBytes = ConvertFrom-MihoBase64V1 -Text ([string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "old_task_sddl_base64"))
    if ($xmlBytes.Length -gt $script:MihoTaskXmlMaximumBytesV1 -or $sddlBytes.Length -gt $script:MihoTaskSddlMaximumBytesV1) {
        throw "Automation journal old task evidence exceeds its supported size."
    }
    $xml = (Get-MihoUtf8V1).GetString($xmlBytes)
    $sddl = (Get-MihoUtf8V1).GetString($sddlBytes)
    if ((Get-MihoSha256TextV1 -Text $xml) -cne [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "old_task_xml_sha256") -or (Get-MihoSddlSemanticFingerprintV1 -Sddl $sddl) -cne [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "old_task_sddl_sha256")) {
        throw "Automation journal old task evidence is corrupt."
    }
    return Convert-MihoTaskXmlToSnapshotV1 -TaskName ([string]$Journal.task_name) -Xml $xml -Sddl $sddl
}

function Get-MihoJournalLegacyTaskV1 {
    param([Parameter(Mandatory = $true)]$Journal)

    if (-not [bool](Get-MihoRequiredPropertyV1 -Object $Journal -Name "legacy_task_authorized")) { return $null }
    $xmlBytes = ConvertFrom-MihoBase64V1 -Text ([string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "legacy_task_xml_base64"))
    $sddlBytes = ConvertFrom-MihoBase64V1 -Text ([string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "legacy_task_sddl_base64"))
    if ($xmlBytes.Length -gt $script:MihoTaskXmlMaximumBytesV1 -or $sddlBytes.Length -gt $script:MihoTaskSddlMaximumBytesV1) {
        throw "Automation journal legacy task evidence exceeds its supported size."
    }
    $xml = (Get-MihoUtf8V1).GetString($xmlBytes)
    $sddl = (Get-MihoUtf8V1).GetString($sddlBytes)
    $xmlHash = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "legacy_task_xml_sha256")
    $sddlHash = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "legacy_task_sddl_sha256")
    if ((Get-MihoSha256TextV1 -Text $xml) -cne $xmlHash -or
        (Get-MihoSddlSemanticFingerprintV1 -Sddl $sddl) -cne $sddlHash) {
        throw "Automation journal legacy task evidence is corrupt."
    }
    $snapshot = Convert-MihoTaskXmlToSnapshotV1 -TaskName $script:MihoLegacyTaskNameV1 -Xml $xml -Sddl $sddl
    if (-not (Test-MihoStrictLegacyTaskV1 -Snapshot $snapshot -OwnerSid ([string]$Journal.owner_sid) -ExpectedXmlSha256 $xmlHash -ExpectedSddlSha256 $sddlHash -AllowEnabled)) {
        throw "Automation journal legacy task evidence is not an authorized legacy task."
    }
    return $snapshot
}

function Test-MihoLegacyQuiescedSnapshotV1 {
    param($Snapshot, $Authorized)

    if ($null -eq $Snapshot -or $null -eq $Authorized -or $Snapshot.Enabled) { return $false }
    if ($Authorized.Enabled) {
        return Test-MihoTaskEquivalentExceptEnabledV1 -Snapshot $Snapshot -Expected $Authorized
    }
    return Test-MihoSnapshotExactlyV1 -Snapshot $Snapshot -Expected $Authorized
}

function Quiesce-MihoJournalLegacyTaskV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)][hashtable]$Adapter,
        [int]$TimeoutSeconds = 30,
        [hashtable]$FileHooks
    )

    $authorized = Get-MihoJournalLegacyTaskV1 -Journal $Journal
    if ($null -eq $authorized) { return $false }
    if ([bool]$Journal.legacy_removed) { throw "Removed legacy task cannot be quiesced again." }
    $current = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($script:MihoLegacyTaskNameV1)
    if ($null -eq $current) { throw "Authorized legacy task disappeared before quiesce." }
    if ([bool]$Journal.legacy_quiesced) {
        if (-not (Test-MihoLegacyQuiescedSnapshotV1 -Snapshot $current -Authorized $authorized)) {
            throw "Quiesced legacy task drifted during recovery."
        }
        return $true
    }
    if (Test-MihoSnapshotExactlyV1 -Snapshot $current -Expected $authorized) {
        if ($current.Enabled) {
            Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "DisableTask" -Arguments @($script:MihoLegacyTaskNameV1) | Out-Null
        }
        Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "StopTask" -Arguments @($script:MihoLegacyTaskNameV1, $TimeoutSeconds) | Out-Null
        $current = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($script:MihoLegacyTaskNameV1)
    }
    elseif (-not (Test-MihoLegacyQuiescedSnapshotV1 -Snapshot $current -Authorized $authorized)) {
        throw "Authorized legacy task changed before quiesce."
    }
    if (-not (Test-MihoLegacyQuiescedSnapshotV1 -Snapshot $current -Authorized $authorized)) {
        throw "Legacy task did not enter the exact quiesced state."
    }
    $Journal.legacy_quiesced = $true
    Write-MihoJournalV1 -Journal $Journal -Paths $Paths -FileHooks $FileHooks
    return $true
}

function Restore-MihoJournalLegacyTaskV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)][hashtable]$Adapter
    )

    $authorized = Get-MihoJournalLegacyTaskV1 -Journal $Journal
    if ($null -eq $authorized) { return }
    if ([bool]$Journal.legacy_removed) { throw "Rollback cannot restore a durably removed legacy task." }
    $current = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($script:MihoLegacyTaskNameV1)
    if (Test-MihoSnapshotExactlyV1 -Snapshot $current -Expected $authorized) { return }
    if (-not (Test-MihoLegacyQuiescedSnapshotV1 -Snapshot $current -Authorized $authorized)) {
        throw "Legacy task drifted before rollback restore."
    }
    Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "RestoreTask" -Arguments @($script:MihoLegacyTaskNameV1, [string]$authorized.RawXml, [string]$authorized.Sddl) | Out-Null
    $restored = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($script:MihoLegacyTaskNameV1)
    if (-not (Test-MihoSnapshotExactlyV1 -Snapshot $restored -Expected $authorized)) {
        throw "Legacy task rollback restore could not be verified."
    }
}

function Remove-MihoJournalLegacyTaskV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)][hashtable]$Adapter,
        [int]$TimeoutSeconds = 30,
        [hashtable]$FileHooks
    )

    $authorized = Get-MihoJournalLegacyTaskV1 -Journal $Journal
    if ($null -eq $authorized) { return $false }
    if (-not [bool]$Journal.legacy_quiesced) { throw "Authorized legacy task was not durably quiesced before removal." }
    $current = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($script:MihoLegacyTaskNameV1)
    if ($null -eq $current) {
        if (-not [bool]$Journal.legacy_removed) {
            $Journal.legacy_removed = $true
            Write-MihoJournalV1 -Journal $Journal -Paths $Paths -FileHooks $FileHooks
        }
        return $true
    }
    if ([bool]$Journal.legacy_removed -or -not (Test-MihoLegacyQuiescedSnapshotV1 -Snapshot $current -Authorized $authorized)) {
        throw "Authorized legacy task drifted before exact removal."
    }
    Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "StopTask" -Arguments @($script:MihoLegacyTaskNameV1, $TimeoutSeconds) | Out-Null
    Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "RemoveTask" -Arguments @($script:MihoLegacyTaskNameV1) | Out-Null
    if ($null -ne (Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($script:MihoLegacyTaskNameV1))) {
        throw "Authorized legacy task removal could not be verified."
    }
    $Journal.legacy_removed = $true
    Write-MihoJournalV1 -Journal $Journal -Paths $Paths -FileHooks $FileHooks
    return $true
}

function Get-MihoJournalOldManifestBytesV1 {
    param([Parameter(Mandatory = $true)]$Journal)

    $oldManifestExisted = Get-MihoRequiredPropertyV1 -Object $Journal -Name "old_manifest_existed"
    if (-not ($oldManifestExisted -is [bool])) {
        throw "Automation journal old-manifest flag is invalid."
    }
    if (-not $oldManifestExisted) {
        return $null
    }
    $bytes = ConvertFrom-MihoBase64V1 -Text ([string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "old_manifest_bytes_base64"))
    if ($bytes.Length -gt $script:MihoManifestMaximumBytesV1) {
        throw "Automation journal old manifest evidence exceeds its supported size."
    }
    if ((Get-MihoSha256BytesV1 -Bytes $bytes) -ne [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "old_manifest_sha256")) {
        throw "Automation journal old manifest evidence is corrupt."
    }
    return $bytes
}

function ConvertFrom-MihoStrictJsonBytesV1 {
    param(
        [Parameter(Mandatory = $true)][byte[]]$Bytes,
        [int64]$MaximumBytes = $script:MihoManifestMaximumBytesV1
    )

    if ($Bytes.Length -gt $MaximumBytes) {
        throw "Automation embedded JSON exceeds its supported size."
    }
    try {
        $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
        $json = $strictUtf8.GetString($Bytes)
        Assert-MihoJsonObjectKeysUniqueV1 -Json $json
        $object = ConvertFrom-MihoJsonTextV1 -Json $json
    }
    catch {
        throw "Automation embedded JSON is not strict unique-key UTF-8 JSON."
    }
    if ($null -eq $object -or $object -isnot [pscustomobject]) {
        throw "Automation embedded JSON must contain one object."
    }
    return $object
}

function Get-MihoExpectedUnboundBytesV1 {
    param(
        [Parameter(Mandatory = $true)][byte[]]$ManifestBytes,
        [Parameter(Mandatory = $true)]$Owner,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Paths
    )

    $manifest = ConvertFrom-MihoStrictJsonBytesV1 -Bytes $ManifestBytes -MaximumBytes $script:MihoManifestMaximumBytesV1
    Assert-MihoObjectExactPropertyNamesV1 -Object $manifest -ExpectedNames @(
        "schema", "owner_kind", "owner_instance_id", "owner_epoch", "owner_sid", "install_id",
        "task_name", "task_path", "canonical_workspace", "canonical_config", "config_relative",
        "generation", "version", "generation_path", "exe_path", "exe_sha256", "action_fingerprint",
        "task_xml_sha256", "task_sddl_sha256", "source", "schedule_at"
    ) -Label "Embedded automation ownership manifest"
    Assert-MihoOwnerTripletV1 -Object $manifest -Label "Embedded automation ownership manifest"
    $installId = [string](Get-MihoRequiredPropertyV1 -Object $manifest -Name "install_id")
    if ([string]$manifest.schema -cne $script:MihoAutomationSchemaV1 -or
        -not (Test-MihoOwnerTripletMatchesV1 -Object $manifest -Owner $Owner) -or
        -not (Test-MihoCanonicalUuidV1 -Value $installId) -or
        -not [string]::Equals([string]$manifest.owner_sid, $Identity.OwnerSid, [System.StringComparison]::OrdinalIgnoreCase) -or
        [string]$manifest.task_name -cne $Identity.TaskName -or [string]$manifest.task_path -cne $Identity.TaskPath) {
        throw "Embedded automation manifest cannot authorize an unbound receipt."
    }
    $record = New-MihoUnboundRecordV1 -Owner $Owner -Identity $Identity -Paths $Paths -PriorInstallId $installId -PriorManifestSha256 (Get-MihoSha256BytesV1 -Bytes $ManifestBytes)
    return ConvertTo-MihoJsonBytesV1 -Object $record
}

function Remove-MihoExpectedUnboundV1 {
    param(
        [Parameter(Mandatory = $true)][byte[]]$ExpectedBytes,
        [Parameter(Mandatory = $true)]$Paths,
        [hashtable]$FileHooks
    )

    if (-not (Test-Path -LiteralPath $Paths.Unbound)) { return }
    $actual = [System.IO.File]::ReadAllBytes($Paths.Unbound)
    if ((Get-MihoSha256BytesV1 -Bytes $actual) -cne (Get-MihoSha256BytesV1 -Bytes $ExpectedBytes)) {
        throw "Automation unbound receipt drifted; refusing mutation."
    }
    Remove-MihoFileV1 -Path $Paths.Unbound -Purpose "unbound-rollback" -FileHooks $FileHooks
}

function Remove-MihoCommittedInstallUnboundV1 {
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Owner,
        [hashtable]$FileHooks
    )

    $record = Read-MihoUnboundV1 -Paths $Paths -Identity $Identity
    if ($null -eq $record) { return $false }
    if (-not (Test-MihoOwnerTripletMatchesV1 -Object $record.Object -Owner $Owner)) {
        throw "Committed install cannot remove a foreign unbound receipt."
    }
    Remove-MihoExpectedUnboundV1 -ExpectedBytes $record.Bytes -Paths $Paths -FileHooks $FileHooks
    if (Test-Path -LiteralPath $Paths.Unbound) {
        throw "Committed install unbound receipt cleanup could not be verified."
    }
    return $true
}

function Test-MihoSnapshotExactlyV1 {
    param(
        $Snapshot,
        $Expected
    )

    if ($null -eq $Snapshot -or $null -eq $Expected) {
        return ($null -eq $Snapshot -and $null -eq $Expected)
    }
    $xmlEqual = (Get-MihoSha256TextV1 -Text ([string]$Snapshot.RawXml)) -eq (Get-MihoSha256TextV1 -Text ([string]$Expected.RawXml))
    $sddlEqual = (Get-MihoSddlSemanticFingerprintV1 -Sddl ([string]$Snapshot.Sddl)) -eq (Get-MihoSddlSemanticFingerprintV1 -Sddl ([string]$Expected.Sddl))
    return ($xmlEqual -and $sddlEqual)
}

function Test-MihoTaskEquivalentExceptEnabledV1 {
    param(
        $Snapshot,
        $Expected
    )

    if ($null -eq $Snapshot -or $null -eq $Expected) { return $false }
    $properties = @(
        "TaskName", "TaskPath", "ActionCount", "PrincipalCount", "TriggerCount",
        "Execute", "Arguments", "WorkingDirectory", "OwnerSid", "LogonType",
        "RunLevel", "Source", "Description", "MultipleInstancesPolicy",
        "StartWhenAvailable", "ExecutionTimeLimit", "Hidden",
        "AllowStartOnDemand", "CalendarDaysInterval", "At"
    )
    foreach ($property in $properties) {
        if (-not [string]::Equals([string]$Snapshot.$property, [string]$Expected.$property, [System.StringComparison]::Ordinal)) {
            return $false
        }
    }
    if ((Get-MihoSddlSemanticFingerprintV1 -Sddl ([string]$Snapshot.Sddl)) -ne (Get-MihoSddlSemanticFingerprintV1 -Sddl ([string]$Expected.Sddl))) {
        return $false
    }
    return ($Expected.Enabled -and -not $Snapshot.Enabled)
}

function Get-MihoJournalPriorStatePreflightV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)][hashtable]$Adapter
    )

    $oldTask = Get-MihoJournalOldTaskV1 -Journal $Journal
    $oldManifestBytes = Get-MihoJournalOldManifestBytesV1 -Journal $Journal
    $currentTask = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($Identity.TaskName)
    $currentIsOld = Test-MihoSnapshotExactlyV1 -Snapshot $currentTask -Expected $oldTask
    $currentIsNew = $false
    if ($null -ne $currentTask -and $null -ne $Journal.new_spec) {
        $newSpec = ConvertFrom-MihoJournalSpecRecordV1 -Record $Journal.new_spec
        $currentIsNew = Test-MihoTaskMatchesSpecV1 -Snapshot $currentTask -Spec $newSpec
    }
    if ($null -ne $currentTask -and [string]$Journal.operation -eq "uninstall" -and (Test-MihoTaskEquivalentExceptEnabledV1 -Snapshot $currentTask -Expected $oldTask)) {
        $currentIsNew = $true
    }
    $currentIsOldDisabled = $null -ne $currentTask -and (Test-MihoTaskEquivalentExceptEnabledV1 -Snapshot $currentTask -Expected $oldTask)
    if ($null -ne $currentTask -and -not $currentIsOld -and -not $currentIsNew -and -not $currentIsOldDisabled) {
        throw "Canonical task drifted during recovery; refusing to overwrite it."
    }

    $currentManifestBytes = $null
    if (Test-Path -LiteralPath $Paths.Manifest) {
        Assert-MihoNoReparseChainV1 -Path $Paths.Manifest
        $currentManifestBytes = [System.IO.File]::ReadAllBytes($Paths.Manifest)
    }
    $currentManifestAllowed = $null -eq $currentManifestBytes
    if ($null -ne $currentManifestBytes -and $null -ne $oldManifestBytes -and (Get-MihoSha256BytesV1 -Bytes $currentManifestBytes) -eq (Get-MihoSha256BytesV1 -Bytes $oldManifestBytes)) {
        $currentManifestAllowed = $true
    }
    $newManifestHash = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "new_manifest_sha256")
    if ($null -ne $currentManifestBytes -and -not [string]::IsNullOrWhiteSpace($newManifestHash) -and (Get-MihoSha256BytesV1 -Bytes $currentManifestBytes) -eq $newManifestHash) {
        $currentManifestAllowed = $true
    }
    if (-not $currentManifestAllowed) {
        throw "Automation manifest drifted during recovery; refusing to overwrite it."
    }

    return [pscustomobject][ordered]@{
        OldTask = $oldTask
        OldManifestBytes = $oldManifestBytes
        CurrentTask = $currentTask
        CurrentIsOld = $currentIsOld
        CurrentIsOldDisabled = $currentIsOldDisabled
        CurrentIsNew = $currentIsNew
    }
}

function Remove-MihoJournalNewCanonicalV1 {
    param(
        [Parameter(Mandatory = $true)]$Preflight,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)][hashtable]$Adapter
    )

    if ($null -ne $Preflight.CurrentTask -and $Preflight.CurrentIsNew -and -not $Preflight.CurrentIsOld -and -not $Preflight.CurrentIsOldDisabled) {
        Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "RemoveTask" -Arguments @($Identity.TaskName) | Out-Null
        if ($null -ne (Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($Identity.TaskName))) {
            throw "New canonical task cleanup could not be verified."
        }
    }
}

function Restore-MihoJournalManifestV1 {
    param(
        [Parameter(Mandatory = $true)]$Preflight,
        [Parameter(Mandatory = $true)]$Paths,
        [hashtable]$FileHooks
    )

    if ($null -ne $Preflight.OldManifestBytes) {
        Write-MihoAtomicBytesV1 -Path $Paths.Manifest -Bytes $Preflight.OldManifestBytes -Purpose "manifest-restore" -FileHooks $FileHooks
    }
    else {
        Remove-MihoFileV1 -Path $Paths.Manifest -Purpose "manifest-restore" -FileHooks $FileHooks
    }
    if ($null -ne $Preflight.OldManifestBytes) {
        if (-not (Test-Path -LiteralPath $Paths.Manifest) -or (Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($Paths.Manifest))) -ne (Get-MihoSha256BytesV1 -Bytes $Preflight.OldManifestBytes)) {
            throw "Automation manifest rollback verification failed."
        }
    }
    elseif (Test-Path -LiteralPath $Paths.Manifest) {
        throw "Automation manifest rollback removal failed."
    }
}

function Restore-MihoJournalTaskLastV1 {
    param(
        [Parameter(Mandatory = $true)]$Preflight,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)][hashtable]$Adapter
    )

    $currentTask = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($Identity.TaskName)
    if ($null -ne $Preflight.OldTask) {
        if (-not (Test-MihoSnapshotExactlyV1 -Snapshot $currentTask -Expected $Preflight.OldTask)) {
            if ($null -ne $currentTask -and -not (Test-MihoTaskEquivalentExceptEnabledV1 -Snapshot $currentTask -Expected $Preflight.OldTask)) {
                throw "Canonical task changed after rollback preflight."
            }
            Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "RestoreTask" -Arguments @($Identity.TaskName, $Preflight.OldTask.RawXml, $Preflight.OldTask.Sddl) | Out-Null
        }
    }
    elseif ($null -ne $currentTask) {
        throw "Unexpected canonical task appeared during rollback."
    }
    $verifiedTask = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($Identity.TaskName)
    if (-not (Test-MihoSnapshotExactlyV1 -Snapshot $verifiedTask -Expected $Preflight.OldTask)) {
        throw "Canonical task rollback verification failed."
    }
}

function Restore-MihoJournalPriorStateV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)][hashtable]$Adapter,
        [hashtable]$FileHooks
    )

    $preflight = Get-MihoJournalPriorStatePreflightV1 -Journal $Journal -Paths $Paths -Identity $Identity -Adapter $Adapter
    Remove-MihoJournalNewCanonicalV1 -Preflight $preflight -Identity $Identity -Adapter $Adapter
    Restore-MihoJournalManifestV1 -Preflight $preflight -Paths $Paths -FileHooks $FileHooks
    Restore-MihoJournalTaskLastV1 -Preflight $preflight -Identity $Identity -Adapter $Adapter
}

function Assert-MihoJournalQuarantineV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)]$Paths
    )

    $original = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "original_generation_path")
    $quarantine = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "quarantine_path")
    if ([string]::IsNullOrWhiteSpace($original) -or [string]::IsNullOrWhiteSpace($quarantine)) {
        throw "Uninstall journal generation paths are missing."
    }
    if (-not (Test-MihoPathBelowV1 -Path $original -Parent $Paths.Generations) -or -not (Test-MihoPathBelowV1 -Path $quarantine -Parent $Paths.Generations)) {
        throw "Uninstall journal generation paths escape the automation root."
    }
    if (-not (Test-MihoPathEqualV1 -Left (Split-Path -Parent $original) -Right $Paths.Generations) -or -not (Test-MihoPathEqualV1 -Left (Split-Path -Parent $quarantine) -Right $Paths.Generations)) {
        throw "Uninstall journal generation paths are not direct children."
    }
    if (-not ([System.IO.Path]::GetFileName($quarantine)).StartsWith(".uninstall-", [System.StringComparison]::Ordinal)) {
        throw "Uninstall journal quarantine name is invalid."
    }
    $oldManifestBytes = Get-MihoJournalOldManifestBytesV1 -Journal $Journal
    if ($null -eq $oldManifestBytes) {
        throw "Uninstall journal lacks its old ownership manifest."
    }
    $oldManifest = ConvertFrom-MihoStrictJsonBytesV1 -Bytes $oldManifestBytes
    $manifestGeneration = [string](Get-MihoRequiredPropertyV1 -Object $oldManifest -Name "generation_path")
    $manifestExecutable = [string](Get-MihoRequiredPropertyV1 -Object $oldManifest -Name "exe_path")
    $manifestHash = [string](Get-MihoRequiredPropertyV1 -Object $oldManifest -Name "exe_sha256")
    if (-not (Test-MihoPathEqualV1 -Left $manifestGeneration -Right $original) -or
        -not (Test-MihoPathEqualV1 -Left $manifestExecutable -Right (Join-Path $original "miho.exe")) -or
        $manifestHash -notmatch '^[0-9a-f]{64}$') {
        throw "Uninstall journal generation evidence does not match its old manifest."
    }
    return [pscustomobject][ordered]@{
        Original = [System.IO.Path]::GetFullPath($original)
        Quarantine = [System.IO.Path]::GetFullPath($quarantine)
        Sha256 = $manifestHash
    }
}

function Remove-MihoJournalQuarantineGenerationV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)]$Paths,
        [hashtable]$FileHooks
    )

    $evidence = Assert-MihoJournalQuarantineV1 -Journal $Journal -Paths $Paths
    if (-not (Test-Path -LiteralPath $evidence.Quarantine)) {
        if ([bool]$Journal.quarantine_generation_cleanup_started) { return }
        throw "Committed uninstall quarantine disappeared before cleanup was authorized."
    }
    if (Test-Path -LiteralPath $evidence.Original) {
        throw "Original generation unexpectedly exists during quarantine cleanup."
    }
    $generation = [pscustomobject]@{
        Directory = $evidence.Quarantine
        Executable = Join-Path $evidence.Quarantine "miho.exe"
        Sha256 = $evidence.Sha256
    }
    if (-not [bool]$Journal.quarantine_generation_cleanup_started) {
        $null = Assert-MihoExactGenerationDirectoryV1 -Directory $generation.Directory -Sha256 $generation.Sha256 -Paths $Paths
        $Journal.quarantine_generation_cleanup_started = $true
        Write-MihoJournalV1 -Journal $Journal -Paths $Paths -FileHooks $FileHooks
    }
    Remove-MihoExactGenerationV1 -Generation $generation -Paths $Paths -Purpose "uninstall-generation-cleanup" -CleanupStarted -FileHooks $FileHooks
}

function Remove-MihoJournalNewGenerationV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)]$Paths,
        [hashtable]$FileHooks
    )

    $directory = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "new_generation_path")
    $stagingDirectory = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "new_generation_staging_path")
    $hash = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "new_exe_sha256")
    if ([string]::IsNullOrWhiteSpace($directory) -or [string]::IsNullOrWhiteSpace($hash)) {
        return
    }
    $oldTask = Get-MihoJournalOldTaskV1 -Journal $Journal
    if ($null -ne $oldTask -and (Test-MihoPathEqualV1 -Left (Split-Path -Parent $oldTask.Execute) -Right $directory)) {
        return
    }
    $stagingExists = -not [string]::IsNullOrEmpty($stagingDirectory) -and (Test-Path -LiteralPath $stagingDirectory)
    $publishedExists = Test-Path -LiteralPath $directory
    if ($stagingExists -and $publishedExists) {
        throw "Both staged and published install generations exist during recovery."
    }
    if ($stagingExists) {
        $generation = [pscustomobject]@{
            Directory = $stagingDirectory
            Executable = Join-Path $stagingDirectory "miho.exe"
            Sha256 = $hash
        }
        if (-not [bool]$Journal.new_generation_cleanup_started) {
            $null = Assert-MihoExactGenerationDirectoryV1 -Directory $generation.Directory -Sha256 $generation.Sha256 -Paths $Paths
            $Journal.new_generation_cleanup_started = $true
            Write-MihoJournalV1 -Journal $Journal -Paths $Paths -FileHooks $FileHooks
        }
        Remove-MihoExactGenerationV1 -Generation $generation -Paths $Paths -Purpose "staged-generation-cleanup" -CleanupStarted -FileHooks $FileHooks
        return
    }
    $generation = [pscustomobject]@{
        Directory = $directory
        Executable = Join-Path $directory "miho.exe"
        Sha256 = $hash
    }
    if (-not $publishedExists) {
        if ([bool]$Journal.new_generation_cleanup_started) { return }
        throw "Journal-bound staged and published generations are both missing before cleanup was authorized."
    }
    if (-not [bool]$Journal.new_generation_cleanup_started) {
        $null = Assert-MihoExactGenerationDirectoryV1 -Directory $generation.Directory -Sha256 $generation.Sha256 -Paths $Paths
        $Journal.new_generation_cleanup_started = $true
        Write-MihoJournalV1 -Journal $Journal -Paths $Paths -FileHooks $FileHooks
    }
    Remove-MihoExactGenerationV1 -Generation $generation -Paths $Paths -Purpose "journal-generation-cleanup" -CleanupStarted -FileHooks $FileHooks
}

function Get-MihoPrepareWindowV1 {
    param([Parameter(Mandatory = $true)]$Journal)

    try {
        $culture = [System.Globalization.CultureInfo]::InvariantCulture
        $styles = [System.Globalization.DateTimeStyles]::RoundtripKind
        $prepared = [DateTimeOffset]::ParseExact([string]$Journal.prepared_at_utc, "o", $culture, $styles)
        $expires = [DateTimeOffset]::ParseExact([string]$Journal.prepare_expires_at_utc, "o", $culture, $styles)
    }
    catch {
        throw "Automation prepare validity window is invalid."
    }
    if ($prepared.Offset -ne [TimeSpan]::Zero -or $expires.Offset -ne [TimeSpan]::Zero -or
        $expires -le $prepared -or ($expires - $prepared).TotalSeconds -gt 3600) {
        throw "Automation prepare validity window is unsafe."
    }
    return [pscustomobject][ordered]@{ Prepared = $prepared; Expires = $expires }
}

function Test-MihoExternalPrepareCoordinatorActiveV1 {
    param([Parameter(Mandatory = $true)]$Journal)

    if ([string]$Journal.prepare_mode -cne "external") { return $false }
    $window = Get-MihoPrepareWindowV1 -Journal $Journal
    if ([DateTimeOffset]::UtcNow -gt $window.Expires) { return $false }
    $pidValue = [int64]$Journal.coordinator_pid
    if ($pidValue -le 0 -or [string]::IsNullOrWhiteSpace([string]$Journal.coordinator_started_at_utc)) { return $false }
    try {
        $process = Get-Process -Id $pidValue -ErrorAction Stop
        $actual = $process.StartTime.ToUniversalTime().ToString("o", [System.Globalization.CultureInfo]::InvariantCulture)
    }
    catch {
        return $false
    }
    return [string]::Equals($actual, [string]$Journal.coordinator_started_at_utc, [System.StringComparison]::Ordinal)
}

function Get-MihoInstallJournalEvidenceV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity
    )

    if ([string]$Journal.operation -cne "install" -or $null -eq $Journal.new_spec -or $null -eq $Journal.candidate_spec) {
        throw "Install journal lacks its exact task specifications."
    }
    $canonical = ConvertFrom-MihoJournalSpecRecordV1 -Record $Journal.new_spec
    $candidate = ConvertFrom-MihoJournalSpecRecordV1 -Record $Journal.candidate_spec
    $workspace = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "bootstrap_workspace")
    $configRelative = Resolve-MihoConfigRelativeV1 -Config ([string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "bootstrap_config_relative"))
    $canonicalConfig = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "bootstrap_canonical_config")
    $transactionToken = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "transaction_token")
    $prepareMode = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "prepare_mode")
    $null = Get-MihoPrepareWindowV1 -Journal $Journal
    $expectedAttemptId = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "expected_attempt_id")
    $transaction = Assert-MihoBootstrapTransactionPathV1 `
        -TransactionPath ([string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "bootstrap_transaction_path")) `
        -Paths $Paths
    $generationPath = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "new_generation_path")
    $generationName = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "new_generation")
    $version = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "new_version")
    $generationHash = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "new_exe_sha256")
    $expectedCanonicalArguments = New-MihoUpdateActionArgumentsV1 -Workspace $workspace -ConfigRelative $configRelative
    $expectedCandidateArguments = New-MihoUpdateActionArgumentsV1 -Workspace $workspace -ConfigRelative $configRelative -AttemptId $expectedAttemptId
    if ($transactionToken -cnotmatch '^[0-9a-f]{32}$' -or $prepareMode -cnotin @("single-call", "external") -or
        ($prepareMode -eq "external" -and ([int64]$Journal.coordinator_pid -le 0 -or [string]::IsNullOrWhiteSpace([string]$Journal.coordinator_started_at_utc))) -or
        $expectedAttemptId -cnotmatch '^[A-Za-z0-9_-]{1,96}$' -or [string]::IsNullOrWhiteSpace($generationName) -or [string]::IsNullOrWhiteSpace($version) -or
        -not [System.IO.Path]::IsPathRooted($workspace) -or -not [System.IO.Path]::IsPathRooted($canonicalConfig) -or
        -not (Test-MihoPathEqualV1 -Left $canonicalConfig -Right ([System.IO.Path]::GetFullPath((Join-Path $workspace $configRelative)))) -or
        -not (Test-MihoPathEqualV1 -Left $workspace -Right $canonical.WorkingDirectory) -or
        -not (Test-MihoPathEqualV1 -Left $workspace -Right $candidate.WorkingDirectory) -or
        -not (Test-MihoPathEqualV1 -Left $canonical.Execute -Right (Join-Path $generationPath "miho.exe")) -or
        -not (Test-MihoPathEqualV1 -Left $candidate.Execute -Right $canonical.Execute) -or
        $generationHash -cnotmatch '^[0-9a-f]{64}$' -or
        -not (Test-MihoPathEqualV1 -Left (Split-Path -Parent $generationPath) -Right $Paths.Generations) -or
        $canonical.TaskName -cne $Identity.TaskName -or $canonical.TriggerKind -cne "Daily" -or
        $candidate.TriggerKind -cne "None" -or
        $candidate.TaskName -cnotmatch ('^' + [regex]::Escape($script:MihoCanonicalTaskPrefixV1 + '-Candidate-' + $Identity.SidHash + '-') + '[0-9a-f]{32}$') -or
        $canonical.OwnerSid -cne $candidate.OwnerSid -or $canonical.InstallId -cne $candidate.InstallId -or $canonical.InstallId -cnotmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' -or
        $canonical.Arguments -cne $expectedCanonicalArguments -or $candidate.Arguments -cne $expectedCandidateArguments -or
        $candidate.Source -cne ($canonical.Source + "/candidate/" + $candidate.TaskName.Substring($candidate.TaskName.Length - 32))) {
        throw "Install journal transaction evidence is inconsistent."
    }
    $workspace = Resolve-MihoExistingDirectoryV1 -Path $workspace -Label "Journal bootstrap workspace"
    if (Test-Path -LiteralPath $generationPath) {
        $exactGeneration = Assert-MihoExactGenerationDirectoryV1 -Directory $generationPath -Sha256 $generationHash -Paths $Paths
    }
    elseif ([string]$Journal.phase -ceq "prepared" -and [bool]$Journal.new_generation_created) {
        $stagingPath = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "new_generation_staging_path")
        $null = Assert-MihoExactGenerationDirectoryV1 -Directory $stagingPath -Sha256 $generationHash -Paths $Paths
        $exactGeneration = [pscustomobject][ordered]@{
            Directory = [System.IO.Path]::GetFullPath($generationPath)
            Executable = [System.IO.Path]::GetFullPath((Join-Path $generationPath "miho.exe"))
            Sha256 = $generationHash
        }
    }
    else {
        throw "Install journal generation is missing after publication should have completed."
    }
    $generation = [pscustomobject][ordered]@{
        Version = $version
        Generation = $generationName
        Directory = $exactGeneration.Directory
        Executable = $exactGeneration.Executable
        Sha256 = $exactGeneration.Sha256
        Created = $false
    }
    return [pscustomobject][ordered]@{
        CanonicalSpec = $canonical
        CandidateSpec = $candidate
        Workspace = $workspace
        ConfigRelative = $configRelative
        CanonicalConfig = $canonicalConfig
        TransactionToken = $transactionToken
        PrepareMode = $prepareMode
        ExpectedAttemptId = $expectedAttemptId
        TransactionPath = $transaction
        Generation = $generation
    }
}

function Remove-MihoJournalCandidateV1 {
    param(
        [Parameter(Mandatory = $true)]$Evidence,
        [Parameter(Mandatory = $true)][hashtable]$Adapter,
        [int]$QuiesceTimeoutSeconds = 30
    )

    $candidate = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($Evidence.CandidateSpec.TaskName)
    if ($null -eq $candidate) {
        return $false
    }
    if (-not (Test-MihoTaskMatchesSpecV1 -Snapshot $candidate -Spec $Evidence.CandidateSpec)) {
        throw "Candidate task drifted during recovery; refusing to remove it."
    }
    Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "StopTask" -Arguments @($Evidence.CandidateSpec.TaskName, $QuiesceTimeoutSeconds) | Out-Null
    $candidate = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($Evidence.CandidateSpec.TaskName)
    if ($null -eq $candidate -or -not (Test-MihoTaskMatchesSpecV1 -Snapshot $candidate -Spec $Evidence.CandidateSpec)) {
        throw "Candidate task changed while being quiesced."
    }
    Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "RemoveTask" -Arguments @($Evidence.CandidateSpec.TaskName) | Out-Null
    if ($null -ne (Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($Evidence.CandidateSpec.TaskName))) {
        throw "Candidate task cleanup could not be verified."
    }
    return $true
}

function Assert-MihoCommittedInstallJournalV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Evidence,
        [Parameter(Mandatory = $true)][hashtable]$Adapter
    )

    if (Test-Path -LiteralPath $Evidence.TransactionPath) {
        throw "Committed bootstrap transaction evidence unexpectedly remains."
    }
    $null = Remove-MihoJournalCandidateV1 -Evidence $Evidence -Adapter $Adapter
    $task = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($Identity.TaskName)
    if ($null -eq $task -or -not (Test-MihoTaskMatchesSpecV1 -Snapshot $task -Spec $Evidence.CanonicalSpec)) {
        throw "Committed install journal no longer matches the canonical task."
    }
    $expectedXmlHash = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "new_task_xml_sha256")
    $expectedSddlHash = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "new_task_sddl_sha256")
    $manifestHash = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "new_manifest_sha256")
    if ($expectedXmlHash -cnotmatch '^[0-9a-f]{64}$' -or $expectedSddlHash -cnotmatch '^[0-9a-f]{64}$' -or $manifestHash -cnotmatch '^[0-9a-f]{64}$' -or
        (Get-MihoSha256TextV1 -Text ([string]$task.RawXml)) -cne $expectedXmlHash -or
        ((Get-MihoSddlSemanticFingerprintV1 -Sddl ([string]$task.Sddl)) -cne $expectedSddlHash)) {
        throw "Committed install task XML or SDDL has drifted."
    }
    if (-not (Test-Path -LiteralPath $Paths.Manifest)) {
        throw "Committed install journal lacks its ownership manifest."
    }
    Assert-MihoNoReparseChainV1 -Path $Paths.Manifest
    $metadata = Get-Item -LiteralPath $Paths.Manifest -Force -ErrorAction Stop
    if ($metadata.PSIsContainer -or [int64]$metadata.Length -gt $script:MihoManifestMaximumBytesV1 -or
        (Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($Paths.Manifest))) -cne $manifestHash) {
        throw "Committed install manifest has drifted."
    }
}

function Remove-MihoJournalRetiredGenerationV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)]$Paths,
        [hashtable]$FileHooks
    )

    $oldManifestBytes = Get-MihoJournalOldManifestBytesV1 -Journal $Journal
    if ($null -eq $oldManifestBytes) { return $false }
    $oldManifest = ConvertFrom-MihoStrictJsonBytesV1 -Bytes $oldManifestBytes
    $oldGenerationName = [string](Get-MihoRequiredPropertyV1 -Object $oldManifest -Name "generation")
    $oldGenerationPath = [string](Get-MihoRequiredPropertyV1 -Object $oldManifest -Name "generation_path")
    $oldExecutablePath = [string](Get-MihoRequiredPropertyV1 -Object $oldManifest -Name "exe_path")
    $oldHash = [string](Get-MihoRequiredPropertyV1 -Object $oldManifest -Name "exe_sha256")
    $expectedOldPath = Join-Path $Paths.Generations $oldGenerationName
    if ($oldHash -cnotmatch '^[0-9a-f]{64}$' -or
        -not (Test-MihoPathEqualV1 -Left $oldGenerationPath -Right $expectedOldPath) -or
        -not (Test-MihoPathEqualV1 -Left $oldExecutablePath -Right (Join-Path $expectedOldPath "miho.exe")) -or
        -not (Test-MihoPathBelowV1 -Path $oldGenerationPath -Parent $Paths.Generations)) {
        throw "Retired generation evidence is not an exact owned child."
    }
    $oldGeneration = [pscustomobject]@{ Directory = $oldGenerationPath; Executable = $oldExecutablePath; Sha256 = $oldHash }
    $newPath = [string](Get-MihoRequiredPropertyV1 -Object $Journal -Name "new_generation_path")
    if (Test-MihoPathEqualV1 -Left $oldGeneration.Directory -Right $newPath) { return $false }
    if (-not (Test-Path -LiteralPath $oldGeneration.Directory)) {
        if ([bool]$Journal.retired_generation_cleanup_started) { return $true }
        throw "Retired generation disappeared before cleanup was authorized."
    }
    if (-not [bool]$Journal.retired_generation_cleanup_started) {
        $null = Assert-MihoExactGenerationDirectoryV1 -Directory $oldGeneration.Directory -Sha256 $oldGeneration.Sha256 -Paths $Paths
        $Journal.retired_generation_cleanup_started = $true
        Write-MihoJournalV1 -Journal $Journal -Paths $Paths -FileHooks $FileHooks
    }
    Remove-MihoExactGenerationV1 -Generation $oldGeneration -Paths $Paths -Purpose "retired-generation-cleanup" -CleanupStarted -FileHooks $FileHooks
    return $true
}

function Complete-MihoCommittedInstallJournalV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Owner,
        [Parameter(Mandatory = $true)]$Evidence,
        [Parameter(Mandatory = $true)][hashtable]$Adapter,
        [hashtable]$FileHooks
    )

    Assert-MihoCommittedInstallJournalV1 -Journal $Journal -Paths $Paths -Identity $Identity -Evidence $Evidence -Adapter $Adapter
    $null = Remove-MihoCommittedInstallUnboundV1 -Paths $Paths -Identity $Identity -Owner $Owner -FileHooks $FileHooks
    $legacyRemoved = Remove-MihoJournalLegacyTaskV1 -Journal $Journal -Paths $Paths -Adapter $Adapter -FileHooks $FileHooks
    $retiredRemoved = $false
    $cleanupWarning = ""
    try {
        $retiredRemoved = Remove-MihoJournalRetiredGenerationV1 -Journal $Journal -Paths $Paths -FileHooks $FileHooks
    }
    catch {
        $cleanupWarning = "Exact retired generation cleanup was preserved: $($_.Exception.Message)"
        return [pscustomobject][ordered]@{
            recovered = $true
            committed = $true
            retired_generation_removed = $false
            legacy_removed = [bool]$legacyRemoved
            retained_transaction = ""
            warning = $cleanupWarning
        }
    }
    Remove-MihoFileV1 -Path $Paths.Journal -Purpose "journal-commit-cleanup" -FileHooks $FileHooks
    return [pscustomobject][ordered]@{
        recovered = $true
        committed = $true
        retired_generation_removed = $retiredRemoved
        legacy_removed = [bool]$legacyRemoved
        retained_transaction = ""
        warning = $cleanupWarning
    }
}

function Rollback-MihoInstallJournalV1 {
    param(
        [Parameter(Mandatory = $true)]$Journal,
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Owner,
        [Parameter(Mandatory = $true)][hashtable]$Adapter,
        [int]$ProcessTimeoutSeconds = 7200,
        [hashtable]$FileHooks
    )

    $phase = [string]$Journal.phase
    $evidence = Get-MihoInstallJournalEvidenceV1 -Journal $Journal -Paths $Paths -Identity $Identity
    if ($phase -eq "bootstrap-commit-started") {
        $null = Invoke-MihoBootstrapTransactionV1 -Adapter $Adapter -Executable $evidence.Generation.Executable -Workspace $evidence.Workspace -TransactionPath $evidence.TransactionPath -Operation "commit" -TimeoutSeconds $ProcessTimeoutSeconds
        $Journal.phase = "bootstrap-committed"
        Write-MihoJournalV1 -Journal $Journal -Paths $Paths -FileHooks $FileHooks
        $phase = "bootstrap-committed"
    }
    if ($phase -eq "bootstrap-committed") {
        $null = Invoke-MihoBootstrapTransactionV1 -Adapter $Adapter -Executable $evidence.Generation.Executable -Workspace $evidence.Workspace -TransactionPath $evidence.TransactionPath -Operation "finalize" -CompletedOperation "commit" -TimeoutSeconds $ProcessTimeoutSeconds
        return Complete-MihoCommittedInstallJournalV1 -Journal $Journal -Paths $Paths -Identity $Identity -Owner $Owner -Evidence $evidence -Adapter $Adapter -FileHooks $FileHooks
    }

    $preflight = Get-MihoJournalPriorStatePreflightV1 -Journal $Journal -Paths $Paths -Identity $Identity -Adapter $Adapter
    $null = Remove-MihoJournalCandidateV1 -Evidence $evidence -Adapter $Adapter
    Remove-MihoJournalNewCanonicalV1 -Preflight $preflight -Identity $Identity -Adapter $Adapter

    $retainedTransaction = ""
    $begunPhases = @(
        "bootstrap-begun", "candidate-registered", "candidate-ran", "candidate-healthy",
        "bootstrap-verified", "candidate-removed", "canonical-replaced", "committed", "bootstrap-commit-started"
    )
    $discardPhases = @("bootstrap-rollback-completed", "bootstrap-discard-started", "bootstrap-discarded")
    if ($phase -notin $discardPhases) {
        $transactionExists = Test-Path -LiteralPath $evidence.TransactionPath
        if ($transactionExists) {
            if ($phase -notin (@("bootstrap-begin-started") + $begunPhases)) {
                throw "Bootstrap transaction evidence appeared before begin."
            }
            $null = Invoke-MihoBootstrapTransactionV1 -Adapter $Adapter -Executable $evidence.Generation.Executable -Workspace $evidence.Workspace -TransactionPath $evidence.TransactionPath -Operation "rollback" -TimeoutSeconds $ProcessTimeoutSeconds
            $Journal.phase = "bootstrap-rollback-completed"
            Write-MihoJournalV1 -Journal $Journal -Paths $Paths -FileHooks $FileHooks
            $phase = "bootstrap-rollback-completed"
        }
        elseif ($phase -in $begunPhases) {
            throw "Bootstrap transaction evidence is missing; refusing partial recovery."
        }
    }
    if ($phase -eq "bootstrap-rollback-completed") {
        $Journal.phase = "bootstrap-discard-started"
        Write-MihoJournalV1 -Journal $Journal -Paths $Paths -FileHooks $FileHooks
        $phase = "bootstrap-discard-started"
    }
    if ($phase -eq "bootstrap-discard-started") {
        $null = Invoke-MihoBootstrapTransactionV1 -Adapter $Adapter -Executable $evidence.Generation.Executable -Workspace $evidence.Workspace -TransactionPath $evidence.TransactionPath -Operation "discard" -TimeoutSeconds $ProcessTimeoutSeconds
        $Journal.phase = "bootstrap-discarded"
        Write-MihoJournalV1 -Journal $Journal -Paths $Paths -FileHooks $FileHooks
        $phase = "bootstrap-discarded"
    }
    if ($phase -eq "bootstrap-discarded") {
        $null = Invoke-MihoBootstrapTransactionV1 -Adapter $Adapter -Executable $evidence.Generation.Executable -Workspace $evidence.Workspace -TransactionPath $evidence.TransactionPath -Operation "finalize" -CompletedOperation "discard" -TimeoutSeconds $ProcessTimeoutSeconds
    }

    Restore-MihoJournalManifestV1 -Preflight $preflight -Paths $Paths -FileHooks $FileHooks
    Restore-MihoJournalTaskLastV1 -Preflight $preflight -Identity $Identity -Adapter $Adapter
    Restore-MihoJournalLegacyTaskV1 -Journal $Journal -Adapter $Adapter
    Remove-MihoJournalNewGenerationV1 -Journal $Journal -Paths $Paths -FileHooks $FileHooks
    $rollbackReceipt = [pscustomobject][ordered]@{
        schema = "miho-automation-rollback-receipt-v1"
        transaction_token = [string]$Journal.transaction_token
        owner_kind = $Owner.Kind
        owner_instance_id = $Owner.InstanceId
        owner_epoch = $Owner.Epoch
        owner_sid = $Identity.OwnerSid
        task_name = $Identity.TaskName
        automation_root = $Paths.Root
        retained_bootstrap_transaction = $retainedTransaction
    }
    $rollbackReceiptPath = Join-Path $Paths.Root ("rollback-receipt-" + [string]$Journal.transaction_token + ".json")
    if (Test-Path -LiteralPath $rollbackReceiptPath) {
        $existingRollback = Get-MihoRollbackReceiptV1 -TransactionToken ([string]$Journal.transaction_token) -Paths $Paths -Identity $Identity -Owner $Owner
        if ($null -eq $existingRollback -or [string]$existingRollback.Object.retained_bootstrap_transaction -cne $retainedTransaction) {
            throw "Existing rollback receipt does not match this exact rollback."
        }
    }
    else {
        Write-MihoAtomicBytesV1 -Path $rollbackReceiptPath -Bytes (ConvertTo-MihoJsonBytesV1 -Object $rollbackReceipt) -Purpose "rollback-receipt" -FileHooks $FileHooks
    }
    Remove-MihoFileV1 -Path $Paths.Journal -Purpose "journal-rollback-cleanup" -FileHooks $FileHooks
    return [pscustomobject][ordered]@{
        recovered = $true
        committed = $false
        retired_generation_removed = $false
        retained_transaction = $retainedTransaction
        rollback_receipt = $rollbackReceiptPath
    }
}

function Repair-MihoAutomationJournalCoreV1 {
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Owner,
        [Parameter(Mandatory = $true)][hashtable]$Adapter,
        [int]$ProcessTimeoutSeconds = 7200,
        [hashtable]$FileHooks
    )

    if (-not (Test-Path -LiteralPath $Paths.Journal)) {
        return [pscustomobject][ordered]@{ recovered = $false; committed = $false; retained_transaction = "" }
    }
    $record = Read-MihoJsonFileV1 -Path $Paths.Journal -MaximumBytes $script:MihoJournalMaximumBytesV1
    $journal = $record.Object
    Assert-MihoJournalIdentityV1 -Journal $journal -Identity $Identity -Owner $Owner -Paths $Paths
    $operation = [string]$journal.operation
    $phase = [string](Get-MihoRequiredPropertyV1 -Object $journal -Name "phase")

    if ($operation -eq "install") {
        return Rollback-MihoInstallJournalV1 -Journal $journal -Paths $Paths -Identity $Identity -Owner $Owner -Adapter $Adapter -ProcessTimeoutSeconds $ProcessTimeoutSeconds -FileHooks $FileHooks
    }

    if ($operation -eq "uninstall" -and $phase -eq "committed") {
        $pathsRecord = Assert-MihoJournalQuarantineV1 -Journal $journal -Paths $Paths
        $oldManifestBytes = Get-MihoJournalOldManifestBytesV1 -Journal $journal
        $expectedUnboundBytes = Get-MihoExpectedUnboundBytesV1 -ManifestBytes $oldManifestBytes -Owner $Owner -Identity $Identity -Paths $Paths
        $task = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($Identity.TaskName)
        if ($null -ne $task -or (Test-Path -LiteralPath $Paths.Manifest) -or (Test-Path -LiteralPath $pathsRecord.Original)) {
            throw "Committed uninstall state drifted; refusing cleanup."
        }
        if (-not (Test-Path -LiteralPath $Paths.Unbound) -or
            (Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($Paths.Unbound))) -cne (Get-MihoSha256BytesV1 -Bytes $expectedUnboundBytes)) {
            throw "Committed uninstall lacks its exact owner-bound unbound receipt."
        }
        Remove-MihoJournalQuarantineGenerationV1 -Journal $journal -Paths $Paths -FileHooks $FileHooks
        Remove-MihoFileV1 -Path $Paths.Journal -Purpose "journal-commit-cleanup" -FileHooks $FileHooks
        return [pscustomobject][ordered]@{ recovered = $true; committed = $true; retained_transaction = "" }
    }

    if ($operation -eq "uninstall") {
        $pathsRecord = Assert-MihoJournalQuarantineV1 -Journal $journal -Paths $Paths
        $oldManifestBytes = Get-MihoJournalOldManifestBytesV1 -Journal $journal
        $expectedUnboundBytes = Get-MihoExpectedUnboundBytesV1 -ManifestBytes $oldManifestBytes -Owner $Owner -Identity $Identity -Paths $Paths
        Remove-MihoExpectedUnboundV1 -ExpectedBytes $expectedUnboundBytes -Paths $Paths -FileHooks $FileHooks
        $originalExists = Test-Path -LiteralPath $pathsRecord.Original
        $quarantineExists = Test-Path -LiteralPath $pathsRecord.Quarantine
        if ($originalExists -and $quarantineExists) {
            throw "Both original and quarantined generations exist during recovery."
        }
        if (-not $originalExists -and $quarantineExists) {
            $null = Assert-MihoExactGenerationDirectoryV1 -Directory $pathsRecord.Quarantine -Sha256 $pathsRecord.Sha256 -Paths $Paths
            Move-MihoDirectoryV1 -Source $pathsRecord.Quarantine -Destination $pathsRecord.Original -Purpose "uninstall-generation-restore" -FileHooks $FileHooks
            $null = Assert-MihoExactGenerationDirectoryV1 -Directory $pathsRecord.Original -Sha256 $pathsRecord.Sha256 -Paths $Paths
        }
        elseif (-not $originalExists -and -not $quarantineExists) {
            throw "Owned generation is missing during uninstall recovery."
        }
    }
    Restore-MihoJournalPriorStateV1 -Journal $journal -Paths $Paths -Identity $Identity -Adapter $Adapter -FileHooks $FileHooks
    Remove-MihoFileV1 -Path $Paths.Journal -Purpose "journal-rollback-cleanup" -FileHooks $FileHooks
    return [pscustomobject][ordered]@{ recovered = $true; committed = $false; retained_transaction = "" }
}

function Repair-MihoAutomationJournalV1 {
    param(
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerKind,
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerInstanceId,
        [string]$AutomationRoot,
        [int]$ProcessTimeoutSeconds = 7200,
        [hashtable]$Adapter,
        [hashtable]$FileHooks
    )

    $expectedOwner = New-MihoExpectedOwnerV1 -OwnerKind $ExpectedOwnerKind -OwnerInstanceId $ExpectedOwnerInstanceId
    $identity = Get-MihoTaskIdentityV1 -OwnerSid (Get-MihoCurrentSidV1)
    $coordinator = Enter-MihoAutomationCoordinatorV1 -AutomationRoot $AutomationRoot
    try {
        Assert-MihoNoPendingClaimIntentV1 -Coordinator $coordinator -Identity $identity
        Assert-MihoNoPendingReleaseIntentV1 -Coordinator $coordinator
        $paths = Get-MihoAutomationPathsV1 -AutomationRoot $coordinator.Root
        if ($null -eq $Adapter) { $Adapter = New-MihoRealAdapterV1 }
        $mutex = Enter-MihoAutomationMutexV1 -Paths $paths
        try {
            if (Test-Path -LiteralPath $paths.ClaimJournal) { throw "Automation owner claim requires explicit same-owner Claim recovery." }
            $owner = Get-MihoOwnerContextV1 -ExpectedOwner $expectedOwner -Paths $paths -Identity $identity
            return Repair-MihoAutomationJournalCoreV1 -Paths $paths -Identity $identity -Owner $owner -Adapter $Adapter -ProcessTimeoutSeconds $ProcessTimeoutSeconds -FileHooks $FileHooks
        }
        finally { Exit-MihoAutomationMutexV1 -Mutex $mutex }
    }
    finally { Exit-MihoAutomationCoordinatorV1 -Coordinator $coordinator }
}

function Test-MihoStrictLegacyTaskV1 {
    param(
        $Snapshot,
        [Parameter(Mandatory = $true)][string]$OwnerSid,
        [Parameter(Mandatory = $true)][string]$ExpectedXmlSha256,
        [Parameter(Mandatory = $true)][string]$ExpectedSddlSha256,
        [switch]$AllowEnabled
    )

    if ($null -eq $Snapshot) { return $false }
    if ($ExpectedXmlSha256 -notmatch '^[0-9a-f]{64}$' -or $ExpectedSddlSha256 -notmatch '^[0-9a-f]{64}$') { return $false }
    if ($Snapshot.Enabled -and -not $AllowEnabled) { return $false }
    if ((Get-MihoSha256TextV1 -Text ([string]$Snapshot.RawXml)) -cne $ExpectedXmlSha256 -or
        (Get-MihoSddlSemanticFingerprintV1 -Sddl ([string]$Snapshot.Sddl)) -cne $ExpectedSddlSha256) { return $false }
    if ($Snapshot.TaskName -ne $script:MihoLegacyTaskNameV1 -or $Snapshot.ActionCount -ne 1 -or $Snapshot.PrincipalCount -ne 1 -or $Snapshot.TriggerCount -ne 1) { return $false }
    if (-not [string]::Equals($Snapshot.OwnerSid, $OwnerSid, [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
    if ((Normalize-MihoLogonTypeV1 -Value $Snapshot.LogonType) -ne "InteractiveToken" -or (Normalize-MihoRunLevelV1 -Value $Snapshot.RunLevel) -ne "Limited") { return $false }
    if (-not [string]::Equals($Snapshot.Execute, "powershell.exe", [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
    $argumentPattern = '^-NoProfile -ExecutionPolicy Bypass -File "([^"]+)" -Root "([^"]+)"$'
    if ([string]$Snapshot.Arguments -notmatch $argumentPattern) { return $false }
    $scriptPath = [string]$Matches[1]
    $legacyRoot = [string]$Matches[2]
    if (-not [System.IO.Path]::IsPathRooted($scriptPath) -or -not [System.IO.Path]::IsPathRooted($legacyRoot)) { return $false }
    $canonicalLegacyRoot = [System.IO.Path]::GetFullPath($legacyRoot).TrimEnd("\", "/")
    if (-not [string]::Equals($legacyRoot.TrimEnd("\", "/"), $canonicalLegacyRoot, [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
    $expectedScript = Join-Path $canonicalLegacyRoot "scripts\update_endgame_data.ps1"
    if (-not (Test-MihoPathEqualV1 -Left $scriptPath -Right $expectedScript)) { return $false }
    if (-not [string]::IsNullOrEmpty([string]$Snapshot.WorkingDirectory) -or -not [string]::IsNullOrEmpty([string]$Snapshot.Source)) { return $false }
    if ($Snapshot.Description -ne $script:MihoLegacyDescriptionV1) { return $false }
    if ($Snapshot.MultipleInstancesPolicy -ne "IgnoreNew" -or -not $Snapshot.StartWhenAvailable -or $Snapshot.ExecutionTimeLimit -ne "PT2H") { return $false }
    if ($Snapshot.Hidden -or -not $Snapshot.AllowStartOnDemand -or $Snapshot.CalendarDaysInterval -ne "1") { return $false }
    return $true
}

function New-MihoOwnershipManifestV1 {
    param(
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Owner,
        [Parameter(Mandatory = $true)][string]$InstallId,
        [Parameter(Mandatory = $true)][string]$Workspace,
        [Parameter(Mandatory = $true)][string]$ConfigRelative,
        [Parameter(Mandatory = $true)][string]$CanonicalConfig,
        [Parameter(Mandatory = $true)]$Generation,
        [Parameter(Mandatory = $true)]$CanonicalTask,
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$ScheduleAt
    )

    $fingerprintParameters = @{
        Execute = $Generation.Executable
        Arguments = New-MihoUpdateActionArgumentsV1 -Workspace $Workspace -ConfigRelative $ConfigRelative
        WorkingDirectory = $Workspace
        OwnerSid = $Identity.OwnerSid
        LogonType = "InteractiveToken"
        RunLevel = "Limited"
        Source = $Source
        InstallId = $InstallId
    }
    return [pscustomobject][ordered]@{
        schema = $script:MihoAutomationSchemaV1
        owner_kind = $Owner.Kind
        owner_instance_id = $Owner.InstanceId
        owner_epoch = $Owner.Epoch
        owner_sid = $Identity.OwnerSid
        install_id = $InstallId
        task_name = $Identity.TaskName
        task_path = $Identity.TaskPath
        canonical_workspace = $Workspace
        canonical_config = $CanonicalConfig
        config_relative = $ConfigRelative
        generation = $Generation.Generation
        version = $Generation.Version
        generation_path = $Generation.Directory
        exe_path = $Generation.Executable
        exe_sha256 = $Generation.Sha256
        action_fingerprint = Get-MihoNormalizedActionFingerprintV1 @fingerprintParameters
        task_xml_sha256 = Get-MihoSha256TextV1 -Text ([string]$CanonicalTask.RawXml)
        task_sddl_sha256 = Get-MihoSddlSemanticFingerprintV1 -Sddl ([string]$CanonicalTask.Sddl)
        source = $Source
        schedule_at = $ScheduleAt
    }
}

function Test-MihoStateUnchangedV1 {
    param(
        $Before,
        $After
    )

    if ($null -eq $Before -or $null -eq $After) {
        return ($null -eq $Before -and $null -eq $After)
    }
    return ((Test-MihoSnapshotExactlyV1 -Snapshot $Before.Task -Expected $After.Task) -and (Get-MihoSha256BytesV1 -Bytes $Before.ManifestBytes) -eq (Get-MihoSha256BytesV1 -Bytes $After.ManifestBytes))
}

function Install-MihoDailyUpdateTaskV1 {
    param(
        [Parameter(Mandatory = $true)][string]$SourceCli,
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerKind,
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerInstanceId,
        [string]$Workspace,
        [string]$DefaultWorkspace,
        [string]$DesktopSettingsPath,
        [string]$Config,
        [string]$At = "09:30",
        [int]$CandidateTimeoutSeconds = 7200,
        [int]$ProcessTimeoutSeconds = 7200,
        [int]$PrepareValiditySeconds = 1800,
        [int64]$CoordinatorPid = 0,
        [string]$AutomationRoot,
        [string]$ExpectedLegacyXmlSha256,
        [string]$ExpectedLegacySddlSha256,
        [string]$ResultPath,
        [string]$CallerNonce,
        [switch]$PrepareOnly,
        [hashtable]$Adapter,
        [hashtable]$FileHooks
    )

    if ($CandidateTimeoutSeconds -le 0 -or $ProcessTimeoutSeconds -le 0 -or $PrepareValiditySeconds -le 0 -or $PrepareValiditySeconds -gt 3600) {
        throw "Timeout values must be positive."
    }
    $handoffRequested = -not [string]::IsNullOrWhiteSpace($ResultPath) -or -not [string]::IsNullOrWhiteSpace($CallerNonce)
    if ($handoffRequested -and (-not $PrepareOnly -or [string]::IsNullOrWhiteSpace($ResultPath) -or
        $CallerNonce -cnotmatch '^[0-9a-f]{32}$' -or $CoordinatorPid -le 0)) {
        throw "Prepare handoff ResultPath, lowercase 32-hex CallerNonce, and positive CoordinatorPid are required together in prepare mode."
    }
    $resolvedResultPath = ""
    if ($handoffRequested) {
        $resolvedResultPath = Resolve-MihoPrepareHandoffPathV1 -Path $ResultPath
        if (Test-Path -LiteralPath $resolvedResultPath) { throw "Prepare handoff receipt path already exists." }
    }
    $legacyAuthorizationProvided = -not [string]::IsNullOrWhiteSpace($ExpectedLegacyXmlSha256) -or -not [string]::IsNullOrWhiteSpace($ExpectedLegacySddlSha256)
    if ($legacyAuthorizationProvided -and
        ($ExpectedLegacyXmlSha256 -notmatch '^[0-9a-f]{64}$' -or $ExpectedLegacySddlSha256 -notmatch '^[0-9a-f]{64}$')) {
        throw "Legacy cleanup requires exact lowercase XML and SDDL SHA-256 authorization."
    }
    $expectedOwner = New-MihoExpectedOwnerV1 -OwnerKind $ExpectedOwnerKind -OwnerInstanceId $ExpectedOwnerInstanceId
    $ownerSid = Get-MihoCurrentSidV1
    $identity = Get-MihoTaskIdentityV1 -OwnerSid $ownerSid
    $ownerCoordinator = Enter-MihoAutomationCoordinatorV1 -AutomationRoot $AutomationRoot
    try {
        Assert-MihoNoPendingClaimIntentV1 -Coordinator $ownerCoordinator -Identity $identity
        Assert-MihoNoPendingReleaseIntentV1 -Coordinator $ownerCoordinator
        $paths = Get-MihoAutomationPathsV1 -AutomationRoot $ownerCoordinator.Root
        if ($handoffRequested -and ((Test-MihoPathEqualV1 -Left $resolvedResultPath -Right $paths.Root) -or
            (Test-MihoPathBelowV1 -Path $resolvedResultPath -Parent $paths.Root))) {
            throw "Prepare handoff receipt must be outside automation storage."
        }
        if ($null -eq $Adapter) { $Adapter = New-MihoRealAdapterV1 }
        $mutex = Enter-MihoAutomationMutexV1 -Paths $paths
        try {
        if (Test-Path -LiteralPath $paths.ClaimJournal) { throw "Automation owner claim requires explicit same-owner Claim recovery." }
        $owner = Get-MihoOwnerContextV1 -ExpectedOwner $expectedOwner -Paths $paths -Identity $identity
        if (Test-Path -LiteralPath $paths.Journal) {
            $pendingRecord = Read-MihoJsonFileV1 -Path $paths.Journal -MaximumBytes $script:MihoJournalMaximumBytesV1
            Assert-MihoJournalIdentityV1 -Journal $pendingRecord.Object -Identity $identity -Owner $owner -Paths $paths
            if ([string]$pendingRecord.Object.operation -ceq "install" -and (Test-MihoExternalPrepareCoordinatorActiveV1 -Journal $pendingRecord.Object)) {
                throw "A prepared automation install is pending explicit Commit or Rollback with its transaction token."
            }
        }
        $null = Repair-MihoAutomationJournalCoreV1 -Paths $paths -Identity $identity -Owner $owner -Adapter $Adapter -ProcessTimeoutSeconds $ProcessTimeoutSeconds -FileHooks $FileHooks
        $oldState = Get-MihoInstalledStateV1 -Paths $paths -Identity $identity -Owner $owner -Adapter $Adapter
        $selectedWorkspace = ""
        if (-not [string]::IsNullOrWhiteSpace($Workspace)) {
            $selectedWorkspace = $Workspace
        }
        elseif ($null -ne $oldState) {
            $selectedWorkspace = $oldState.Workspace
        }
        elseif (-not [string]::IsNullOrWhiteSpace($DesktopSettingsPath)) {
            if ([string]::IsNullOrWhiteSpace($DefaultWorkspace)) {
                throw "DefaultWorkspace is required with DesktopSettingsPath."
            }
            $selectedWorkspace = Resolve-MihoDesktopWorkspaceV1 -DefaultWorkspace $DefaultWorkspace -SettingsPath $DesktopSettingsPath
        }
        elseif (-not [string]::IsNullOrWhiteSpace($DefaultWorkspace)) {
            $selectedWorkspace = $DefaultWorkspace
        }
        else {
            throw "Workspace is required for a fresh automation install."
        }
        $workspacePath = Resolve-MihoExistingDirectoryV1 -Path $selectedWorkspace -Label "Workspace"
        if ((Test-MihoPathEqualV1 -Left $workspacePath -Right $paths.Root) -or (Test-MihoPathBelowV1 -Path $workspacePath -Parent $paths.Root) -or (Test-MihoPathBelowV1 -Path $paths.Root -Parent $workspacePath)) {
            throw "Workspace and automation storage must not overlap."
        }
        $sourcePath = Resolve-MihoExistingFileV1 -Path $SourceCli -Label "Source CLI"
        $selectedConfig = $Config
        if ([string]::IsNullOrWhiteSpace($selectedConfig)) {
            $selectedConfig = if ($null -ne $oldState) { $oldState.ConfigRelative } else { "configs\update_v1.json" }
        }
        $configRelative = Resolve-MihoConfigRelativeV1 -Config $selectedConfig
        if ($null -ne $oldState) {
            if (-not (Test-MihoPathEqualV1 -Left $oldState.Workspace -Right $workspacePath)) {
                throw "Canonical task belongs to a different workspace."
            }
            if ($oldState.ConfigRelative -ne $configRelative) {
                throw "Canonical task belongs to a different config."
            }
        }

        # Copy into a random staging directory first.  The single-directory
        # publish is deferred until the switch journal is durable.
        $generation = Get-MihoGenerationV1 -SourceCli $sourcePath -Paths $paths -Adapter $Adapter -Workspace $workspacePath -TimeoutSeconds $ProcessTimeoutSeconds -DeferPublish -FileHooks $FileHooks
        $installId = if ($null -ne $oldState) { $oldState.InstallId } else { [guid]::NewGuid().ToString("D").ToLowerInvariant() }
        $sourceMarker = "com.miho.endgame/automation-v1/$($owner.Kind)/$($owner.InstanceId)/$($owner.Epoch)/$installId"
        $actionArguments = New-MihoUpdateActionArgumentsV1 -Workspace $workspacePath -ConfigRelative $configRelative
        $expectedAttemptId = "installer-" + [guid]::NewGuid().ToString("N")
        $candidateActionArguments = New-MihoUpdateActionArgumentsV1 -Workspace $workspacePath -ConfigRelative $configRelative -AttemptId $expectedAttemptId
        $candidateNonce = [guid]::NewGuid().ToString("N")
        $candidateName = "$($script:MihoCanonicalTaskPrefixV1)-Candidate-$($identity.SidHash)-$candidateNonce"
        $candidateSpec = New-MihoTaskSpecV1 -TaskName $candidateName -Execute $generation.Executable -Arguments $candidateActionArguments -WorkingDirectory $workspacePath -OwnerSid $ownerSid -Source "$sourceMarker/candidate/$candidateNonce" -InstallId $installId -TriggerKind "None"
        $canonicalSpec = New-MihoTaskSpecV1 -TaskName $identity.TaskName -Execute $generation.Executable -Arguments $actionArguments -WorkingDirectory $workspacePath -OwnerSid $ownerSid -Source $sourceMarker -InstallId $installId -TriggerKind "Daily" -At $At -ReplaceExisting ($null -ne $oldState)
        $canonicalConfigPlanned = [System.IO.Path]::GetFullPath((Join-Path $workspacePath $configRelative))
        if (-not (Test-MihoPathBelowV1 -Path $canonicalConfigPlanned -Parent $workspacePath)) {
            throw "Canonical config escapes the workspace."
        }
        $transactionToken = [guid]::NewGuid().ToString("N")
        $preparedAt = [DateTimeOffset]::UtcNow
        $prepareExpiresAt = $preparedAt.AddSeconds($PrepareValiditySeconds)
        $coordinatorPidValue = [int64]0
        $coordinatorStartedAtUtc = ""
        if ($PrepareOnly) {
            $coordinatorPidValue = if ($CoordinatorPid -gt 0) { $CoordinatorPid } else { $PID }
            try {
                $coordinatorProcess = Get-Process -Id $coordinatorPidValue -ErrorAction Stop
                $coordinatorStartedAtUtc = $coordinatorProcess.StartTime.ToUniversalTime().ToString("o", [System.Globalization.CultureInfo]::InvariantCulture)
            }
            catch {
                throw "External prepare coordinator process is unavailable."
            }
        }
        $transactionPath = Join-Path $paths.Root ("bootstrap-transaction-" + [guid]::NewGuid().ToString("N"))
        $transactionPath = Assert-MihoBootstrapTransactionPathV1 -TransactionPath $transactionPath -Paths $paths
        $oldTask = if ($null -ne $oldState) { $oldState.Task } else { $null }
        $oldManifestBytes = if ($null -ne $oldState) { $oldState.ManifestBytes } else { $null }
        $legacyTaskForJournal = $null
        $legacyAtStart = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($script:MihoLegacyTaskNameV1)
        if ($null -ne $legacyAtStart -and $legacyAuthorizationProvided -and
            (Test-MihoStrictLegacyTaskV1 -Snapshot $legacyAtStart -OwnerSid $ownerSid -ExpectedXmlSha256 $ExpectedLegacyXmlSha256 -ExpectedSddlSha256 $ExpectedLegacySddlSha256 -AllowEnabled)) {
            $legacyTaskForJournal = $legacyAtStart
        }
        $journal = New-MihoJournalV1 -Operation "install" -Identity $identity -Owner $owner -Paths $paths -OldTask $oldTask -OldManifestBytes $oldManifestBytes -LegacyTask $legacyTaskForJournal -NewSpec $canonicalSpec -CandidateSpec $candidateSpec -TransactionToken $transactionToken -PrepareMode $(if ($PrepareOnly) { "external" } else { "single-call" }) -PreparedAtUtc $preparedAt.ToString("o", [System.Globalization.CultureInfo]::InvariantCulture) -PrepareExpiresAtUtc $prepareExpiresAt.ToString("o", [System.Globalization.CultureInfo]::InvariantCulture) -CoordinatorPid $coordinatorPidValue -CoordinatorStartedAtUtc $coordinatorStartedAtUtc -ExpectedAttemptId $expectedAttemptId -NewGenerationCreated ([bool]$generation.Created) -NewGenerationPath $generation.Directory -NewGenerationStagingPath $generation.StagingDirectory -NewGeneration $generation.Generation -NewVersion $generation.Version -NewExeSha256 $generation.Sha256 -BootstrapWorkspace $workspacePath -BootstrapConfigRelative $configRelative -BootstrapCanonicalConfig $canonicalConfigPlanned -BootstrapTransactionPath $transactionPath
        try {
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
        }
        catch {
            if (-not (Test-Path -LiteralPath $paths.Journal) -and $generation.Created) {
                if (-not [string]::IsNullOrEmpty([string]$generation.StagingDirectory)) {
                    Remove-MihoPrivateStagingGenerationV1 -Directory $generation.StagingDirectory -Paths $paths -FileHooks $FileHooks
                }
                else {
                    Remove-MihoExactGenerationV1 -Generation $generation -Paths $paths -Purpose "pre-journal-generation-cleanup" -FileHooks $FileHooks
                }
            }
            elseif (Test-Path -LiteralPath $paths.Journal) {
                throw "Prepared automation journal may already be durable and requires explicit repair: $($_.Exception.Message)"
            }
            throw
        }

        $runResult = $null
        $health = $null
        $manifest = $null
        $commitRecoveryWarning = ""
        $recoveredRetiredGenerationRemoved = $false
        $transactionCommitted = $false
        $legacyRemoved = $false
        try {
            $generation = Publish-MihoGenerationV1 -Generation $generation -Paths $paths -FileHooks $FileHooks
            $null = Quiesce-MihoJournalLegacyTaskV1 -Journal $journal -Paths $paths -Adapter $Adapter -TimeoutSeconds $CandidateTimeoutSeconds -FileHooks $FileHooks
            if ($null -ne $oldState) {
                Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "DisableTask" -Arguments @($identity.TaskName) | Out-Null
                $disabledTask = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($identity.TaskName)
                if (-not (Test-MihoTaskEquivalentExceptEnabledV1 -Snapshot $disabledTask -Expected $oldTask)) {
                    throw "Old canonical task could not be disabled exactly."
                }
                Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "StopTask" -Arguments @($identity.TaskName, 30) | Out-Null
                $disabledTask = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($identity.TaskName)
                if (-not (Test-MihoTaskEquivalentExceptEnabledV1 -Snapshot $disabledTask -Expected $oldTask)) {
                    throw "Old canonical task changed while being quiesced."
                }
            }
            $journal.phase = "old-quiesced"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks

            $journal.phase = "bootstrap-begin-started"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
            $null = Invoke-MihoBootstrapTransactionV1 -Adapter $Adapter -Executable $generation.Executable -Workspace $workspacePath -TransactionPath $transactionPath -Operation "begin" -TimeoutSeconds $ProcessTimeoutSeconds
            $journal.phase = "bootstrap-begun"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks

            $canonicalConfig = Resolve-MihoExistingFileV1 -Path $canonicalConfigPlanned -Label "Bootstrapped update config"
            $journal.prior_health_attempt_id = Get-MihoHealthyAttemptBeforeCandidateV1 -Adapter $Adapter -Executable $generation.Executable -Workspace $workspacePath -ConfigRelative $configRelative -TimeoutSeconds $ProcessTimeoutSeconds
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks

            Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "RegisterTask" -Arguments @($candidateSpec) | Out-Null
            $candidateTask = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($candidateName)
            if ($null -eq $candidateTask -or -not (Test-MihoTaskMatchesSpecV1 -Snapshot $candidateTask -Spec $candidateSpec)) {
                throw "Candidate task definition verification failed."
            }
            $journal.phase = "candidate-registered"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks

            $runResult = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "RunTask" -Arguments @($candidateName, $CandidateTimeoutSeconds)
            if ($null -eq $runResult -or -not (Test-MihoObjectPropertyV1 -Object $runResult -Name "Completed") -or -not ($runResult.Completed -is [bool]) -or -not $runResult.Completed -or
                -not (Test-MihoObjectPropertyV1 -Object $runResult -Name "TaskName") -or -not ($runResult.TaskName -is [string]) -or [string]$runResult.TaskName -cne $candidateName -or
                -not (Test-MihoObjectPropertyV1 -Object $runResult -Name "RunToken") -or -not ($runResult.RunToken -is [string]) -or [string]::IsNullOrWhiteSpace([string]$runResult.RunToken) -or
                -not (Test-MihoObjectPropertyV1 -Object $runResult -Name "ExitCode") -or -not ($runResult.ExitCode -is [int] -or $runResult.ExitCode -is [long]) -or [int64]$runResult.ExitCode -ne 0) {
                throw "The specific candidate task run did not complete successfully."
            }
            $journal.candidate_run_token = [string]$runResult.RunToken
            $journal.phase = "candidate-ran"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks

            $healthResult = Invoke-MihoCheckedProcessV1 -Adapter $Adapter -FilePath $generation.Executable -Arguments @("update", "health", "--workspace", $workspacePath, "--config", $configRelative) -WorkingDirectory $workspacePath -Label "miho update health" -TimeoutSeconds $ProcessTimeoutSeconds
            $health = ConvertFrom-MihoHealthJsonV1 -Json ([string]$healthResult.StdOut).Trim()
            if ([string]$health.attempt_id -cne [string]$journal.expected_attempt_id) {
                throw "Candidate health does not belong to this exact candidate attempt."
            }
            $journal.health_attempt_id = [string]$health.attempt_id
            $journal.phase = "candidate-healthy"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks

            $null = Invoke-MihoBootstrapTransactionV1 -Adapter $Adapter -Executable $generation.Executable -Workspace $workspacePath -TransactionPath $transactionPath -Operation "verify" -TimeoutSeconds $ProcessTimeoutSeconds
            $journal.phase = "bootstrap-verified"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks

            $evidence = Get-MihoInstallJournalEvidenceV1 -Journal $journal -Paths $paths -Identity $identity
            $null = Remove-MihoJournalCandidateV1 -Evidence $evidence -Adapter $Adapter -QuiesceTimeoutSeconds 30
            $journal.phase = "candidate-removed"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks

            if ($PrepareOnly) {
                $prepareResult = [pscustomobject][ordered]@{
                    schema = "miho-automation-prepare-result-v1"
                    transaction_token = $transactionToken
                    phase = $journal.phase
                    owner_kind = $owner.Kind
                    owner_instance_id = $owner.InstanceId
                    owner_epoch = $owner.Epoch
                    coordinator_pid = $coordinatorPidValue
                    task_name = $identity.TaskName
                    workspace = $workspacePath
                    candidate_run_token = [string]$journal.candidate_run_token
                    health_attempt_id = [string]$journal.health_attempt_id
                    retained_bootstrap_transaction = $transactionPath
                }
                if ($handoffRequested) {
                    $handoff = New-MihoPrepareHandoffReceiptV1 -CallerNonce $CallerNonce -TransactionToken $transactionToken -Owner $owner -CoordinatorPid $coordinatorPidValue -Phase ([string]$journal.phase) -Generation $generation.Generation -ExeSha256 $generation.Sha256 -Workspace $workspacePath
                    $null = Write-MihoPrepareHandoffReceiptV1 -Path $resolvedResultPath -Receipt $handoff -FileHooks $FileHooks
                }
                return $prepareResult
            }

            $priorPreflight = Get-MihoJournalPriorStatePreflightV1 -Journal $journal -Paths $paths -Identity $identity -Adapter $Adapter
            if (($null -ne $oldState -and -not $priorPreflight.CurrentIsOldDisabled) -or ($null -eq $oldState -and $null -ne $priorPreflight.CurrentTask)) {
                throw "Canonical task changed while the candidate was running."
            }
            Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "RegisterTask" -Arguments @($canonicalSpec) | Out-Null
            $canonicalTask = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($identity.TaskName)
            if ($null -eq $canonicalTask -or -not (Test-MihoTaskMatchesSpecV1 -Snapshot $canonicalTask -Spec $canonicalSpec)) {
                throw "Canonical task replacement verification failed."
            }
            $manifest = New-MihoOwnershipManifestV1 -Identity $identity -Owner $owner -InstallId $installId -Workspace $workspacePath -ConfigRelative $configRelative -CanonicalConfig $canonicalConfig -Generation $generation -CanonicalTask $canonicalTask -Source $sourceMarker -ScheduleAt $At
            $manifestBytes = ConvertTo-MihoJsonBytesV1 -Object $manifest
            $journal.new_manifest_sha256 = Get-MihoSha256BytesV1 -Bytes $manifestBytes
            $journal.new_task_xml_sha256 = Get-MihoSha256TextV1 -Text ([string]$canonicalTask.RawXml)
            $journal.new_task_sddl_sha256 = Get-MihoSddlSemanticFingerprintV1 -Sddl ([string]$canonicalTask.Sddl)
            $journal.phase = "canonical-replaced"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
            Write-MihoAtomicBytesV1 -Path $paths.Manifest -Bytes $manifestBytes -Purpose "manifest" -FileHooks $FileHooks
            if ((Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($paths.Manifest))) -cne $journal.new_manifest_sha256 -or
                -not (Test-MihoSnapshotExactlyV1 -Snapshot (Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($identity.TaskName)) -Expected $canonicalTask)) {
                throw "Canonical task or ownership manifest drifted before commit."
            }
            $journal.phase = "committed"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
            $journal.phase = "bootstrap-commit-started"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
            $null = Invoke-MihoBootstrapTransactionV1 -Adapter $Adapter -Executable $generation.Executable -Workspace $workspacePath -TransactionPath $transactionPath -Operation "commit" -TimeoutSeconds $ProcessTimeoutSeconds
            $transactionCommitted = $true
            $journal.phase = "bootstrap-committed"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
            $null = Invoke-MihoBootstrapTransactionV1 -Adapter $Adapter -Executable $generation.Executable -Workspace $workspacePath -TransactionPath $transactionPath -Operation "finalize" -CompletedOperation "commit" -TimeoutSeconds $ProcessTimeoutSeconds
            $null = Remove-MihoCommittedInstallUnboundV1 -Paths $paths -Identity $identity -Owner $owner -FileHooks $FileHooks
            $legacyRemoved = Remove-MihoJournalLegacyTaskV1 -Journal $journal -Paths $paths -Adapter $Adapter -TimeoutSeconds $CandidateTimeoutSeconds -FileHooks $FileHooks
        }
        catch {
            $primary = $_
            try {
                $repair = Repair-MihoAutomationJournalCoreV1 -Paths $paths -Identity $identity -Owner $owner -Adapter $Adapter -ProcessTimeoutSeconds $ProcessTimeoutSeconds -FileHooks $FileHooks
                if ($repair.committed) {
                    $transactionCommitted = $true
                    $recoveredRetiredGenerationRemoved = [bool]$repair.retired_generation_removed
                    $legacyRemoved = [bool]$repair.legacy_removed
                    $commitRecoveryWarning = "Bootstrap commit completed and exact committed state was recovered after: $($primary.Exception.Message)"
                    if (-not [string]::IsNullOrWhiteSpace([string]$repair.warning)) {
                        $commitRecoveryWarning += " $($repair.warning)"
                    }
                }
                else {
                    $retained = ""
                    if (-not [string]::IsNullOrWhiteSpace([string]$repair.retained_transaction)) {
                        $retained = " Rollback evidence retained at: $($repair.retained_transaction)"
                    }
                    throw "__MIHO_ROLLED_BACK__ Automation install failed and was rolled back. Primary: $($primary.Exception.Message)$retained"
                }
            }
            catch {
                if ($_.Exception.Message -like "__MIHO_ROLLED_BACK__*") {
                    throw $_.Exception.Message.Substring("__MIHO_ROLLED_BACK__ ".Length)
                }
                throw "Automation install failed and rollback is pending in the journal. Primary: $($primary.Exception.Message) Rollback: $($_.Exception.Message)"
            }
        }
        if (-not $transactionCommitted) {
            throw "Automation install did not reach bootstrap commit."
        }

        $retiredGenerationRemoved = $recoveredRetiredGenerationRemoved
        $retiredWarning = ""
        if (Test-Path -LiteralPath $paths.Journal) {
            $retiredCleanupSucceeded = $true
            try {
                $retiredGenerationRemoved = Remove-MihoJournalRetiredGenerationV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
            }
            catch {
                $retiredCleanupSucceeded = $false
                $retiredWarning = "Committed canonical task, but exact retired generation cleanup was preserved after an error: $($_.Exception.Message)"
            }
            if ($retiredCleanupSucceeded) {
                try {
                    Remove-MihoFileV1 -Path $paths.Journal -Purpose "journal-commit-cleanup" -FileHooks $FileHooks
                }
                catch {
                    $retiredWarning = ($retiredWarning + " Committed canonical task, but bootstrap-committed journal cleanup remains pending: $($_.Exception.Message)").Trim()
                }
            }
        }
        $legacyWarning = ""
        try {
            $legacy = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($script:MihoLegacyTaskNameV1)
            if ($null -ne $legacy) {
                $legacyWarning = "Committed canonical task; legacy task was preserved because no exact authorized XML/SDDL snapshot matched."
            }
        }
        catch {
            $legacyWarning = "Committed canonical task, but strict legacy cleanup was preserved after an error: $($_.Exception.Message)"
        }
        $warnings = @($commitRecoveryWarning, $retiredWarning, $legacyWarning | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        return [pscustomobject][ordered]@{
            schema = "miho-automation-install-result-v1"
            task_name = $identity.TaskName
            workspace = $workspacePath
            config = $canonicalConfig
            generation = $generation.Generation
            executable = $generation.Executable
            exe_sha256 = $generation.Sha256
            action_fingerprint = $manifest.action_fingerprint
            candidate_run_token = [string]$journal.candidate_run_token
            health_attempt_id = [string]$journal.health_attempt_id
            healthy = $true
            retired_generation_removed = $retiredGenerationRemoved
            legacy_removed = $legacyRemoved
            warning = [string]::Join(" ", $warnings)
        }
    }
        finally { Exit-MihoAutomationMutexV1 -Mutex $mutex }
    }
    finally { Exit-MihoAutomationCoordinatorV1 -Coordinator $ownerCoordinator }
}

function Prepare-MihoDailyUpdateTaskInstallV1 {
    param(
        [Parameter(Mandatory = $true)][string]$SourceCli,
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerKind,
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerInstanceId,
        [string]$Workspace,
        [string]$DefaultWorkspace,
        [string]$DesktopSettingsPath,
        [string]$Config,
        [string]$At = "09:30",
        [int]$CandidateTimeoutSeconds = 7200,
        [int]$ProcessTimeoutSeconds = 7200,
        [int]$PrepareValiditySeconds = 1800,
        [int64]$CoordinatorPid = 0,
        [string]$AutomationRoot,
        [string]$ResultPath,
        [string]$CallerNonce,
        [hashtable]$Adapter,
        [hashtable]$FileHooks
    )

    return Install-MihoDailyUpdateTaskV1 `
        -SourceCli $SourceCli `
        -ExpectedOwnerKind $ExpectedOwnerKind `
        -ExpectedOwnerInstanceId $ExpectedOwnerInstanceId `
        -Workspace $Workspace `
        -DefaultWorkspace $DefaultWorkspace `
        -DesktopSettingsPath $DesktopSettingsPath `
        -Config $Config `
        -At $At `
        -CandidateTimeoutSeconds $CandidateTimeoutSeconds `
        -ProcessTimeoutSeconds $ProcessTimeoutSeconds `
        -PrepareValiditySeconds $PrepareValiditySeconds `
        -CoordinatorPid $CoordinatorPid `
        -AutomationRoot $AutomationRoot `
        -ResultPath $ResultPath `
        -CallerNonce $CallerNonce `
        -Adapter $Adapter `
        -FileHooks $FileHooks `
        -PrepareOnly
}

function Get-MihoRollbackReceiptV1 {
    param(
        [Parameter(Mandatory = $true)][string]$TransactionToken,
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Identity,
        [Parameter(Mandatory = $true)]$Owner
    )

    if ($TransactionToken -cnotmatch '^[0-9a-f]{32}$') {
        throw "Automation transaction token is invalid."
    }
    $path = Join-Path $Paths.Root ("rollback-receipt-$TransactionToken.json")
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    $record = Read-MihoJsonFileV1 -Path $path -MaximumBytes $script:MihoManifestMaximumBytesV1 -ExpectedKeys @(
        "schema", "transaction_token", "owner_kind", "owner_instance_id", "owner_epoch", "owner_sid", "task_name", "automation_root", "retained_bootstrap_transaction"
    )
    $receipt = $record.Object
    foreach ($name in @("schema", "transaction_token", "owner_kind", "owner_instance_id", "owner_epoch", "owner_sid", "task_name", "automation_root", "retained_bootstrap_transaction")) {
        if (-not ($receipt.$name -is [string])) { throw "Automation rollback receipt values are invalid." }
    }
    if ([string]$receipt.schema -cne "miho-automation-rollback-receipt-v1" -or
        [string]$receipt.transaction_token -cne $TransactionToken -or
        -not (Test-MihoOwnerTripletMatchesV1 -Object $receipt -Owner $Owner) -or
        -not [string]::Equals([string]$receipt.owner_sid, $Identity.OwnerSid, [System.StringComparison]::OrdinalIgnoreCase) -or
        [string]$receipt.task_name -cne $Identity.TaskName -or
        -not (Test-MihoPathEqualV1 -Left ([string]$receipt.automation_root) -Right $Paths.Root)) {
        throw "Automation rollback receipt is foreign or corrupt."
    }
    return [pscustomobject][ordered]@{ Path = $path; Object = $receipt }
}

function Commit-MihoDailyUpdateTaskInstallV1 {
    param(
        [Parameter(Mandatory = $true)][string]$TransactionToken,
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerKind,
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerInstanceId,
        [int]$ProcessTimeoutSeconds = 7200,
        [string]$AutomationRoot,
        [string]$ExpectedLegacyXmlSha256,
        [string]$ExpectedLegacySddlSha256,
        [string]$ResultPath,
        [string]$CallerNonce,
        [int64]$CoordinatorPid = 0,
        [hashtable]$Adapter,
        [hashtable]$FileHooks
    )

    if ($TransactionToken -cnotmatch '^[0-9a-f]{32}$' -or $ProcessTimeoutSeconds -le 0) {
        throw "Automation transaction token or timeout is invalid."
    }
    $legacyAuthorizationProvided = -not [string]::IsNullOrWhiteSpace($ExpectedLegacyXmlSha256) -or -not [string]::IsNullOrWhiteSpace($ExpectedLegacySddlSha256)
    if ($legacyAuthorizationProvided -and ($ExpectedLegacyXmlSha256 -cnotmatch '^[0-9a-f]{64}$' -or $ExpectedLegacySddlSha256 -cnotmatch '^[0-9a-f]{64}$')) {
        throw "Legacy cleanup requires exact lowercase XML and SDDL SHA-256 authorization."
    }
    $expectedOwner = New-MihoExpectedOwnerV1 -OwnerKind $ExpectedOwnerKind -OwnerInstanceId $ExpectedOwnerInstanceId
    $handoffRequested = -not [string]::IsNullOrWhiteSpace($ResultPath) -or -not [string]::IsNullOrWhiteSpace($CallerNonce) -or $CoordinatorPid -gt 0
    if ($handoffRequested -and ([string]::IsNullOrWhiteSpace($ResultPath) -or [string]::IsNullOrWhiteSpace($CallerNonce) -or $CoordinatorPid -le 0)) {
        throw "Commit handoff ResultPath, CallerNonce, and CoordinatorPid are required together."
    }
    $handoff = $null
    if ($handoffRequested) {
        $handoff = Read-MihoPrepareHandoffReceiptV1 -Path $ResultPath -CallerNonce $CallerNonce -ExpectedOwner $expectedOwner -CoordinatorPid $CoordinatorPid
        if ([string]$handoff.Object.transaction_token -cne $TransactionToken) { throw "Commit handoff transaction token disagrees with the request." }
        if ([string]$handoff.Object.phase -ceq "rolled-back") { throw "Prepared automation transaction was already rolled back and cannot be committed." }
    }
    $ownerSid = Get-MihoCurrentSidV1
    $identity = Get-MihoTaskIdentityV1 -OwnerSid $ownerSid
    $ownerCoordinator = Enter-MihoAutomationCoordinatorV1 -AutomationRoot $AutomationRoot
    try {
        Assert-MihoNoPendingClaimIntentV1 -Coordinator $ownerCoordinator -Identity $identity
        Assert-MihoNoPendingReleaseIntentV1 -Coordinator $ownerCoordinator
        $paths = Get-MihoAutomationPathsV1 -AutomationRoot $ownerCoordinator.Root
        if ($null -eq $Adapter) { $Adapter = New-MihoRealAdapterV1 }
        $mutex = Enter-MihoAutomationMutexV1 -Paths $paths
        try {
        if (Test-Path -LiteralPath $paths.ClaimJournal) { throw "Prepared commit is blocked by an owner claim journal." }
        $owner = Get-MihoOwnerContextV1 -ExpectedOwner $expectedOwner -Paths $paths -Identity $identity
        if ($null -ne $handoff -and $owner.Epoch -cne [string]$handoff.Object.owner_epoch) {
            throw "Commit handoff owner epoch is stale."
        }
        if ($null -ne $handoff -and [string]$handoff.Object.phase -ceq "committed") {
            $state = Get-MihoInstalledStateV1 -Paths $paths -Identity $identity -Owner $owner -Adapter $Adapter
            if ($null -eq $state -or -not (Test-MihoInstalledStateMatchesHandoffV1 -State $state -Owner $owner -Handoff $handoff)) {
                throw "Committed handoff no longer matches active automation state."
            }
            return [pscustomobject][ordered]@{
                schema = "miho-automation-install-result-v1"
                transaction_token = $TransactionToken
                task_name = $identity.TaskName
                workspace = $state.Workspace
                config = [string]$state.Manifest.canonical_config
                generation = [string]$state.Manifest.generation
                executable = $state.Generation.Executable
                exe_sha256 = $state.Generation.Sha256
                action_fingerprint = [string]$state.Manifest.action_fingerprint
                candidate_run_token = ""
                health_attempt_id = ""
                healthy = $true
                retired_generation_removed = $false
                legacy_removed = $false
                warning = "Idempotent committed prepare handoff replay."
            }
        }
        if (-not (Test-Path -LiteralPath $paths.Journal)) {
            if ($null -ne $handoff) {
                $rollback = Get-MihoRollbackReceiptV1 -TransactionToken $TransactionToken -Paths $paths -Identity $identity -Owner $owner
                if ($null -ne $rollback) {
                    $null = Set-MihoPrepareHandoffTerminalPhaseV1 -Record $handoff -Phase "rolled-back" -FileHooks $FileHooks
                    throw "Prepared automation transaction was already rolled back and cannot be committed."
                }
                $state = Get-MihoInstalledStateV1 -Paths $paths -Identity $identity -Owner $owner -Adapter $Adapter
                if ($null -ne $state -and (Test-MihoInstalledStateMatchesHandoffV1 -State $state -Owner $owner -Handoff $handoff)) {
                    $handoff = Set-MihoPrepareHandoffTerminalPhaseV1 -Record $handoff -Phase "committed" -FileHooks $FileHooks
                    return [pscustomobject][ordered]@{
                        schema = "miho-automation-install-result-v1"; transaction_token = $TransactionToken; task_name = $identity.TaskName
                        workspace = $state.Workspace; config = [string]$state.Manifest.canonical_config; generation = [string]$state.Manifest.generation
                        executable = $state.Generation.Executable; exe_sha256 = $state.Generation.Sha256; action_fingerprint = [string]$state.Manifest.action_fingerprint
                        candidate_run_token = ""; health_attempt_id = ""; healthy = $true; retired_generation_removed = $false; legacy_removed = $false
                        warning = "Recovered committed state from exact prepare handoff evidence."
                    }
                }
            }
            throw "Prepared automation journal is unavailable."
        }
        $record = Read-MihoJsonFileV1 -Path $paths.Journal -MaximumBytes $script:MihoJournalMaximumBytesV1
        $journal = $record.Object
        Assert-MihoJournalIdentityV1 -Journal $journal -Identity $identity -Owner $owner -Paths $paths
        if ([string]$journal.operation -cne "install" -or [string]$journal.transaction_token -cne $TransactionToken) {
            throw "Prepared automation journal does not match this transaction token."
        }
        $evidence = Get-MihoInstallJournalEvidenceV1 -Journal $journal -Paths $paths -Identity $identity
        if ([string]$journal.phase -cne "candidate-removed") {
            $repair = Rollback-MihoInstallJournalV1 -Journal $journal -Paths $paths -Identity $identity -Owner $owner -Adapter $Adapter -ProcessTimeoutSeconds $ProcessTimeoutSeconds -FileHooks $FileHooks
            if (-not $repair.committed) {
                if ($null -ne $handoff) { $handoff = Set-MihoPrepareHandoffTerminalPhaseV1 -Record $handoff -Phase "rolled-back" -FileHooks $FileHooks }
                $retained = if ([string]::IsNullOrWhiteSpace([string]$repair.retained_transaction)) { "" } else { " Rollback evidence retained at: $($repair.retained_transaction)" }
                throw "An interrupted commit was recovered by exact rollback.$retained"
            }
            if ($null -ne $handoff) { $handoff = Set-MihoPrepareHandoffTerminalPhaseV1 -Record $handoff -Phase "committed" -FileHooks $FileHooks }
            $manifestRecord = Read-MihoJsonFileV1 -Path $paths.Manifest -MaximumBytes $script:MihoManifestMaximumBytesV1
            return [pscustomobject][ordered]@{
                schema = "miho-automation-install-result-v1"
                transaction_token = $TransactionToken
                task_name = $identity.TaskName
                workspace = $evidence.Workspace
                config = $evidence.CanonicalConfig
                generation = $evidence.Generation.Generation
                executable = $evidence.Generation.Executable
                exe_sha256 = $evidence.Generation.Sha256
                action_fingerprint = [string]$manifestRecord.Object.action_fingerprint
                candidate_run_token = [string]$journal.candidate_run_token
                health_attempt_id = [string]$journal.health_attempt_id
                healthy = $true
                retired_generation_removed = [bool]$repair.retired_generation_removed
                legacy_removed = [bool]$repair.legacy_removed
                warning = "Interrupted bootstrap commit had already completed; exact committed state was finalized. $([string]$repair.warning)".Trim()
            }
        }
        if (-not (Test-Path -LiteralPath $evidence.TransactionPath)) {
            throw "Prepared bootstrap transaction evidence is missing."
        }
        $null = Remove-MihoJournalCandidateV1 -Evidence $evidence -Adapter $Adapter
        $priorPreflight = Get-MihoJournalPriorStatePreflightV1 -Journal $journal -Paths $paths -Identity $identity -Adapter $Adapter
        if (($null -ne $priorPreflight.OldTask -and -not $priorPreflight.CurrentIsOldDisabled) -or ($null -eq $priorPreflight.OldTask -and $null -ne $priorPreflight.CurrentTask)) {
            throw "Canonical task changed after prepare."
        }
        $canonicalConfig = Resolve-MihoExistingFileV1 -Path $evidence.CanonicalConfig -Label "Prepared update config"
        $manifest = $null
        $transactionCommitted = $false
        $commitRecoveryWarning = ""
        $recoveredRetiredGenerationRemoved = $false
        $legacyRemoved = $false
        try {
            $window = Get-MihoPrepareWindowV1 -Journal $journal
            $now = [DateTimeOffset]::UtcNow
            if ($now -lt $window.Prepared -or $now -gt $window.Expires) {
                throw "Prepared automation evidence expired before commit."
            }
            $null = Invoke-MihoBootstrapTransactionV1 -Adapter $Adapter -Executable $evidence.Generation.Executable -Workspace $evidence.Workspace -TransactionPath $evidence.TransactionPath -Operation "verify" -TimeoutSeconds $ProcessTimeoutSeconds
            $healthResult = Invoke-MihoCheckedProcessV1 -Adapter $Adapter -FilePath $evidence.Generation.Executable -Arguments @("update", "health", "--workspace", $evidence.Workspace, "--config", $evidence.ConfigRelative) -WorkingDirectory $evidence.Workspace -Label "miho update health at commit" -TimeoutSeconds $ProcessTimeoutSeconds
            $commitHealth = ConvertFrom-MihoHealthJsonV1 -Json ([string]$healthResult.StdOut).Trim()
            if ([string]$commitHealth.attempt_id -cne $evidence.ExpectedAttemptId) {
                throw "Commit health does not belong to the prepared candidate attempt."
            }
            Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "RegisterTask" -Arguments @($evidence.CanonicalSpec) | Out-Null
            $canonicalTask = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($identity.TaskName)
            if ($null -eq $canonicalTask -or -not (Test-MihoTaskMatchesSpecV1 -Snapshot $canonicalTask -Spec $evidence.CanonicalSpec)) {
                throw "Canonical task replacement verification failed."
            }
            $manifest = New-MihoOwnershipManifestV1 -Identity $identity -Owner $owner -InstallId $evidence.CanonicalSpec.InstallId -Workspace $evidence.Workspace -ConfigRelative $evidence.ConfigRelative -CanonicalConfig $canonicalConfig -Generation $evidence.Generation -CanonicalTask $canonicalTask -Source $evidence.CanonicalSpec.Source -ScheduleAt $evidence.CanonicalSpec.At
            $manifestBytes = ConvertTo-MihoJsonBytesV1 -Object $manifest
            $journal.new_manifest_sha256 = Get-MihoSha256BytesV1 -Bytes $manifestBytes
            $journal.new_task_xml_sha256 = Get-MihoSha256TextV1 -Text ([string]$canonicalTask.RawXml)
            $journal.new_task_sddl_sha256 = Get-MihoSddlSemanticFingerprintV1 -Sddl ([string]$canonicalTask.Sddl)
            $journal.phase = "canonical-replaced"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
            Write-MihoAtomicBytesV1 -Path $paths.Manifest -Bytes $manifestBytes -Purpose "manifest" -FileHooks $FileHooks
            if ((Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($paths.Manifest))) -cne $journal.new_manifest_sha256 -or
                -not (Test-MihoSnapshotExactlyV1 -Snapshot (Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($identity.TaskName)) -Expected $canonicalTask)) {
                throw "Canonical task or ownership manifest drifted before commit."
            }
            $journal.phase = "committed"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
            $journal.phase = "bootstrap-commit-started"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
            $null = Invoke-MihoBootstrapTransactionV1 -Adapter $Adapter -Executable $evidence.Generation.Executable -Workspace $evidence.Workspace -TransactionPath $evidence.TransactionPath -Operation "commit" -TimeoutSeconds $ProcessTimeoutSeconds
            $transactionCommitted = $true
            $journal.phase = "bootstrap-committed"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
            $null = Invoke-MihoBootstrapTransactionV1 -Adapter $Adapter -Executable $evidence.Generation.Executable -Workspace $evidence.Workspace -TransactionPath $evidence.TransactionPath -Operation "finalize" -CompletedOperation "commit" -TimeoutSeconds $ProcessTimeoutSeconds
            $null = Remove-MihoCommittedInstallUnboundV1 -Paths $paths -Identity $identity -Owner $owner -FileHooks $FileHooks
            $legacyRemoved = Remove-MihoJournalLegacyTaskV1 -Journal $journal -Paths $paths -Adapter $Adapter -FileHooks $FileHooks
        }
        catch {
            $primary = $_
            try {
                $repair = Repair-MihoAutomationJournalCoreV1 -Paths $paths -Identity $identity -Owner $owner -Adapter $Adapter -ProcessTimeoutSeconds $ProcessTimeoutSeconds -FileHooks $FileHooks
                if ($repair.committed) {
                    $transactionCommitted = $true
                    $recoveredRetiredGenerationRemoved = [bool]$repair.retired_generation_removed
                    $legacyRemoved = [bool]$repair.legacy_removed
                    $commitRecoveryWarning = "Bootstrap commit completed and exact committed state was recovered after: $($primary.Exception.Message)"
                    if (-not [string]::IsNullOrWhiteSpace([string]$repair.warning)) { $commitRecoveryWarning += " $($repair.warning)" }
                }
                else {
                    if ($null -ne $handoff) { $handoff = Set-MihoPrepareHandoffTerminalPhaseV1 -Record $handoff -Phase "rolled-back" -FileHooks $FileHooks }
                    $retained = if ([string]::IsNullOrWhiteSpace([string]$repair.retained_transaction)) { "" } else { " Rollback evidence retained at: $($repair.retained_transaction)" }
                    throw "__MIHO_ROLLED_BACK__ Automation commit failed and was rolled back. Primary: $($primary.Exception.Message)$retained"
                }
            }
            catch {
                if ($_.Exception.Message -like "__MIHO_ROLLED_BACK__*") {
                    throw $_.Exception.Message.Substring("__MIHO_ROLLED_BACK__ ".Length)
                }
                throw "Automation commit failed and rollback is pending in the journal. Primary: $($primary.Exception.Message) Rollback: $($_.Exception.Message)"
            }
        }
        if (-not $transactionCommitted) { throw "Automation commit did not reach bootstrap commit." }
        if ($null -ne $handoff) { $handoff = Set-MihoPrepareHandoffTerminalPhaseV1 -Record $handoff -Phase "committed" -FileHooks $FileHooks }

        $retiredGenerationRemoved = $recoveredRetiredGenerationRemoved
        $cleanupWarning = ""
        if (Test-Path -LiteralPath $paths.Journal) {
            $retiredCleanupSucceeded = $true
            try { $retiredGenerationRemoved = Remove-MihoJournalRetiredGenerationV1 -Journal $journal -Paths $paths -FileHooks $FileHooks }
            catch {
                $retiredCleanupSucceeded = $false
                $cleanupWarning = "Exact retired generation cleanup was preserved: $($_.Exception.Message)"
            }
            if ($retiredCleanupSucceeded) {
                try { Remove-MihoFileV1 -Path $paths.Journal -Purpose "journal-commit-cleanup" -FileHooks $FileHooks }
                catch { $cleanupWarning = ($cleanupWarning + " Bootstrap-committed journal cleanup remains pending: $($_.Exception.Message)").Trim() }
            }
        }

        $legacyWarning = ""
        try {
            $legacy = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($script:MihoLegacyTaskNameV1)
            if ($null -ne $legacy) {
                $legacyWarning = "Committed canonical task; legacy task was preserved because no exact authorized XML/SDDL snapshot matched."
            }
        }
        catch { $legacyWarning = "Committed canonical task, but strict legacy cleanup was preserved after an error: $($_.Exception.Message)" }
        $warnings = @($commitRecoveryWarning, $cleanupWarning, $legacyWarning | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        return [pscustomobject][ordered]@{
            schema = "miho-automation-install-result-v1"
            transaction_token = $TransactionToken
            task_name = $identity.TaskName
            workspace = $evidence.Workspace
            config = $evidence.CanonicalConfig
            generation = $evidence.Generation.Generation
            executable = $evidence.Generation.Executable
            exe_sha256 = $evidence.Generation.Sha256
            action_fingerprint = $manifest.action_fingerprint
            candidate_run_token = [string]$journal.candidate_run_token
            health_attempt_id = [string]$journal.health_attempt_id
            healthy = $true
            retired_generation_removed = $retiredGenerationRemoved
            legacy_removed = $legacyRemoved
            warning = [string]::Join(" ", $warnings)
        }
    }
        finally { Exit-MihoAutomationMutexV1 -Mutex $mutex }
    }
    finally { Exit-MihoAutomationCoordinatorV1 -Coordinator $ownerCoordinator }
}

function Rollback-MihoDailyUpdateTaskInstallV1 {
    param(
        [Parameter(Mandatory = $true)][string]$TransactionToken,
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerKind,
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerInstanceId,
        [int]$ProcessTimeoutSeconds = 7200,
        [string]$AutomationRoot,
        [string]$ResultPath,
        [string]$CallerNonce,
        [int64]$CoordinatorPid = 0,
        [hashtable]$Adapter,
        [hashtable]$FileHooks
    )

    if ($TransactionToken -cnotmatch '^[0-9a-f]{32}$' -or $ProcessTimeoutSeconds -le 0) {
        throw "Automation transaction token or timeout is invalid."
    }
    $expectedOwner = New-MihoExpectedOwnerV1 -OwnerKind $ExpectedOwnerKind -OwnerInstanceId $ExpectedOwnerInstanceId
    $handoffRequested = -not [string]::IsNullOrWhiteSpace($ResultPath) -or -not [string]::IsNullOrWhiteSpace($CallerNonce) -or $CoordinatorPid -gt 0
    if ($handoffRequested -and ([string]::IsNullOrWhiteSpace($ResultPath) -or [string]::IsNullOrWhiteSpace($CallerNonce) -or $CoordinatorPid -le 0)) {
        throw "Rollback handoff ResultPath, CallerNonce, and CoordinatorPid are required together."
    }
    $handoff = $null
    if ($handoffRequested) {
        $handoff = Read-MihoPrepareHandoffReceiptV1 -Path $ResultPath -CallerNonce $CallerNonce -ExpectedOwner $expectedOwner -CoordinatorPid $CoordinatorPid
        if ([string]$handoff.Object.transaction_token -cne $TransactionToken) { throw "Rollback handoff transaction token disagrees with the request." }
        if ([string]$handoff.Object.phase -ceq "committed") { throw "Prepared automation transaction is already committed and cannot be rolled back." }
    }
    $ownerSid = Get-MihoCurrentSidV1
    $identity = Get-MihoTaskIdentityV1 -OwnerSid $ownerSid
    $ownerCoordinator = Enter-MihoAutomationCoordinatorV1 -AutomationRoot $AutomationRoot
    try {
        Assert-MihoNoPendingClaimIntentV1 -Coordinator $ownerCoordinator -Identity $identity
        Assert-MihoNoPendingReleaseIntentV1 -Coordinator $ownerCoordinator
        $paths = Get-MihoAutomationPathsV1 -AutomationRoot $ownerCoordinator.Root
        if ($null -eq $Adapter) { $Adapter = New-MihoRealAdapterV1 }
        $mutex = Enter-MihoAutomationMutexV1 -Paths $paths
        try {
        if (Test-Path -LiteralPath $paths.ClaimJournal) { throw "Prepared rollback is blocked by an owner claim journal." }
        $owner = Get-MihoOwnerContextV1 -ExpectedOwner $expectedOwner -Paths $paths -Identity $identity
        if ($null -ne $handoff -and $owner.Epoch -cne [string]$handoff.Object.owner_epoch) {
            throw "Rollback handoff owner epoch is stale."
        }
        if (-not (Test-Path -LiteralPath $paths.Journal)) {
            $existing = Get-MihoRollbackReceiptV1 -TransactionToken $TransactionToken -Paths $paths -Identity $identity -Owner $owner
            if ($null -eq $existing) {
                if ($null -ne $handoff) {
                    $state = Get-MihoInstalledStateV1 -Paths $paths -Identity $identity -Owner $owner -Adapter $Adapter
                    if ($null -ne $state -and (Test-MihoInstalledStateMatchesHandoffV1 -State $state -Owner $owner -Handoff $handoff)) {
                        $handoff = Set-MihoPrepareHandoffTerminalPhaseV1 -Record $handoff -Phase "committed" -FileHooks $FileHooks
                        throw "Prepared automation transaction is already committed and cannot be rolled back."
                    }
                }
                throw "Prepared automation journal is unavailable."
            }
            if ($null -ne $handoff) { $handoff = Set-MihoPrepareHandoffTerminalPhaseV1 -Record $handoff -Phase "rolled-back" -FileHooks $FileHooks }
            return [pscustomobject][ordered]@{
                schema = "miho-automation-rollback-result-v1"
                transaction_token = $TransactionToken
                rolled_back = $true
                idempotent_replay = $true
                retained_transaction = [string]$existing.Object.retained_bootstrap_transaction
                rollback_receipt = $existing.Path
            }
        }
        $record = Read-MihoJsonFileV1 -Path $paths.Journal -MaximumBytes $script:MihoJournalMaximumBytesV1
        $journal = $record.Object
        Assert-MihoJournalIdentityV1 -Journal $journal -Identity $identity -Owner $owner -Paths $paths
        if ([string]$journal.operation -cne "install" -or [string]$journal.transaction_token -cne $TransactionToken) {
            throw "Prepared automation journal does not match this transaction token."
        }
        $repair = Rollback-MihoInstallJournalV1 -Journal $journal -Paths $paths -Identity $identity -Owner $owner -Adapter $Adapter -ProcessTimeoutSeconds $ProcessTimeoutSeconds -FileHooks $FileHooks
        if ($null -ne $handoff) {
            if ($repair.committed) {
                $handoff = Set-MihoPrepareHandoffTerminalPhaseV1 -Record $handoff -Phase "committed" -FileHooks $FileHooks
                throw "Prepared automation transaction crossed the commit boundary and cannot be rolled back."
            }
            $handoff = Set-MihoPrepareHandoffTerminalPhaseV1 -Record $handoff -Phase "rolled-back" -FileHooks $FileHooks
        }
        return [pscustomobject][ordered]@{
            schema = "miho-automation-rollback-result-v1"
            transaction_token = $TransactionToken
            rolled_back = (-not $repair.committed)
            idempotent_replay = $false
            retained_transaction = [string]$repair.retained_transaction
            rollback_receipt = [string]$repair.rollback_receipt
        }
    }
        finally { Exit-MihoAutomationMutexV1 -Mutex $mutex }
    }
    finally { Exit-MihoAutomationCoordinatorV1 -Coordinator $ownerCoordinator }
}

function Uninstall-MihoDailyUpdateTaskV1 {
    param(
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerKind,
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerInstanceId,
        [int]$QuiesceTimeoutSeconds = 30,
        [string]$AutomationRoot,
        [hashtable]$Adapter,
        [hashtable]$FileHooks,
        $CallerCoordinator,
        [switch]$ReserveOwnerRelease
    )

    if ($QuiesceTimeoutSeconds -le 0) {
        throw "Quiesce timeout must be positive."
    }
    $expectedOwner = New-MihoExpectedOwnerV1 -OwnerKind $ExpectedOwnerKind -OwnerInstanceId $ExpectedOwnerInstanceId
    $ownerSid = Get-MihoCurrentSidV1
    $identity = Get-MihoTaskIdentityV1 -OwnerSid $ownerSid
    $ownsCoordinator = $null -eq $CallerCoordinator
    if ($ownsCoordinator) {
        $ownerCoordinator = Enter-MihoAutomationCoordinatorV1 -AutomationRoot $AutomationRoot
    }
    else {
        Assert-MihoAutomationCoordinatorLeaseV1 -Coordinator $CallerCoordinator -AutomationRoot $AutomationRoot
        $ownerCoordinator = $CallerCoordinator
    }
    try {
        Assert-MihoNoPendingClaimIntentV1 -Coordinator $ownerCoordinator -Identity $identity
        $pendingRelease = Read-MihoReleaseIntentV1 -Path $ownerCoordinator.ReleaseIntent -Identity $identity -AutomationRoot $ownerCoordinator.Root
        if (-not $ReserveOwnerRelease -and $null -ne $pendingRelease) {
            throw "Automation owner release is pending explicit same-owner ReleaseClaim recovery."
        }
        if ($null -ne $pendingRelease -and
            ([string]$pendingRelease.Object.owner_kind -cne $expectedOwner.Kind -or
             [string]$pendingRelease.Object.owner_instance_id -cne $expectedOwner.InstanceId)) {
            throw "Pending automation owner release belongs to a different owner instance."
        }
        if ($null -eq $Adapter) { $Adapter = New-MihoRealAdapterV1 }
        if (-not (Test-Path -LiteralPath $ownerCoordinator.Root)) {
            if ($null -ne (Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($identity.TaskName))) {
                throw "Automation root is absent but the canonical task still exists."
            }
            return [pscustomobject][ordered]@{
                schema = "miho-automation-uninstall-result-v1"
                task_name = $identity.TaskName
                removed = $false
                already_absent = $true
                generation_removed = $false
            }
        }
        $paths = Get-MihoAutomationPathsV1 -AutomationRoot $ownerCoordinator.Root
        $mutex = Enter-MihoAutomationMutexV1 -Paths $paths
        try {
        if (Test-Path -LiteralPath $paths.ClaimJournal) { throw "Uninstall is blocked by an owner claim journal." }
        $owner = Get-MihoOwnerContextV1 -ExpectedOwner $expectedOwner -Paths $paths -Identity $identity
        if (Test-Path -LiteralPath $paths.Journal) {
            $pendingRecord = Read-MihoJsonFileV1 -Path $paths.Journal -MaximumBytes $script:MihoJournalMaximumBytesV1
            Assert-MihoJournalIdentityV1 -Journal $pendingRecord.Object -Identity $identity -Owner $owner -Paths $paths
            if ([string]$pendingRecord.Object.operation -ceq "install" -and (Test-MihoExternalPrepareCoordinatorActiveV1 -Journal $pendingRecord.Object)) {
                throw "A prepared automation install is pending explicit Commit or Rollback with its transaction token."
            }
        }
        $null = Repair-MihoAutomationJournalCoreV1 -Paths $paths -Identity $identity -Owner $owner -Adapter $Adapter -FileHooks $FileHooks
        $state = Get-MihoInstalledStateV1 -Paths $paths -Identity $identity -Owner $owner -Adapter $Adapter
        if ($null -eq $state) {
            if ($ReserveOwnerRelease) {
                $unboundRecord = Read-MihoUnboundV1 -Paths $paths -Identity $identity
                if ($null -eq $unboundRecord -or -not (Test-MihoOwnerTripletMatchesV1 -Object $unboundRecord.Object -Owner $owner)) {
                    throw "Clean automation uninstall lacks its exact owner-bound unbound receipt."
                }
                $reservation = Reserve-MihoAutomationOwnerReleaseV1 `
                    -Coordinator $ownerCoordinator `
                    -Paths $paths `
                    -Identity $identity `
                    -Owner $owner `
                    -ExpectedUnboundBytes $unboundRecord.Bytes `
                    -ExistingIntent $pendingRelease `
                    -FileHooks $FileHooks
                $pendingRelease = $reservation.Record
            }
            return [pscustomobject][ordered]@{
                schema = "miho-automation-uninstall-result-v1"
                task_name = $identity.TaskName
                removed = $false
                already_absent = $true
                generation_removed = $false
            }
        }
        $ownedGeneration = Assert-MihoGenerationOwnedV1 -Manifest $state.Manifest -Paths $paths -RequireOnlyExecutable
        $quarantine = Join-Path $paths.Generations (".uninstall-{0}" -f [guid]::NewGuid().ToString("N"))
        $expectedUnboundBytes = Get-MihoExpectedUnboundBytesV1 -ManifestBytes $state.ManifestBytes -Owner $owner -Identity $identity -Paths $paths
        $journal = New-MihoJournalV1 -Operation "uninstall" -Identity $identity -Owner $owner -Paths $paths -OldTask $state.Task -OldManifestBytes $state.ManifestBytes -NewSpec $null -OriginalGenerationPath $ownedGeneration.Directory -QuarantinePath $quarantine
        Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
        $committed = $false
        try {
            if ($ReserveOwnerRelease) {
                $reservation = Reserve-MihoAutomationOwnerReleaseV1 `
                    -Coordinator $ownerCoordinator `
                    -Paths $paths `
                    -Identity $identity `
                    -Owner $owner `
                    -ExpectedUnboundBytes $expectedUnboundBytes `
                    -ExistingIntent $pendingRelease `
                    -FileHooks $FileHooks
                $pendingRelease = $reservation.Record
            }
            Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "DisableTask" -Arguments @($identity.TaskName) | Out-Null
            Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "StopTask" -Arguments @($identity.TaskName, $QuiesceTimeoutSeconds) | Out-Null
            $quiesced = Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($identity.TaskName)
            if ($null -eq $quiesced -or -not (Test-MihoTaskEquivalentExceptEnabledV1 -Snapshot $quiesced -Expected $state.Task)) {
                throw "Canonical task did not enter the exact quiesced state."
            }
            Move-MihoDirectoryV1 -Source $ownedGeneration.Directory -Destination $quarantine -Purpose "uninstall-generation-quarantine" -FileHooks $FileHooks
            $journal.phase = "generation-quarantined"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
            Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "RemoveTask" -Arguments @($identity.TaskName) | Out-Null
            if ($null -ne (Invoke-MihoAdapterV1 -Adapter $Adapter -Operation "GetTask" -Arguments @($identity.TaskName))) {
                throw "Canonical task removal could not be verified."
            }
            Remove-MihoFileV1 -Path $paths.Manifest -Purpose "uninstall-manifest" -FileHooks $FileHooks
            if (Test-Path -LiteralPath $paths.Manifest) {
                throw "Ownership manifest removal could not be verified."
            }
            Write-MihoAtomicBytesV1 -Path $paths.Unbound -Bytes $expectedUnboundBytes -Purpose "uninstall-unbound" -FileHooks $FileHooks
            if ((Get-MihoSha256BytesV1 -Bytes ([System.IO.File]::ReadAllBytes($paths.Unbound))) -cne (Get-MihoSha256BytesV1 -Bytes $expectedUnboundBytes)) {
                throw "Automation unbound receipt write could not be verified."
            }
            $journal.phase = "committed"
            Write-MihoJournalV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
            $committed = $true
        }
        catch {
            $primary = $_
            try {
                $repair = Repair-MihoAutomationJournalCoreV1 -Paths $paths -Identity $identity -Owner $owner -Adapter $Adapter -FileHooks $FileHooks
                if ($repair.committed) { $committed = $true }
                else {
                    if ($ReserveOwnerRelease -and $null -ne $pendingRelease) {
                        Remove-MihoExpectedReleaseIntentV1 -Path $ownerCoordinator.ReleaseIntent -ExpectedBytes $pendingRelease.Bytes -FileHooks $FileHooks
                    }
                    throw "__MIHO_UNINSTALL_ROLLED_BACK__ Automation uninstall failed and was rolled back. Primary: $($primary.Exception.Message)"
                }
            }
            catch {
                if ($_.Exception.Message -like "__MIHO_UNINSTALL_ROLLED_BACK__*") { throw $_.Exception.Message.Substring("__MIHO_UNINSTALL_ROLLED_BACK__ ".Length) }
                throw "Automation uninstall failed and rollback is pending in the journal. Primary: $($primary.Exception.Message) Rollback: $($_.Exception.Message)"
            }
        }
        Remove-MihoJournalQuarantineGenerationV1 -Journal $journal -Paths $paths -FileHooks $FileHooks
        Remove-MihoFileV1 -Path $paths.Journal -Purpose "journal-commit-cleanup" -FileHooks $FileHooks
        return [pscustomobject][ordered]@{
            schema = "miho-automation-uninstall-result-v1"
            task_name = $identity.TaskName
            removed = $true
            already_absent = $false
            generation_removed = $true
        }
    }
        finally { Exit-MihoAutomationMutexV1 -Mutex $mutex }
    }
    finally {
        if ($ownsCoordinator) { Exit-MihoAutomationCoordinatorV1 -Coordinator $ownerCoordinator }
    }
}

function UninstallAndRelease-MihoDailyUpdateTaskV1 {
    param(
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerKind,
        [Parameter(Mandatory = $true)][string]$ExpectedOwnerInstanceId,
        [int]$QuiesceTimeoutSeconds = 30,
        [string]$AutomationRoot,
        [hashtable]$Adapter,
        [hashtable]$FileHooks
    )

    $expectedOwner = New-MihoExpectedOwnerV1 -OwnerKind $ExpectedOwnerKind -OwnerInstanceId $ExpectedOwnerInstanceId
    $identity = Get-MihoTaskIdentityV1 -OwnerSid (Get-MihoCurrentSidV1)
    $coordinator = Enter-MihoAutomationCoordinatorV1 -AutomationRoot $AutomationRoot
    try {
        $pendingRelease = Read-MihoReleaseIntentV1 -Path $coordinator.ReleaseIntent -Identity $identity -AutomationRoot $coordinator.Root
        if ($null -ne $pendingRelease -and
            ([string]$pendingRelease.Object.owner_kind -cne $expectedOwner.Kind -or
             [string]$pendingRelease.Object.owner_instance_id -cne $expectedOwner.InstanceId)) {
            throw "Pending automation owner release belongs to a different owner instance."
        }

        $resumePartialRelease = $null -ne $pendingRelease -and
            (-not (Test-Path -LiteralPath $coordinator.Root) -or
             -not (Test-Path -LiteralPath (Join-Path $coordinator.Root "automation-authority-v1.json")))
        if ($resumePartialRelease) {
            $automation = [pscustomobject][ordered]@{
                schema = "miho-automation-uninstall-result-v1"
                task_name = $identity.TaskName
                removed = $false
                already_absent = $true
                generation_removed = $false
            }
        }
        else {
            $uninstallParameters = @{
                ExpectedOwnerKind = $expectedOwner.Kind
                ExpectedOwnerInstanceId = $expectedOwner.InstanceId
                QuiesceTimeoutSeconds = $QuiesceTimeoutSeconds
                AutomationRoot = $coordinator.Root
                CallerCoordinator = $coordinator
                ReserveOwnerRelease = $true
            }
            if ($null -ne $Adapter) { $uninstallParameters.Adapter = $Adapter }
            if ($null -ne $FileHooks) { $uninstallParameters.FileHooks = $FileHooks }
            $automation = Uninstall-MihoDailyUpdateTaskV1 @uninstallParameters
        }

        if ($null -ne $FileHooks -and $FileHooks.ContainsKey("CompositeCheckpoint")) {
            & $FileHooks["CompositeCheckpoint"] "before-release"
        }

        $releaseParameters = @{
            ExpectedOwnerKind = $expectedOwner.Kind
            ExpectedOwnerInstanceId = $expectedOwner.InstanceId
            AutomationRoot = $coordinator.Root
            CallerCoordinator = $coordinator
        }
        if ($null -ne $Adapter) { $releaseParameters.Adapter = $Adapter }
        if ($null -ne $FileHooks) { $releaseParameters.FileHooks = $FileHooks }
        $claim = Release-MihoAutomationOwnerClaimV1 @releaseParameters
        return [pscustomobject][ordered]@{
            schema = "miho-automation-uninstall-release-result-v1"
            owner_kind = $expectedOwner.Kind
            owner_instance_id = $expectedOwner.InstanceId
            automation = $automation
            claim = $claim
        }
    }
    finally { Exit-MihoAutomationCoordinatorV1 -Coordinator $coordinator }
}

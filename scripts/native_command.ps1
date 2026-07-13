function Invoke-NativeCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$FilePath,

        [AllowEmptyCollection()]
        [string[]]$ArgumentList = @(),

        [string]$FailureMessage = "Native command failed"
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $nativeErrorPreference = Get-Variable `
        -Name PSNativeCommandUseErrorActionPreference `
        -ErrorAction SilentlyContinue
    try {
        # Capture the process exit code ourselves. PowerShell 7 would otherwise
        # turn a non-zero code into a terminating error before $LASTEXITCODE can
        # be copied when both native error handling and EAP=Stop are enabled.
        $ErrorActionPreference = "Stop"
        $PSNativeCommandUseErrorActionPreference = $false
        & $FilePath @ArgumentList
        $exitCode = [int]$LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        if ($null -ne $nativeErrorPreference) {
            Set-Variable `
                -Name PSNativeCommandUseErrorActionPreference `
                -Value $nativeErrorPreference.Value
        }
        else {
            Remove-Variable `
                -Name PSNativeCommandUseErrorActionPreference `
                -Scope Local `
                -ErrorAction SilentlyContinue
        }
    }
    if ($exitCode -ne 0) {
        $exception = [System.Exception]::new("$FailureMessage (exit code $exitCode)")
        $exception.Data["NativeExitCode"] = [int]$exitCode
        throw $exception
    }
}

function Invoke-NativeCommandLine {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Command,

        [string]$FailureMessage = "Native command failed"
    )

    if ($null -eq $Command -or $Command.Length -eq 0) {
        throw "Native command line is empty"
    }
    $arguments = if ($Command.Length -gt 1) {
        @($Command[1..($Command.Length - 1)])
    }
    else {
        @()
    }
    Invoke-NativeCommand `
        -FilePath $Command[0] `
        -ArgumentList $arguments `
        -FailureMessage $FailureMessage
}

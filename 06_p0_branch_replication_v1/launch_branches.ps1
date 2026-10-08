param(
    [Parameter(Mandatory = $true)][string]$Preflight,
    [string]$RunnerValidation,
    [switch]$Smoke
)

$ErrorActionPreference = 'Stop'
$implementationRoot = $PSScriptRoot
$preflightPath = (Resolve-Path -LiteralPath $Preflight).Path
if (-not $Smoke -and -not $RunnerValidation) { throw 'Research branches require RunnerValidation.' }
$runnerPath = if ($RunnerValidation) { (Resolve-Path -LiteralPath $RunnerValidation).Path } else { $null }
$pythonPath = Join-Path $implementationRoot '.venv\Scripts\python.exe'
$runnerScript = Join-Path $implementationRoot 'run_branches.py'
$stageName = if ($Smoke) { '_branch_smoke_cuda_' } else { '_branch_replication_cuda_' }
$jobName = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + $stageName + [guid]::NewGuid().ToString('N').Substring(0, 8)
$jobPath = Join-Path (Join-Path $implementationRoot 'results') $jobName
New-Item -ItemType Directory -Path $jobPath -ErrorAction Stop | Out-Null
$runPath = Join-Path $jobPath 'run'
$stdoutPath = Join-Path $jobPath 'stdout.log'
$stderrPath = Join-Path $jobPath 'stderr.log'
$workerArguments = @('-u', ('"' + $runnerScript + '"'), '--output', ('"' + $runPath + '"'),
                     '--preflight', ('"' + $preflightPath + '"'))
if ($Smoke) { $workerArguments += '--smoke' }
else { $workerArguments += @('--runner-validation', ('"' + $runnerPath + '"')) }

# Normalize duplicate environment-key casing in this launcher process only.
$processEnvironment = [Environment]::GetEnvironmentVariables('Process')
$duplicateGroups = @($processEnvironment.Keys | Group-Object { $_.ToUpperInvariant() } | Where-Object Count -gt 1)
foreach ($group in $duplicateGroups) {
    $canonicalName = $group.Group[0]
    $inheritedValue = [Environment]::GetEnvironmentVariable($canonicalName, 'Process')
    foreach ($key in $group.Group) { [Environment]::SetEnvironmentVariable($key, $null, 'Process') }
    [Environment]::SetEnvironmentVariable($canonicalName, $inheritedValue, 'Process')
}
$worker = Start-Process -FilePath $pythonPath -ArgumentList $workerArguments -WorkingDirectory $implementationRoot `
    -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
$record = [ordered]@{
    launched_at = (Get-Date).ToUniversalTime().ToString('o')
    launcher_pid = $worker.Id
    python = $pythonPath
    output = $runPath
    stdout = $stdoutPath
    stderr = $stderrPath
    preflight = $preflightPath
    runner_validation = $runnerPath
    smoke = [bool]$Smoke
    note = 'Progress records the actual Python PID. Every research branch restores the same 200k parent.'
}
$json = $record | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $jobPath 'process.json'), $json + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
$json

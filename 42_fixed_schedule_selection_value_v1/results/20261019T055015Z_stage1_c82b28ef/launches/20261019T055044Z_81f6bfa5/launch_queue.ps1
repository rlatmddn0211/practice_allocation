param([string]$Campaign)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoRoot '13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe'
if (-not $Campaign) {
    $active = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'ACTIVE_CAMPAIGN.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $Campaign = $active.campaign
}
$campaignPath = (Resolve-Path -LiteralPath $Campaign).Path
$launchId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '_' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$launchDir = Join-Path $campaignPath ('launches\' + $launchId)
New-Item -ItemType Directory -Path $launchDir -ErrorAction Stop | Out-Null
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $launchDir 'launch_queue.ps1')
$processEnvironment = [Environment]::GetEnvironmentVariables('Process')
$duplicateGroups = $processEnvironment.Keys | Group-Object { ([string]$_).ToUpperInvariant() } | Where-Object Count -gt 1
foreach ($group in $duplicateGroups) {
    $chosenKey = [string]$group.Group[0]
    $chosenValue = [string]$processEnvironment[$chosenKey]
    foreach ($entry in $group.Group) { [Environment]::SetEnvironmentVariable([string]$entry, $null, 'Process') }
    [Environment]::SetEnvironmentVariable($chosenKey, $chosenValue, 'Process')
}
$controller = Join-Path $PSScriptRoot 'campaign.py'
$process = Start-Process -FilePath $pythonPath -ArgumentList @('-u', '-B', ('"' + $controller + '"'), 'run', '--campaign', ('"' + $campaignPath + '"')) -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $launchDir 'stdout.log') -RedirectStandardError (Join-Path $launchDir 'stderr.log') -PassThru
$record = @{pid=$process.Id; campaign=$campaignPath; launch_directory=$launchDir; created_at=[DateTime]::UtcNow.ToString('o'); python=$pythonPath}
$record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $launchDir 'launch.json') -Encoding UTF8
$record | ConvertTo-Json

param([string]$Campaign)
$ErrorActionPreference = 'Stop'
$queueRoot = $PSScriptRoot
$pythonPath = Join-Path $queueRoot '.venv\Scripts\python.exe'
if (-not $Campaign) {
    $active = Get-Content -LiteralPath (Join-Path $queueRoot 'ACTIVE_CAMPAIGN.json') -Raw | ConvertFrom-Json
    $Campaign = $active.campaign
}
$campaignPath = (Resolve-Path -LiteralPath $Campaign).Path
$controller = Join-Path $queueRoot 'campaign.py'
$launchId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '_' + [Guid]::NewGuid().ToString('N').Substring(0,6)
$launchDir = Join-Path $campaignPath ('launches\' + $launchId)
New-Item -ItemType Directory -Path $launchDir -ErrorAction Stop | Out-Null
# Windows environment dictionaries may contain both Path and PATH.
$processEnvironment = [Environment]::GetEnvironmentVariables('Process')
$duplicateGroups = $processEnvironment.Keys | Group-Object { ([string]$_).ToUpperInvariant() } | Where-Object Count -gt 1
foreach ($group in $duplicateGroups) {
    $chosenKey = [string]$group.Group[0]
    $chosenValue = [string]$processEnvironment[$chosenKey]
    foreach ($entry in $group.Group) { [Environment]::SetEnvironmentVariable([string]$entry, $null, 'Process') }
    [Environment]::SetEnvironmentVariable($chosenKey, $chosenValue, 'Process')
}
$process = Start-Process -FilePath $pythonPath -ArgumentList @('-u', ('"' + $controller + '"'), 'run', '--campaign', ('"' + $campaignPath + '"')) -WorkingDirectory $queueRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $launchDir 'stdout.log') -RedirectStandardError (Join-Path $launchDir 'stderr.log') -PassThru
$record = @{pid=$process.Id; campaign=$campaignPath; launch_directory=$launchDir; created_at=[DateTime]::UtcNow.ToString('o'); python=$pythonPath}
$record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $launchDir 'launch.json') -Encoding UTF8
$record | ConvertTo-Json

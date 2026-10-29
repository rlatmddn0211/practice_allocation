param([Parameter(Mandatory=$true)][string]$Campaign)
$ErrorActionPreference = 'Stop'
$versionRoot = $PSScriptRoot
$repoRoot = Split-Path -Parent $versionRoot
$taskPython = Join-Path $repoRoot '13_e0_e3_autonomous_queue_v1\.venv\Scripts\python.exe'
$campaignPath = (Resolve-Path -LiteralPath $Campaign).Path
$launcherPath = Join-Path $campaignPath ('launches\' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '_' + [guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $launcherPath | Out-Null
$taskArgs = @('-B', ('"' + (Join-Path $versionRoot 'campaign.py') + '"'), 'run', '--campaign', ('"' + $campaignPath + '"'))
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList $taskArgs -WorkingDirectory $versionRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $launcherPath 'stdout.log') -RedirectStandardError (Join-Path $launcherPath 'stderr.log') -PassThru
@{pid=$taskProcess.Id; campaign=$campaignPath; launched_at=(Get-Date).ToUniversalTime().ToString('o'); window='Hidden'} | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $launcherPath 'process.json')
Write-Output (@{pid=$taskProcess.Id;campaign=$campaignPath;launch=$launcherPath} | ConvertTo-Json -Compress)

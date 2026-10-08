param([string]$Campaign)
$ErrorActionPreference = 'Stop'
if (-not $Campaign) {
    $active = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'ACTIVE_CAMPAIGN.json') -Raw | ConvertFrom-Json
    $Campaign = $active.campaign
}
$campaignPath = (Resolve-Path -LiteralPath $Campaign).Path
$taskName = 'PracticeAllocation_E0_E3_' + (Split-Path $campaignPath -Leaf)
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
$controller = Join-Path $PSScriptRoot 'campaign.py'
$arguments = '"' + $controller + '" run --campaign "' + $campaignPath + '"'
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument $arguments -WorkingDirectory $PSScriptRoot
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$logon = New-ScheduledTaskTrigger -AtLogOn -User $identity
$repeat = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(5)) -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$task = Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($logon,$repeat) -Settings $settings -Principal $principal -Description 'Authorized E0-E3 sequential research queue. Resumes completed 20k jobs, retains failures, stops after E3.'
$record = @{task_name=$task.TaskName; campaign=$campaignPath; registered_at=[DateTime]::UtcNow.ToString('o'); triggers=@('current-user logon','every 5 minutes'); execution='pythonw hidden, one controller, current user'; scope='E0 through E3 only'}
$recordPath = Join-Path $campaignPath ('scheduler_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '.json')
$record | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
$record | ConvertTo-Json

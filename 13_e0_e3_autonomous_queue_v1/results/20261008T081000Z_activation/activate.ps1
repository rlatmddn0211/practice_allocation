$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
$queueRoot = Join-Path $repoRoot '13_e0_e3_autonomous_queue_v1'
$pythonPath = Join-Path $queueRoot '.venv\Scripts\python.exe'
$storageRoot = 'D:\robot_practice_allocation_runs'
$controller = Join-Path $queueRoot 'campaign.py'
$signoff = Get-Content -LiteralPath (Join-Path $queueRoot 'VALIDATION.json') -Raw | ConvertFrom-Json
if (-not $signoff.passed) { throw 'Final validation has not passed.' }

# Preserve code and verification evidence before starting the scientific jobs.
& git -C $repoRoot add .gitattributes .gitignore AGENTS.md README.md 09_fresh_evaluation_audit_v1 10_independent_seed_checkpoint_study_v1 11_fixed_target_donor_swap_v1 12_task_composition_study_v1 13_e0_e3_autonomous_queue_v1
if ($LASTEXITCODE -ne 0) { throw 'Git staging failed.' }
& git -C $repoRoot diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Git whitespace validation failed.' }
& git -C $repoRoot commit -m 'Implement independent E0-E3 studies and resilient sequential queue' > (Join-Path $PSScriptRoot 'code_commit.log')
if ($LASTEXITCODE -ne 0) { throw 'Code commit failed.' }
$codeCommit = (& git -C $repoRoot rev-parse HEAD).Trim()

& $pythonPath $controller prepare --storage-root $storageRoot > (Join-Path $PSScriptRoot 'prepare.log')
if ($LASTEXITCODE -ne 0) { throw 'Campaign preparation failed.' }
$active = Get-Content -LiteralPath (Join-Path $queueRoot 'ACTIVE_CAMPAIGN.json') -Raw | ConvertFrom-Json
$campaign = $active.campaign
& (Join-Path $queueRoot 'register_queue.ps1') -Campaign $campaign > (Join-Path $PSScriptRoot 'registration.log')
$taskName = 'PracticeAllocation_E0_E3_' + (Split-Path $campaign -Leaf)
Start-ScheduledTask -TaskName $taskName
$deadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Seconds 2
    $state = Get-Content -LiteralPath (Join-Path $campaign 'STATUS.json') -Raw | ConvertFrom-Json
    if ($state.state -eq 'integrity_failed' -or $state.state -eq 'failed') {
        throw ('Campaign failed to start: ' + ($state | ConvertTo-Json -Depth 8))
    }
} while ($state.state -ne 'running' -and (Get-Date) -lt $deadline)
if ($state.state -ne 'running') { throw 'The scheduled controller did not confirm a running worker.' }
$taskInfo = Get-ScheduledTaskInfo -TaskName $taskName
$receipt = @{activated_at=[DateTime]::UtcNow.ToString('o'); code_commit=$codeCommit; campaign=$campaign; task_name=$taskName; state=$state.state; current_job=$state.job; worker_pid=$state.worker_pid; controller_pid=$state.controller_pid; storage_root=$storageRoot; task_last_result=$taskInfo.LastTaskResult; next_task_check=$taskInfo.NextRunTime.ToString('o')}
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'activation_receipt.json') -Encoding UTF8
Copy-Item -LiteralPath (Join-Path $campaign 'plan.json') -Destination (Join-Path $PSScriptRoot 'plan.json') -ErrorAction Stop
Copy-Item -LiteralPath (Join-Path $campaign 'plan_integrity.json') -Destination (Join-Path $PSScriptRoot 'plan_integrity.json') -ErrorAction Stop
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'scheduled_task.xml') -Encoding UTF8
Copy-Item -LiteralPath 'D:\robot_practice_allocation_runs\13_e0_e3_autonomous_queue_v1\results\20261008T074926Z_queue_verification_dd1f2d\verification.json' -Destination (Join-Path $PSScriptRoot 'queue_verification.json') -ErrorAction Stop

& git -C $repoRoot add 13_e0_e3_autonomous_queue_v1/results/20261008T081000Z_activation
if ($LASTEXITCODE -ne 0) { throw 'Activation receipt staging failed.' }
& git -C $repoRoot commit -m 'Record scheduled E0-E3 campaign activation and D-drive recovery verification' > (Join-Path $PSScriptRoot 'activation_commit.log')
if ($LASTEXITCODE -ne 0) { throw 'Activation receipt commit failed.' }
# A network publication error must not stop the already running research queue.
$ErrorActionPreference = 'Continue'
& git -C $repoRoot push origin main > (Join-Path $PSScriptRoot 'push.log') 2>&1
$pushExit = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
$receipt.github_push_exit_code = $pushExit
$receipt | ConvertTo-Json -Depth 8

param([int]$Port = 8707)
$ErrorActionPreference = 'Stop'
$reportRoot = $PSScriptRoot
$reportDist = Join-Path $reportRoot 'report_app\dist'
$socket = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
$socket.Start()
$socket.Stop()
$previewName = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '_preview_' + [guid]::NewGuid().ToString('N').Substring(0,8)
$previewPath = Join-Path (Join-Path $reportRoot 'results') $previewName
New-Item -ItemType Directory -Path $previewPath -ErrorAction Stop | Out-Null
$reportEnvironment = [Environment]::GetEnvironmentVariables('Process')
$reportDuplicates = @($reportEnvironment.Keys | Group-Object { $_.ToUpperInvariant() } | Where-Object Count -gt 1)
foreach ($group in $reportDuplicates) {
    $canonicalName = $group.Group[0]
    $inheritedValue = [Environment]::GetEnvironmentVariable($canonicalName, 'Process')
    foreach ($key in $group.Group) { [Environment]::SetEnvironmentVariable($key, $null, 'Process') }
    [Environment]::SetEnvironmentVariable($canonicalName, $inheritedValue, 'Process')
}
$server = Start-Process -FilePath 'C:\Python312\python.exe' -ArgumentList @('-m', 'http.server', $Port, '--bind', '127.0.0.1', '--directory', ('"' + $reportDist + '"')) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $previewPath 'stdout.log') -RedirectStandardError (Join-Path $previewPath 'stderr.log') -PassThru
$record = [ordered]@{ launched_at=(Get-Date).ToUniversalTime().ToString('o'); pid=$server.Id; url="http://127.0.0.1:$Port/"; source_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash; directory=$reportDist }
$json = $record | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $previewPath 'process.json'), $json + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
$json

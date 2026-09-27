param(
    [Parameter(Mandatory = $true)]
    [string]$Executable
)

$ErrorActionPreference = 'Stop'
$resolved = (Resolve-Path -LiteralPath $Executable).Path
$reportPath = Join-Path ([System.IO.Path]::GetTempPath()) ("hand-modeling-" + [guid]::NewGuid().ToString('N') + '.smoke.json')
try {
    $process = Start-Process -FilePath $resolved -ArgumentList @('--smoke-report', $reportPath) -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) { throw "smoke process failed: $($process.ExitCode)" }
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if ($report.state -ne 'start') { throw 'smoke did not start on start page' }
    if ($report.camera_open) { throw 'camera opened during smoke test' }
    if ($report.tracking_running) { throw 'tracking ran during smoke test' }
    if (-not $report.clean_shutdown) { throw 'smoke shutdown was not clean' }

    $process = Start-Process -FilePath $resolved -ArgumentList @('--graphics-smoke-report', $reportPath) -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) { throw "graphics smoke process failed: $($process.ExitCode)" }
    $graphics = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if ($graphics.state -ne 'graphics-ready') { throw "graphics smoke state: $($graphics.state)" }
    if (-not $graphics.graphics_pipe) { throw 'graphics pipe was not created' }
    if ([string]::IsNullOrWhiteSpace($graphics.pipe_type)) { throw 'graphics pipe type was not reported' }
    Write-Output "result: PASS ($resolved; graphics=$($graphics.pipe_type))"
}
finally {
    if (Test-Path -LiteralPath $reportPath) { Remove-Item -LiteralPath $reportPath -Force }
}

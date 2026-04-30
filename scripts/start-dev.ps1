param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [switch]$NoClean
)

$ErrorActionPreference = "Stop"
$rootPath = (Resolve-Path $Root).Path.TrimEnd("\")
$logsPath = Join-Path $rootPath "logs"
$frontendPath = Join-Path $rootPath "frontend"
$python = Join-Path $rootPath "venv\Scripts\python.exe"
$apiUrl = "http://127.0.0.1:55342"
$webUrl = "http://127.0.0.1:55343/#/"

if (-not (Test-Path $python)) {
    throw "Python venv not found: $python"
}

New-Item -ItemType Directory -Force -Path $logsPath | Out-Null

if (-not $NoClean) {
    & (Join-Path $PSScriptRoot "stop-dev.ps1") -Root $rootPath | Out-Null
    Start-Sleep -Seconds 1
}

Start-Process `
    -FilePath $python `
    -ArgumentList @("api\api_server.py") `
    -WorkingDirectory $rootPath `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logsPath "api_stdout.log") `
    -RedirectStandardError (Join-Path $logsPath "api_stderr.log")

$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        Invoke-RestMethod -Uri "$apiUrl/api/status" -TimeoutSec 2 | Out-Null
        $ready = $true
        break
    } catch {
        $ready = $false
    }
}

if (-not $ready) {
    throw "VoiceType API did not become ready at $apiUrl. See logs\api_stderr.log."
}

if (Test-Path (Join-Path $frontendPath "node_modules")) {
    Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList @("/c", "npm run dev -- --host 127.0.0.1 --port 55343 > ..\logs\frontend_dev.log 2>&1") `
        -WorkingDirectory $frontendPath `
        -WindowStyle Hidden
} else {
    Write-Warning "frontend\node_modules is missing. Run: cd frontend && npm install"
}

$startAll = Invoke-RestMethod -Uri "$apiUrl/api/start-all" -Method Post -TimeoutSec 60

$asrReady = $false
for ($i = 0; $i -lt 300; $i++) {
    Start-Sleep -Seconds 1
    $listener = Get-NetTCPConnection -LocalPort 55341 -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        $asrReady = $true
        break
    }
}

if (-not $asrReady) {
    throw "ASR server did not open port 55341 within 300 seconds. See logs\managed_server_*.log and logs\asr_engine_*.log."
}

Write-Host "VoiceType API: $apiUrl"
Write-Host "VoiceType Web: $webUrl"
Write-Host "ASR start status: server=$($startAll.server.status) client=$($startAll.client.status)"

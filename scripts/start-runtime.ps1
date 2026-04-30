param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$rootPath = (Resolve-Path $Root).Path.TrimEnd("\")
$logsPath = Join-Path $rootPath "logs"
$python = Join-Path $rootPath "venv\Scripts\python.exe"
$apiUrl = "http://127.0.0.1:55342"

if (-not (Test-Path $python)) {
    throw "Python venv not found: $python"
}

New-Item -ItemType Directory -Force -Path $logsPath | Out-Null

$apiReady = $false
try {
    Invoke-RestMethod -Uri "$apiUrl/api/status" -TimeoutSec 2 | Out-Null
    $apiReady = $true
} catch {
    $apiReady = $false
}

if (-not $apiReady) {
    Start-Process `
        -FilePath $python `
        -ArgumentList @("api\api_server.py") `
        -WorkingDirectory $rootPath `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logsPath "api_stdout.log") `
        -RedirectStandardError (Join-Path $logsPath "api_stderr.log")

    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        try {
            Invoke-RestMethod -Uri "$apiUrl/api/status" -TimeoutSec 2 | Out-Null
            $apiReady = $true
            break
        } catch {
            $apiReady = $false
        }
    }
}

if (-not $apiReady) {
    throw "VoiceType API did not become ready at $apiUrl. See logs\api_stderr.log."
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

Write-Host "VoiceType runtime ready: API=$apiUrl ASR=127.0.0.1:55341 server=$($startAll.server.status) client=$($startAll.client.status)"

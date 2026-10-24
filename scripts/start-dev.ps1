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

& (Join-Path $PSScriptRoot "start-runtime.ps1") -Root $rootPath
if (Test-Path (Join-Path $frontendPath "node_modules")) {
    $node = (Get-Command node.exe).Source
    $vite = Join-Path $frontendPath "node_modules/vite/bin/vite.js"
    Start-Process -FilePath $node -ArgumentList ('"' + $vite + '" --host 127.0.0.1 --port 55343 --strictPort') -WorkingDirectory $frontendPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logsPath "frontend_stdout.log") -RedirectStandardError (Join-Path $logsPath "frontend_stderr.log") | Out-Null
} else {
    Write-Warning "Run npm ci in frontend before starting Live UI."
}

Write-Host "VoiceType API: $apiUrl"
Write-Host "VoiceType Web: $webUrl"
Write-Host "Select/download a model in Settings, then apply recognition settings."

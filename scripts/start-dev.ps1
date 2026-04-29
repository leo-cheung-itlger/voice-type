param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$rootPath = (Resolve-Path $Root).Path
$logsPath = Join-Path $rootPath "logs"
$frontendPath = Join-Path $rootPath "frontend"
$python = Join-Path $rootPath "venv\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $logsPath | Out-Null

Start-Process `
    -FilePath $python `
    -ArgumentList @("api\api_server.py") `
    -WorkingDirectory $rootPath `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logsPath "api_stdout.log") `
    -RedirectStandardError (Join-Path $logsPath "api_stderr.log")

Start-Sleep -Seconds 2

if (Test-Path (Join-Path $frontendPath "node_modules")) {
    Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList @("/c", "npm run dev -- --host 127.0.0.1 > ..\logs\frontend_dev.log 2>&1") `
        -WorkingDirectory $frontendPath `
        -WindowStyle Hidden
} else {
    Write-Warning "frontend\node_modules is missing. Run: cd frontend && npm install"
}

Write-Host "VoiceType API: http://127.0.0.1:52342"
Write-Host "VoiceType Web: http://127.0.0.1:52343/#/"

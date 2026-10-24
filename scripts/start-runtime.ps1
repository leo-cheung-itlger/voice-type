param([string]$Root = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = "Stop"
$rootPath = (Resolve-Path -LiteralPath $Root).Path
$python = Join-Path $rootPath "runtime\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = Join-Path $rootPath "venv\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $python)) { throw "Application Python is missing. Extract the complete portable package." }
$logs = Join-Path $rootPath "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
try {
    $response = Invoke-RestMethod "http://127.0.0.1:55342/api/identity" -TimeoutSec 3
    if ($response.root -eq $rootPath) { exit 0 }
    throw "Port 55342 belongs to another VoiceType directory. Close that copy first."
} catch {
    if (Get-NetTCPConnection -LocalPort 55342 -State Listen -ErrorAction SilentlyContinue) {
        throw "Port 55342 is occupied. Close the other application first."
    }
}
$script = Join-Path $rootPath "api\api_server.py"
Start-Process -FilePath $python -ArgumentList ('"' + $script + '"') -WorkingDirectory $rootPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "api_stdout.log") -RedirectStandardError (Join-Path $logs "api_stderr.log") | Out-Null
# Opening the UI never requires an installed/loaded model.
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-RestMethod "http://127.0.0.1:55342/api/identity" -TimeoutSec 2
        if ($response.root -eq $rootPath) { exit 0 }
    } catch { }
}
throw "VoiceType API did not start. See logs\api_stderr.log."

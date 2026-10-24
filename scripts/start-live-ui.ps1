# 开发入口：仅用于 Vite 浏览器联调。发行包请双击 VoiceType.exe，
# 它会打开 Tauri 原生窗口并把运行时放到托盘。
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$Route = "/#/",
    [switch]$NoClean,
    [switch]$RefreshDependencies
)

$ErrorActionPreference = "Stop"
$rootPath = (Resolve-Path $Root).Path.TrimEnd("\")
$frontendPath = Join-Path $rootPath "frontend"
$logsPath = Join-Path $rootPath "logs"
$python = Join-Path $rootPath "venv\Scripts\python.exe"
$startDev = Join-Path $PSScriptRoot "start-dev.ps1"
$webBase = "http://127.0.0.1:55343"
$createdVenv = $false

function Resolve-CommandPath {
    param([string[]]$Names)
    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    return $null
}

function Wait-HttpReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 90
    )
    for ($i = 0; $i -lt $TimeoutSeconds; $i++) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
            return $true
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    return $false
}

if (-not (Test-Path $frontendPath)) {
    throw "Frontend directory not found: $frontendPath"
}

New-Item -ItemType Directory -Force -Path $logsPath | Out-Null

if (-not (Test-Path $python)) {
    $systemPython = Resolve-CommandPath @("python.exe", "py.exe")
    if (-not $systemPython) {
        throw "Python is required to create the local venv."
    }
    Write-Host "Creating Python virtual environment..."
    & $systemPython -m venv (Join-Path $rootPath "venv")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create Python virtual environment."
    }
    $createdVenv = $true
}

if (-not (Test-Path $python)) {
    throw "Python venv not found after setup: $python"
}

if ($createdVenv -or $RefreshDependencies) {
    Write-Host "Installing/updating Python dependencies..."
    & $python -m pip install -r (Join-Path $rootPath "requirements.txt") -q
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install Python dependencies."
    }
}

if (-not (Test-Path (Join-Path $frontendPath "node_modules"))) {
    $npm = Resolve-CommandPath @("npm.cmd", "npm.exe", "npm")
    if (-not $npm) {
        throw "npm is required to install frontend dependencies."
    }
    Write-Host "Installing frontend dependencies..."
    & $npm install --prefix $frontendPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install frontend dependencies."
    }
}

if ($NoClean) {
    & $startDev -Root $rootPath -NoClean
} else {
    & $startDev -Root $rootPath
}

if (-not (Wait-HttpReady -Url "$webBase/" -TimeoutSeconds 90)) {
    throw "Frontend dev server did not become ready at $webBase. See logs\frontend_dev.log."
}

$normalizedRoute = if ($Route.StartsWith("/")) { $Route } else { "/$Route" }
$webUrl = "$webBase$normalizedRoute"
Start-Process $webUrl

Write-Host "VoiceType Live UI ready:"
Write-Host "  Web: $webUrl"
Write-Host "  API: http://127.0.0.1:55342"
Write-Host "  ASR: 127.0.0.1:55341"

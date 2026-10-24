param([string]$Root = (Split-Path -Parent $PSScriptRoot), [string]$Version = "1.0.0-alpha.1", [string]$TargetRelease = "", [switch]$WithCuda, [switch]$UseInstalled)
$ErrorActionPreference = "Stop"
$rootPath = (Resolve-Path -LiteralPath $Root).Path
$python = Join-Path $rootPath "venv\Scripts\python.exe"
if (-not $TargetRelease) { $TargetRelease = Join-Path $rootPath "frontend\src-tauri\target-codex-build7\release" }
$exe = Join-Path $TargetRelease "voicetype.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "Build the desktop EXE first: $exe" }
$dotnet = (Get-Command dotnet.exe -ErrorAction Stop).Source
& $dotnet publish (Join-Path $rootPath "tools\windows_voice_capture\VoiceCaptureHelper.csproj") -c Release -r win-x64 --self-contained true -p:Platform=x64 -o (Join-Path $rootPath "tools\windows_voice_capture\publish")
if ($LASTEXITCODE -ne 0) { throw "Capture helper publish failed" }
$buildArgs = @((Join-Path $rootPath "scripts\build_portable.py"), "--version", $Version, "--exe", $exe)
if ($WithCuda) { $buildArgs += "--cuda" }
if ($UseInstalled) { $buildArgs += "--installed" }
& $python @buildArgs
if ($LASTEXITCODE -ne 0) { throw "Portable build failed" }

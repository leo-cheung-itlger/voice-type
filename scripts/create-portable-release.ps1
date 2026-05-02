param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$Version = "1.0.0",
    [string]$TargetRelease = ""
)

$ErrorActionPreference = "Stop"
$rootPath = (Resolve-Path $Root).Path.TrimEnd("\")
$releaseRoot = Join-Path $rootPath "dist\releases\VoiceType-$Version"
$frontendTauri = Join-Path $rootPath "frontend\src-tauri"

if (-not $TargetRelease) {
    $normal = Join-Path $frontendTauri "target\release\voicetype.exe"
    if (Test-Path $normal) {
        $TargetRelease = (Split-Path -Parent $normal)
    } else {
        $candidate = Get-ChildItem -Path $frontendTauri -Directory -Filter "target-codex-build*" |
            ForEach-Object { Join-Path $_.FullName "release\voicetype.exe" } |
            Where-Object { Test-Path $_ } |
            Sort-Object { (Get-Item $_).LastWriteTime } -Descending |
            Select-Object -First 1
        if ($candidate) {
            $TargetRelease = Split-Path -Parent $candidate
        }
    }
}

$sourceExe = Join-Path $TargetRelease "voicetype.exe"
if (-not (Test-Path $sourceExe)) {
    throw "Cannot find built EXE. Expected: $sourceExe"
}

New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
Copy-Item -LiteralPath $sourceExe -Destination (Join-Path $releaseRoot "VoiceType-$Version-portable.exe") -Force

$readme = @"
# VoiceType $Version Portable

Open this file:

VoiceType-$Version-portable.exe

Do not open EXE files from target\release\deps, target\release\build, or target-codex-build*\deps.

This portable alpha uses the project runtime at:
$rootPath

If the app cannot connect, run:
powershell -NoProfile -ExecutionPolicy Bypass -File "$rootPath\scripts\stop-dev.ps1" -Root "$rootPath"
powershell -NoProfile -ExecutionPolicy Bypass -File "$rootPath\scripts\start-runtime.ps1" -Root "$rootPath"
"@

Set-Content -LiteralPath (Join-Path $releaseRoot "README.txt") -Value $readme -Encoding UTF8
Write-Host "Portable release ready: $(Join-Path $releaseRoot "VoiceType-$Version-portable.exe")"

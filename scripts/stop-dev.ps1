param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "SilentlyContinue"
$rootPath = (Resolve-Path $Root).Path

$patterns = @(
    "api_server.py",
    "vite.js",
    "npm run dev -- --host 127.0.0.1"
)

Get-CimInstance Win32_Process |
    Where-Object {
        $cmd = $_.CommandLine
        if (-not $cmd) { return $false }
        if ($cmd.IndexOf($rootPath, [System.StringComparison]::OrdinalIgnoreCase) -lt 0 -and
            $cmd.IndexOf("voice-type", [System.StringComparison]::OrdinalIgnoreCase) -lt 0 -and
            $cmd.IndexOf("api_server.py", [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
            return $false
        }
        foreach ($pattern in $patterns) {
            if ($cmd -like "*$pattern*") { return $true }
        }
        return $false
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
    }

Write-Host "Stopped VoiceType API/frontend dev processes."

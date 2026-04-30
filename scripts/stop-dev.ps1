param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "SilentlyContinue"
$rootPath = (Resolve-Path $Root).Path.TrimEnd("\")
$currentPid = $PID
$patterns = @(
    "asr_server.py",
    "client_core.py",
    "npm run dev -- --host 127.0.0.1 --port 55343",
    "vite"
)

function Test-VoiceTypeProcess {
    param($Process)
    $CommandLine = $Process.CommandLine
    $Name = $Process.Name
    if (-not $CommandLine) { return $false }
    if ($Name -eq "python.exe" -and
        $CommandLine.IndexOf("api_server.py", [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        ($CommandLine.IndexOf($rootPath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -or
         $CommandLine.IndexOf("api\api_server.py", [System.StringComparison]::OrdinalIgnoreCase) -ge 0)) {
        return $true
    }
    if ($CommandLine.IndexOf($rootPath, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
        return $false
    }
    if ($Name -notin @("python.exe", "node.exe", "cmd.exe", "esbuild.exe")) {
        return $false
    }
    foreach ($pattern in $patterns) {
        if ($CommandLine.IndexOf($pattern, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            return $true
        }
    }
    return $false
}

foreach ($port in @(55341, 55342, 55343)) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object {
            if ($_.OwningProcess -ne $currentPid) {
                Stop-Process -Id $_.OwningProcess -Force
            }
        }
}

Start-Sleep -Milliseconds 300

Get-CimInstance Win32_Process |
    Where-Object {
        $_.ProcessId -ne $currentPid -and (Test-VoiceTypeProcess $_)
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
    }

Write-Host "Stopped VoiceType API/frontend/ASR/client processes for $rootPath."

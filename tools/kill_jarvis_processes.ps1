$ErrorActionPreference = "SilentlyContinue"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue

function Get-ListeningPids {
    param([int]$Port)
    $pids = @()

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        if ($conn.OwningProcess -gt 0) {
            $pids += [int]$conn.OwningProcess
        }
    }

    $netstatRows = netstat -ano
    foreach ($row in $netstatRows) {
        if ($row -notmatch ":$Port\s+") {
            continue
        }
        if ($row -notmatch "LISTENING") {
            continue
        }
        if ($row -match "\s+(\d+)\s*$") {
            $pidValue = [int]$Matches[1]
            if ($pidValue -gt 0) {
                $pids += $pidValue
            }
        }
    }

    return $pids | Select-Object -Unique
}

function Test-JarvisProcess {
    param([int]$ProcessId)

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return $false
    }

    if ($process.ProcessName -match "^(python|pythonw|node|electron|JarvisBackend|JARVIS-PC-V2|JARVIS PC V2)$") {
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
        $commandLine = [string]$cim.CommandLine
        if ($commandLine -like "*$root*" -or $commandLine -like "*Jarvis PC V2*" -or $commandLine -like "*run_backend.py*") {
            return $true
        }
    }

    return $false
}

Write-Host "Stopping JARVIS PC V2 processes..."

$backendPort = 18000
if ($env:JARVIS_BACKEND_PORT) {
    $backendPort = [int]$env:JARVIS_BACKEND_PORT
}

Write-Host "Checking for active listening processes on port $backendPort..."

$listeningPids = @(Get-ListeningPids -Port $backendPort)
foreach ($pidToKill in $listeningPids) {
    if (Test-JarvisProcess -ProcessId $pidToKill) {
        Write-Host "Stopping JARVIS process ID $pidToKill holding port $backendPort..."
        Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
    }
    else {
        Write-Host "Port $backendPort is held by non-JARVIS or stale PID $pidToKill. Leaving it untouched."
    }
}

Get-Process -Name "JarvisBackend" -ErrorAction SilentlyContinue | Stop-Process -Force

Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -like "JARVIS-PC-V2*" -or $_.ProcessName -eq "JARVIS PC V2"
} | Stop-Process -Force

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    ($_.Name -match "^(node|electron)\.exe$") -and ($_.CommandLine -like "*$root*" -or $_.CommandLine -like "*Jarvis PC V2*")
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "Process cleanup complete."

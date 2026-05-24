# Jarvis PC V2 Smoke Runtime Verification Script
# Phase 2.2.1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\.."

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "STEP 1: Checking Codebase Source Format" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
& python "$ProjectRoot\tools\check_source_format.py"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Source formatting check failed!"
    exit 1
}

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "STEP 2: Freeing Port 8000" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
& "$ProjectRoot\tools\kill_jarvis_processes.ps1"
Start-Sleep -Seconds 3


$port = "8001"
$env:JARVIS_BACKEND_PORT = $port

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "STEP 3: Launching Jarvis PC V2 Backend on port $port" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
$BackendDir = "$ProjectRoot\backend"
$Process = Start-Process -FilePath "python" -ArgumentList "run_backend.py" -WorkingDirectory $BackendDir -PassThru -NoNewWindow

Write-Host "Waiting for backend to spin up and respond to /health..." -ForegroundColor Gray
$maxRetries = 15
$alive = $false
for ($i = 1; $i -le $maxRetries; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -Method Get
        if ($health.ok -eq $true -and $health.data.service -eq "jarvis-pc-v2-backend") {
            $alive = $true
            break
        }
    }
    catch {
        # ignore connection error and wait
    }
    Start-Sleep -Seconds 1
}

if (-not $alive) {
    Write-Error "Backend failed to respond to health check in time."
    if ($Process) { Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue }
    exit 1
}
Write-Host "[+] Backend is alive and running!" -ForegroundColor Green

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "STEP 4: Testing Endpoints Validity" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

$endpoints = @(
    "health",
    "debug/startup",
    "runtime/process-info",
    "settings",
    "commands",
    "voice/tts-status",
    "voice/devices",
    "voice/listener-status"
)

foreach ($ep in $endpoints) {
    Write-Host "Checking GET http://127.0.0.1:$port/$ep ..." -ForegroundColor Gray
    try {
        $res = Invoke-RestMethod -Uri "http://127.0.0.1:$port/$ep" -Method Get
        if ($res.ok -eq $false -and $ep -ne "voice/listener-status") {
            # listener-status ok can be false if disabled, but should still respond
            Write-Error "Endpoint /$ep returned ok=false!"
            if ($Process) { Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue }
            exit 1
        }
        Write-Host "  [+] /$ep OK!" -ForegroundColor Green
    }
    catch {
        Write-Error "Failed to call endpoint /$ep : $_"
        if ($Process) { Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue }
        exit 1
    }
}

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "STEP 5: Testing Assistant Query Routing" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
try {
    $bytes = @(208, 148, 208, 182, 208, 176, 209, 128, 208, 178, 208, 184, 209, 129, 44, 32, 208, 186, 208, 176, 208, 186, 32, 208, 180, 208, 181, 208, 187, 208, 176, 63)
    $textVal = [System.Text.Encoding]::UTF8.GetString($bytes)
    $body = @{
        text = $textVal
        speak = $false
        source = "smoke"
        context = @{}
    } | ConvertTo-Json

    Write-Host "Sending POST /assistant/ask..." -ForegroundColor Gray
    $res = Invoke-RestMethod -Uri "http://127.0.0.1:$port/assistant/ask" -Method Post -Body $body -ContentType "application/json"
    
    if (-not $res.ok) {
        Write-Error "Assistant ask query failed!"
        if ($Process) { Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue }
        exit 1
    }
    
    Write-Host "  [+] Ask Query OK!" -ForegroundColor Green
    Write-Host "  [+] Response: $($res.text)" -ForegroundColor Gray
}
catch {
    Write-Error "Failed to query assistant ask endpoint: $_"
    if ($Process) { Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue }
    exit 1
}

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "STEP 6: Stopping Jarvis PC V2 Backend" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
if ($Process) {
    Stop-Process -Id $Process.Id -Force
    Write-Host "[+] Backend stopped cleanly." -ForegroundColor Green
}

Write-Host "`n[+++] SMOKE RUNTIME VERIFICATION SUCCESSFUL! [+++]" -ForegroundColor Green
exit 0

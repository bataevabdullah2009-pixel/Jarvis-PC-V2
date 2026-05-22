param (
    [switch]$Pull
)

$ErrorActionPreference = "Stop"

# Determine project root
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# Verify project paths
if (!(Test-Path "$root\backend")) {
    throw "Backend directory not found at $root\backend"
}
if (!(Test-Path "$root\frontend")) {
    throw "Frontend directory not found at $root\frontend"
}
if (!(Test-Path "$root\backend\requirements.txt")) {
    throw "requirements.txt not found at $root\backend\requirements.txt"
}
if (!(Test-Path "$root\frontend\package.json")) {
    throw "package.json not found at $root\frontend\package.json"
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   JARVIS PC V2 - FRESH DEV RUNNER" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Graceful clean-up of any previous runs
Write-Host "Cleaning up old processes..." -ForegroundColor Yellow
& "$PSScriptRoot\kill_jarvis_processes.ps1"

# 2. Pull changes if -Pull is supplied
if ($Pull) {
    Write-Host "Pulling latest changes from git repository..." -ForegroundColor Yellow
    git pull
}

# 3. Verify Python and Node
Write-Host "Verifying environment dependencies..." -ForegroundColor Yellow
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python is not installed or not in PATH! Cannot start backend."
}
if (!(Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Error "Node.js is not installed or not in PATH! Cannot start frontend."
}

# 4. Set Dev Environment variables
$env:JARVIS_FRONTEND_URL = "http://127.0.0.1:5173"
$env:JARVIS_BACKEND_PORT = "8000"
$env:JARVIS_FRONTEND_MODE = "dev"
$env:JARVIS_PROJECT_ROOT = $root

# 5. Start Backend from source in a separate window
Write-Host "Launching FastAPI Backend..." -ForegroundColor Yellow
$backendProc = Start-Process cmd -ArgumentList "/c title JARVIS Backend && python run_backend.py" -WorkingDirectory "$root\backend" -PassThru -WindowStyle Normal

# 6. Start Frontend Dev Server (Vite) in a separate window
Write-Host "Launching Vite Frontend Dev Server..." -ForegroundColor Yellow
$frontendProc = Start-Process cmd -ArgumentList "/c title JARVIS Frontend Dev && npm run dev" -WorkingDirectory "$root\frontend" -PassThru -WindowStyle Normal

# 7. Poll Backend health (max 20 seconds)
Write-Host "Waiting for backend to become ready..." -ForegroundColor Yellow
$backendReady = $false
$maxRetries = 20
for ($i = 1; $i -le $maxRetries; $i++) {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 1 -ErrorAction Stop
        # Support both raw response and envelope response
        if ($response.ok -eq $true -or $response.status -eq "ok" -or $response.data.status -eq "ok") {
            $backendReady = $true
            Write-Host "Backend is ready after $i seconds!" -ForegroundColor Green
            break
        }
    }
    catch {
        # Silent retry
    }
    Write-Host "Polling backend health ($i/$maxRetries)..." -ForegroundColor Gray
    Start-Sleep -Seconds 1
}

if (-not $backendReady) {
    Write-Host "==================================================" -ForegroundColor Red
    Write-Host "ERROR: Backend failed to respond within 20 seconds!" -ForegroundColor Red
    Write-Host "Check backend logs or open http://127.0.0.1:8000/debug/startup" -ForegroundColor Red
    Write-Host "==================================================" -ForegroundColor Red
    
    if ($backendProc) {
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontendProc) {
        Stop-Process -Id $frontendProc.Id -Force -ErrorAction SilentlyContinue
    }
    & "$PSScriptRoot\kill_jarvis_processes.ps1"
    throw "Backend startup timeout"
}

# 8. Show console addresses
Write-Host ""
Write-Host "--------------------------------------------------" -ForegroundColor Cyan
Write-Host "   JARVIS DEV SERVERS RUNNING" -ForegroundColor Green
Write-Host "   Backend:  http://127.0.0.1:8000" -ForegroundColor Yellow
Write-Host "   Frontend: http://127.0.0.1:5173" -ForegroundColor Yellow
Write-Host "--------------------------------------------------" -ForegroundColor Cyan
Write-Host ""

# 9. Launch Electron dev mode in the foreground (blocking)
try {
    Write-Host "Launching Electron Dev Client..." -ForegroundColor Green
    Set-Location "$root\frontend"
    npm run electron
}
catch {
    Write-Host "An error occurred while running Electron: $_" -ForegroundColor Red
}
finally {
    # 10. Clean up background tasks cleanly when Electron exits
    Write-Host "Electron closed. Terminating background dev servers..." -ForegroundColor Yellow
    
    if ($backendProc) {
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontendProc) {
        Stop-Process -Id $frontendProc.Id -Force -ErrorAction SilentlyContinue
    }
    
    # Run the standard kill script to ensure clean ports
    & "$PSScriptRoot\kill_jarvis_processes.ps1"
    
    Write-Host "Cleanup complete. Goodbye!" -ForegroundColor Green
}

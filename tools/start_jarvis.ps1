# start_jarvis.ps1 - Core launcher for JARVIS PC V2
# Implements full lifetime stabilization, port protection, dependency scanning

$ErrorActionPreference = "Stop"

# 1. Determine project root
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "    JARVIS PC V2 - MAIN LAUNCHER STABILIZER" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan

# Set Environment variables
$env:JARVIS_FRONTEND_URL = "http://127.0.0.1:5173"
$env:JARVIS_BACKEND_PORT = "8000"
$env:JARVIS_FRONTEND_MODE = "dev"
$env:JARVIS_PROJECT_ROOT = $root
$env:JARVIS_LAUNCHER = "START_JARVIS"

# 2. Cleanup old JARVIS processes
Write-Host "Cleaning up old JARVIS processes..." -ForegroundColor Yellow
& "$PSScriptRoot\kill_jarvis_processes.ps1"

# 3. Port 8000 Lock Protection (Task 4)
Write-Host "Verifying Port 8000 availability..." -ForegroundColor Yellow
$netstatOut = netstat -ano | findstr :8000
if ($netstatOut) {
    Write-Host "Port 8000 is occupied. Analyzing processes..." -ForegroundColor Yellow
    foreach ($line in $netstatOut) {
        if ($line -match "\s+LISTENING\s+(\d+)$" -or $line -match "\s+(\d+)$") {
            $pidStr = $Matches[1].Trim()
            $pidVal = 0
            if ([int]::TryParse($pidStr, [ref]$pidVal) -and $pidVal -gt 0) {
                $proc = Get-Process -Id $pidVal -ErrorAction SilentlyContinue
                if ($proc) {
                    $procName = $proc.ProcessName
                    $isJarvisRelated = ($procName -match "^(python|node|electron|JarvisBackend|JARVIS-PC-V2|JARVIS PC V2)$")
                    
                    if ($isJarvisRelated) {
                        Write-Host "Found active JARVIS process: '$procName' (PID $pidVal) on port 8000. Terminating..." -ForegroundColor Yellow
                        Stop-Process -Id $pidVal -Force -ErrorAction SilentlyContinue
                    } else {
                        Write-Host "WARNING: Unknown process '$procName' (PID $pidVal) is holding port 8000!" -ForegroundColor Red
                        $choice = Read-Host "Do you want to terminate this process to free port 8000? (Y/N)"
                        if ($choice -eq "Y" -or $choice -eq "y") {
                            Write-Host "Terminating process '$procName' (PID $pidVal)..." -ForegroundColor Yellow
                            Stop-Process -Id $pidVal -Force -ErrorAction SilentlyContinue
                        } else {
                            Write-Error "Port 8000 is occupied by unknown process '$procName'. Cannot start."
                            exit 1
                        }
                    }
                }
            }
        }
    }
    
    # Wait for OS to release socket
    Start-Sleep -Seconds 2
    
    # Check again
    $netstatCheck = netstat -ano | findstr :8000
    if ($netstatCheck) {
        Write-Error "Failed to release port 8000! Process might still be active."
        exit 1
    }
    Write-Host "Port 8000 is now successfully free!" -ForegroundColor Green
} else {
    Write-Host "Port 8000 is free." -ForegroundColor Green
}

# 4. Perform Git Pull
Write-Host "Pulling latest changes from git repository..." -ForegroundColor Yellow
try {
    git pull
} catch {
    Write-Host "Warning: Git pull failed. Starting with local copy." -ForegroundColor Yellow
}

# 5. Check backend\.env
Write-Host "Verifying backend configuration environment (.env)..." -ForegroundColor Yellow
if (!(Test-Path "$root\backend\.env")) {
    if (Test-Path "$root\.env") {
        Write-Host "Copying .env from project root to backend directory..." -ForegroundColor Green
        Copy-Item -Path "$root\.env" -Destination "$root\backend\.env" -Force
    } elseif (Test-Path "$root\.env.example") {
        Write-Host "Creating default backend .env from .env.example..." -ForegroundColor Green
        Copy-Item -Path "$root\.env.example" -Destination "$root\backend\.env" -Force
    } else {
        Write-Host "Warning: No .env configuration file found!" -ForegroundColor Red
    }
}

# 6. Verify Backend dependencies
Write-Host "Verifying backend python dependencies..." -ForegroundColor Yellow
try {
    python -c "import fastapi, uvicorn, pydantic, dotenv, sounddevice, pyttsx3, pygame, anyio" 2>$null
    Write-Host "[+] Python packages are satisfied." -ForegroundColor Green
} catch {
    Write-Host "Missing required packages. Installing from requirements.txt..." -ForegroundColor Yellow
    python -m pip install -r "$root\backend\requirements.txt"
}

# 7. Verify Frontend dependencies
Write-Host "Verifying frontend node dependencies..." -ForegroundColor Yellow
if (!(Test-Path "$root\frontend\node_modules")) {
    Write-Host "node_modules not found in frontend. Installing dependencies via npm..." -ForegroundColor Yellow
    $oldDir = Get-Location
    Set-Location "$root\frontend"
    npm.cmd install
    Set-Location $oldDir
    Write-Host "[+] Frontend packages installed successfully." -ForegroundColor Green
} else {
    Write-Host "[+] Node packages are satisfied." -ForegroundColor Green
}

# 8. Start Backend in separate window
Write-Host "Launching FastAPI Backend..." -ForegroundColor Yellow
$backendProc = Start-Process cmd -ArgumentList "/c title JARVIS Backend && python run_backend.py" -WorkingDirectory "$root\backend" -PassThru -WindowStyle Normal

# 9. Poll Backend health (max 20 seconds)
Write-Host "Waiting for backend to become ready..." -ForegroundColor Yellow
$backendReady = $false
$maxRetries = 20
for ($i = 1; $i -le $maxRetries; $i++) {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 1 -ErrorAction Stop
        if ($response.ok -eq $true -or $response.status -eq "ok" -or $response.data.status -eq "ok") {
            $backendReady = $true
            Write-Host "Backend is ready after $i seconds!" -ForegroundColor Green
            break
        }
    }
    catch {
        # ignore and sleep
    }
    Write-Host "Polling backend health ($i/$maxRetries)..." -ForegroundColor Gray
    Start-Sleep -Seconds 1
}

if (-not $backendReady) {
    Write-Host "==================================================" -ForegroundColor Red
    Write-Host "ERROR: Backend failed to respond within 20 seconds!" -ForegroundColor Red
    Write-Host "==================================================" -ForegroundColor Red
    if ($backendProc) { Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue }
    & "$PSScriptRoot\kill_jarvis_processes.ps1"
    exit 1
}

# 10. Start Frontend Dev Server (Vite) in separate window
Write-Host "Launching Vite Frontend Dev Server..." -ForegroundColor Yellow
$frontendProc = Start-Process cmd -ArgumentList "/c title JARVIS Frontend Dev && npm.cmd run dev" -WorkingDirectory "$root\frontend" -PassThru -WindowStyle Normal

# 11. Poll Frontend health (max 20 seconds)
Write-Host "Waiting for frontend dev server to become ready..." -ForegroundColor Yellow
$frontendReady = $false
for ($i = 1; $i -le $maxRetries; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $frontendReady = $true
            Write-Host "Frontend dev server is ready after $i seconds!" -ForegroundColor Green
            break
        }
    }
    catch {
        # ignore and sleep
    }
    Write-Host "Polling frontend health ($i/$maxRetries)..." -ForegroundColor Gray
    Start-Sleep -Seconds 1
}

if (-not $frontendReady) {
    Write-Host "==================================================" -ForegroundColor Red
    Write-Host "ERROR: Frontend dev server failed to respond within 20 seconds!" -ForegroundColor Red
    Write-Host "==================================================" -ForegroundColor Red
    if ($backendProc) { Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue }
    if ($frontendProc) { Stop-Process -Id $frontendProc.Id -Force -ErrorAction SilentlyContinue }
    & "$PSScriptRoot\kill_jarvis_processes.ps1"
    exit 1
}

# Show running configuration
Write-Host ""
Write-Host "--------------------------------------------------" -ForegroundColor Cyan
Write-Host "   JARVIS SERVERS ACTIVE" -ForegroundColor Green
Write-Host "   Backend:  http://127.0.0.1:8000" -ForegroundColor Yellow
Write-Host "   Frontend: http://127.0.0.1:5173" -ForegroundColor Yellow
Write-Host "--------------------------------------------------" -ForegroundColor Cyan
Write-Host ""

# 12. Launch Electron dev mode in the foreground (blocking)
try {
    Write-Host "Launching Electron Dev Client..." -ForegroundColor Green
    $oldDir = Get-Location
    Set-Location "$root\frontend"
    npm.cmd run electron
    Set-Location $oldDir
}
catch {
    Write-Host "An error occurred while running Electron: $_" -ForegroundColor Red
}
finally {
    # 13. Clean up backend/frontend when Electron is closed
    Write-Host "Electron closed. Terminating background servers..." -ForegroundColor Yellow
    
    if ($backendProc) {
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontendProc) {
        Stop-Process -Id $frontendProc.Id -Force -ErrorAction SilentlyContinue
    }
    
    & "$PSScriptRoot\kill_jarvis_processes.ps1"
    Write-Host "Clean shutdown completed successfully." -ForegroundColor Green
}

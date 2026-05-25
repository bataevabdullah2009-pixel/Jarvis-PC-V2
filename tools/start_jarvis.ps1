$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Stop-ProcessTree {
    param([System.Diagnostics.Process]$Process)
    if ($null -eq $Process) {
        return
    }
    if ($Process.HasExited) {
        return
    }
    try {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
    catch {
        Write-Host "Could not stop process $($Process.Id): $_" -ForegroundColor Yellow
    }
}

function Get-ListeningPids {
    param([int]$Port)
    $pids = @()

    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        foreach ($connection in $connections) {
            if ($connection.OwningProcess -gt 0) {
                $pids += [int]$connection.OwningProcess
            }
        }
    }
    catch {
        Write-Host "Get-NetTCPConnection unavailable, falling back to netstat." -ForegroundColor Yellow
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

function Clear-BackendPort {
    param([int]$Port)
    Write-Step "Checking port $Port"
    $listeningPids = @(Get-ListeningPids -Port $Port)

    if ($listeningPids.Count -eq 0) {
        Write-Host "Port $Port is free. TIME_WAIT/PID 0 rows are ignored." -ForegroundColor Green
        return
    }

    foreach ($pidValue in $listeningPids) {
        $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            continue
        }

        $name = $process.ProcessName
        $jarvisProcess = $name -match "^(python|pythonw|node|electron|JarvisBackend|JARVIS-PC-V2|JARVIS PC V2)$"
        if (-not $jarvisProcess) {
            throw "Port $Port is held by non-JARVIS process '$name' (PID $pidValue). Close it manually and run START_JARVIS.bat again."
        }

        Write-Host "Stopping stale JARVIS LISTENING process '$name' PID $pidValue on port $Port." -ForegroundColor Yellow
        Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
    }

    Start-Sleep -Seconds 2
    $remaining = @(Get-ListeningPids -Port $Port)
    if ($remaining.Count -gt 0) {
        throw "Port $Port is still occupied by LISTENING PID(s): $($remaining -join ', ')."
    }

    Write-Host "Port $Port is free." -ForegroundColor Green
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSeconds,
        [string]$Name
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Host "$Name is ready: $Url" -ForegroundColor Green
                return $true
            }
        }
        catch {
            Start-Sleep -Milliseconds 700
        }
    }

    return $false
}

function Ensure-BackendEnv {
    param([string]$Root)
    $backendEnv = Join-Path $Root "backend\.env"
    $rootEnv = Join-Path $Root ".env"

    if (Test-Path $backendEnv) {
        Write-Host "backend\.env found." -ForegroundColor Green
        return
    }

    if (Test-Path $rootEnv) {
        Copy-Item -LiteralPath $rootEnv -Destination $backendEnv -Force
        Write-Host "backend\.env was created from root .env." -ForegroundColor Yellow
        return
    }

    throw "backend\.env is missing. Create it from .env.example and add Groq/OpenRouter/Fish Audio keys."
}

function Ensure-BackendDependencies {
    param([string]$Root)
    Push-Location (Join-Path $Root "backend")
    try {
        python -c "import fastapi, uvicorn, pydantic, dotenv, httpx, requests, anyio" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Backend Python dependencies are available." -ForegroundColor Green
            return
        }
        Write-Host "Installing backend dependencies..." -ForegroundColor Yellow
        python -m pip install -r requirements.txt
    }
    finally {
        Pop-Location
    }
}

function Ensure-FrontendDependencies {
    param([string]$Root)
    $frontendDir = Join-Path $Root "frontend"
    $nodeModules = Join-Path $frontendDir "node_modules"

    if (Test-Path $nodeModules) {
        Write-Host "Frontend node_modules found." -ForegroundColor Green
        return
    }

    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    Push-Location $frontendDir
    try {
        npm.cmd install
    }
    finally {
        Pop-Location
    }
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ($env:JARVIS_BACKEND_PORT) {
    $backendPort = [int]$env:JARVIS_BACKEND_PORT
}
else {
    $backendPort = 18000
}
$frontendPort = 5173
$backendProc = $null
$frontendProc = $null

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " JARVIS PC V2 - START_JARVIS runtime lock" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Project root: $root" -ForegroundColor Gray

$env:JARVIS_PROJECT_ROOT = $root
$env:JARVIS_BACKEND_HOST = "127.0.0.1"
$env:JARVIS_BACKEND_PORT = [string]$backendPort
$env:JARVIS_FRONTEND_URL = "http://127.0.0.1:$frontendPort"
$env:JARVIS_FRONTEND_MODE = "dev"
$env:JARVIS_LAUNCHER = "START_JARVIS"
$env:JARVIS_AI_PRIMARY = if ($env:JARVIS_AI_PRIMARY) { $env:JARVIS_AI_PRIMARY } else { "groq" }
$env:JARVIS_AI_FALLBACK = if ($env:JARVIS_AI_FALLBACK) { $env:JARVIS_AI_FALLBACK } else { "openrouter" }
$env:JARVIS_AI_ALLOW_LOCAL_FALLBACK = if ($env:JARVIS_AI_ALLOW_LOCAL_FALLBACK) { $env:JARVIS_AI_ALLOW_LOCAL_FALLBACK } else { "true" }
$env:JARVIS_LISTENER_ENABLED = "true"
$env:JARVIS_LISTENER_AUTOSTART = "true"
$env:JARVIS_WAKE_WORDS = "джарвис,чарли,jarvis"
$env:JARVIS_COMMAND_RECORD_SECONDS = "6"
$env:JARVIS_COOLDOWN_MS = "2500"
$env:JARVIS_IGNORE_SELF_AUDIO = "true"
$env:JARVIS_CLAP_THRESHOLD = "0.25"
$env:JARVIS_MIN_RMS_THRESHOLD = "0.003"
$env:VITE_JARVIS_API_BASE = "http://127.0.0.1:$backendPort"

try {
    Write-Step "Stopping old JARVIS processes"
    & "$PSScriptRoot\kill_jarvis_processes.ps1"

    Clear-BackendPort -Port $backendPort

    Write-Step "Checking backend environment"
    Ensure-BackendEnv -Root $root

    Write-Step "Checking backend dependencies"
    Ensure-BackendDependencies -Root $root

    Write-Step "Checking frontend dependencies"
    Ensure-FrontendDependencies -Root $root

    Write-Step "Starting backend"
    $backendProc = Start-Process -FilePath "python" -ArgumentList "run_backend.py" -WorkingDirectory (Join-Path $root "backend") -PassThru -WindowStyle Hidden

    if (-not (Wait-HttpOk -Url "http://127.0.0.1:$backendPort/health" -TimeoutSeconds 35 -Name "Backend")) {
        throw "Backend did not become healthy on http://127.0.0.1:$backendPort/health."
    }

    Write-Step "Starting frontend dev server"
    $frontendProc = Start-Process -FilePath "npm.cmd" -ArgumentList "run dev" -WorkingDirectory (Join-Path $root "frontend") -PassThru -WindowStyle Hidden

    if (-not (Wait-HttpOk -Url "http://127.0.0.1:$frontendPort" -TimeoutSeconds 35 -Name "Frontend")) {
        throw "Frontend did not become ready on http://127.0.0.1:$frontendPort."
    }

    Write-Host ""
    Write-Host "Backend:  http://127.0.0.1:$backendPort" -ForegroundColor Green
    Write-Host "Frontend: http://127.0.0.1:$frontendPort" -ForegroundColor Green
    Write-Host "Launching Electron. Close Electron to stop backend/frontend." -ForegroundColor Green

    Push-Location (Join-Path $root "frontend")
    try {
        npm.cmd run electron
    }
    finally {
        Pop-Location
    }
}
finally {
    Write-Step "Stopping runtime processes"
    Stop-ProcessTree -Process $frontendProc
    Stop-ProcessTree -Process $backendProc
    & "$PSScriptRoot\kill_jarvis_processes.ps1"
    Write-Host "JARVIS runtime stopped." -ForegroundColor Green
}

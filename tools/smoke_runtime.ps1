param(
    [switch]$StrictEnv
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path
$BackendDir = Join-Path $ProjectRoot "backend"
$Port = 8001
$BaseUrl = "http://127.0.0.1:$Port"
$BackendProcess = $null
$Warnings = New-Object System.Collections.Generic.List[string]

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Invoke-Json {
    param(
        [string]$Path,
        [string]$Method = "GET",
        [object]$Body = $null
    )

    $uri = "$BaseUrl$Path"
    if ($Body -ne $null) {
        $json = $Body | ConvertTo-Json -Depth 8
        return Invoke-RestMethod -Uri $uri -Method $Method -Body $json -ContentType "application/json" -TimeoutSec 35
    }
    return Invoke-RestMethod -Uri $uri -Method $Method -TimeoutSec 35
}

function Stop-Backend {
    if ($BackendProcess -and -not $BackendProcess.HasExited) {
        Stop-Process -Id $BackendProcess.Id -Force -ErrorAction SilentlyContinue
    }
}

try {
    Write-Step "Checking source format"
    & python "$ProjectRoot\tools\check_source_format.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Source format check failed."
    }

    Write-Step "Cleaning old JARVIS processes"
    & "$ProjectRoot\tools\kill_jarvis_processes.ps1"
    Start-Sleep -Seconds 2

    Write-Step "Starting backend on port $Port"
    $env:JARVIS_PROJECT_ROOT = $ProjectRoot
    $env:JARVIS_BACKEND_PORT = [string]$Port
    $env:JARVIS_LISTENER_ENABLED = "false"
    $BackendProcess = Start-Process -FilePath "python" -ArgumentList "run_backend.py" -WorkingDirectory $BackendDir -PassThru -WindowStyle Hidden

    $ready = $false
    for ($i = 1; $i -le 25; $i++) {
        try {
            $health = Invoke-Json -Path "/health"
            if ($health.ok -eq $true) {
                $ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    if (-not $ready) {
        throw "Backend crash or startup failure: /health did not respond."
    }

    Write-Step "Checking required debug endpoints"
    $health = Invoke-Json -Path "/health"
    $startup = Invoke-Json -Path "/debug/startup"
    $envStatus = Invoke-Json -Path "/debug/env-status"
    $network = Invoke-Json -Path "/debug/network-status"
    $voiceProvider = Invoke-Json -Path "/debug/voice-provider-status"
    $ttsStatus = Invoke-Json -Path "/voice/tts-status"
    $listenerStatus = Invoke-Json -Path "/voice/listener-status"

    if ($health.ok -ne $true) {
        throw "/health returned ok=false."
    }
    if ($startup.backend_started -ne $true) {
        throw "/debug/startup did not report backend_started=true."
    }
    if ($listenerStatus.data.running -ne $false) {
        throw "Listener should be disabled/stopped by default."
    }

    if ($envStatus.openrouter.key_present -ne $true) {
        $Warnings.Add("OpenRouter key missing in loaded env.")
    }
    if ($envStatus.fish_audio.key_present -ne $true -or $envStatus.fish_audio.voice_id_present -ne $true) {
        $Warnings.Add("Fish Audio key or voice id missing in loaded env.")
    }
    if ($voiceProvider.selected_provider -eq "text_only") {
        $Warnings.Add("Fish Audio voice unavailable; text_only selected.")
    }
    if ($network.ok -ne $true) {
        $networkError = $network.openrouter.error_type
        if ($networkError -in @("tls_handshake_timeout", "network_timeout", "ssl_error")) {
            $Warnings.Add("OpenRouter network warning: $networkError")
        }
        else {
            $Warnings.Add("OpenRouter network check failed: $networkError")
        }
    }
    if ($StrictEnv -and $Warnings.Count -gt 0) {
        throw "Strict env mode failed: $($Warnings -join '; ')"
    }

    Write-Step "Checking assistant ask"
    $askBytes = @(208, 148, 208, 182, 208, 176, 209, 128, 208, 178, 208, 184, 209, 129, 44, 32, 208, 186, 208, 176, 208, 186, 32, 208, 180, 208, 181, 208, 187, 208, 176, 63)
    $askText = [System.Text.Encoding]::UTF8.GetString($askBytes)
    $askBody = @{
        text = $askText
        speak = $false
        source = "smoke"
        context = @{}
    }
    $ask = Invoke-Json -Path "/assistant/ask" -Method "POST" -Body $askBody
    if ($ask.ok -ne $true) {
        throw "/assistant/ask returned ok=false."
    }

    if ($Warnings.Count -gt 0) {
        Write-Host ""
        Write-Host "Smoke warnings:" -ForegroundColor Yellow
        foreach ($warning in $Warnings) {
            Write-Host " - $warning" -ForegroundColor Yellow
        }
    }

    Write-Host ""
    Write-Host "[+] SMOKE RUNTIME PASSED" -ForegroundColor Green
    exit 0
}
catch {
    Write-Host ""
    Write-Host "[!] SMOKE RUNTIME FAILED: $_" -ForegroundColor Red
    exit 1
}
finally {
    Stop-Backend
}

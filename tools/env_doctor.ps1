$ErrorActionPreference = "Continue"

# Determine project root
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "         JARVIS PC V2 - ENV DOCTOR & DIAGNOSTICS" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan

$envPaths = [ordered]@{
    "backend\.env"     = Join-Path $root "backend\.env"
    "root .env"        = Join-Path $root ".env"
    "app_current\.env" = Join-Path $root "app_current\.env"
}

# 1. Check where .env is found
Write-Host "`n[1/3] Checking .env files locations..." -ForegroundColor Yellow
$foundAny = $false
foreach ($key in $envPaths.Keys) {
    $path = $envPaths[$key]
    if (Test-Path $path) {
        Write-Host "  [+] Found: $key ($path)" -ForegroundColor Green
        $foundAny = $true
    } else {
        Write-Host "  [-] NOT Found: $key" -ForegroundColor Gray
    }
}

if (!$foundAny) {
    Write-Host "`n[!] CRITICAL: No .env files found in any standard locations!" -ForegroundColor Red
}

# 2. Check variable names in found .env files
Write-Host "`n[2/3] Checking variable presence in found .env files (WITHOUT printing values)..." -ForegroundColor Yellow

$requiredVars = @(
    "JARVIS_OPENROUTER_API_KEY",
    "JARVIS_OPENROUTER_MODEL",
    "JARVIS_FISH_AUDIO_API_KEY",
    "JARVIS_FISH_AUDIO_VOICE_ID",
    "TTS_PRIMARY",
    "TTS_REQUIRE_FISH_AUDIO",
    "TTS_FALLBACK_ENABLED"
)

# Helper to check variables in a file
function Check-EnvFile($filePath, $label) {
    if (!(Test-Path $filePath)) { return }
    Write-Host "`nChecking variables in $label..." -ForegroundColor Cyan
    
    $content = Get-Content -Path $filePath
    $missingCount = 0
    
    foreach ($varName in $requiredVars) {
        $found = $false
        foreach ($line in $content) {
            # Trim and check if starts with varName followed by =
            $trimmed = $line.Trim()
            if ($trimmed -like "$varName=*") {
                $val = $trimmed.Substring($varName.Length + 1).Trim()
                if ($val -ne "") {
                    $found = $true
                    break
                }
            }
        }
        
        if ($found) {
            Write-Host "  [+] ${varName}: PRESENT" -ForegroundColor Green
        } else {
            Write-Host "  [-] ${varName}: MISSING or EMPTY" -ForegroundColor Red
            $missingCount++
        }
    }
    
    if ($missingCount -gt 0) {
        Write-Host "  [!] Warning: $missingCount variables are missing or empty in $label!" -ForegroundColor Red
    } else {
        Write-Host "  [+] All required variables are present in $label!" -ForegroundColor Green
    }
}

foreach ($key in $envPaths.Keys) {
    Check-EnvFile $envPaths[$key] $key
}

# 3. Offer copy command and suggestions
Write-Host "`n[3/3] Actions and Suggestions..." -ForegroundColor Yellow

$backendEnv = $envPaths["backend\.env"]
$appCurrentEnv = $envPaths["app_current\.env"]

if (Test-Path $backendEnv) {
    Write-Host "You can synchronize backend\.env to app_current\.env by running:" -ForegroundColor Cyan
    Write-Host "Copy-Item -Path `"$backendEnv`" -Destination `"$appCurrentEnv`" -Force`n" -ForegroundColor Green
} else {
    Write-Host "Please create backend\.env first with proper OpenRouter and Fish Audio keys." -ForegroundColor Red
}

Write-Host "==================================================" -ForegroundColor Cyan

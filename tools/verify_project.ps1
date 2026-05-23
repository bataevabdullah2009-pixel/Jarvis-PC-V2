$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

try {
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "  JARVIS PC V2 - FULL PROJECT VERIFICATION  " -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Cyan

    # 1. Run source format check
    Write-Host "1. Running source formatting check..." -ForegroundColor Yellow
    python "$root\tools\check_source_format.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Source format check failed with code $LASTEXITCODE"
    }
    Write-Host "Source formatting check passed!" -ForegroundColor Green

    # 2. Run backend pytest
    Write-Host "2. Running backend pytest..." -ForegroundColor Yellow
    Set-Location "$root\backend"
    python -m pytest
    if ($LASTEXITCODE -ne 0) {
        throw "Backend pytest suite failed with code $LASTEXITCODE"
    }
    Write-Host "Backend tests passed!" -ForegroundColor Green

    # 3. Run frontend build
    Write-Host "3. Running frontend installation & tsc build..." -ForegroundColor Yellow
    Set-Location "$root\frontend"
    npm.cmd install
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend npm install failed with code $LASTEXITCODE"
    }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend tsc/vite build failed with code $LASTEXITCODE"
    }
    Write-Host "Frontend build passed!" -ForegroundColor Green

    Write-Host "==========================================" -ForegroundColor Green
    Write-Host "  ALL CHECKS PASSED SUCCESSFULLY!  " -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Green
    Exit 0
}
catch {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Red
    Write-Host "       VERIFICATION FAILURE DETECTED      " -ForegroundColor Red
    Write-Host "==========================================" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    Write-Host ""
    Exit 1
}

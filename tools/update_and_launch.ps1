$ErrorActionPreference = "Stop"

# Determine project root
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

try {
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "   JARVIS PC V2 - PRODUCTION UPDATER & LAUNCHER" -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Cyan

    # 1. Close running processes
    Write-Host "Stopping any running JARVIS processes to free up files..." -ForegroundColor Yellow
    & "$PSScriptRoot\kill_jarvis_processes.ps1"

    # 2. Perform Git Pull
    Write-Host "Pulling latest changes from git repository..." -ForegroundColor Yellow
    git pull

    # 3. Check environment
    Write-Host "Verifying developer environments..." -ForegroundColor Yellow
    if (!(Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python is not installed or not in PATH! Cannot build backend."
    }
    if (!(Get-Command node -ErrorAction SilentlyContinue)) {
        throw "Node.js is not installed or not in PATH! Cannot build frontend."
    }

    # 4. Run Pytest backend tests
    Write-Host "Running backend test suite (pytest)..." -ForegroundColor Yellow
    Set-Location "$root\backend"
    python -m pytest
    Write-Host "Backend tests passed successfully!" -ForegroundColor Green

    # 5. Build Frontend (npm install & npm run build)
    Write-Host "Installing frontend dependencies & building Vite bundle..." -ForegroundColor Yellow
    Set-Location "$root\frontend"
    npm install
    npm run build

    # 6. Build Backend Exe
    Write-Host "Compiling Python Backend via PyInstaller..." -ForegroundColor Yellow
    Set-Location $root
    cmd /c "tools\build_backend_exe.bat"
    if ($LASTEXITCODE -ne 0) {
        throw "Backend EXE compilation failed with code $LASTEXITCODE"
    }

    # 7. Archive previous build directory if it exists
    $dateString = Get-Date -Format "yyyy-MM-dd_HH-mm"
    $archiveDir = Join-Path $root "_archive\old_builds\$dateString"

    if (Test-Path "$root\release") {
        Write-Host "Archiving old release directory to $archiveDir..." -ForegroundColor Yellow
        New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
        # We use Move-Item. If folders conflict or lock, we try to handle gracefully.
        Move-Item -Path "$root\release" -Destination $archiveDir -Force
    }

    # 8. Package Electron as folder structure
    Write-Host "Packaging Electron application into folder..." -ForegroundColor Yellow
    Set-Location "$root\frontend"
    # Using package:dir which does electron-builder --dir
    npm run package:dir

    # 9. Clean/Create app_current directory
    $appCurrent = Join-Path $root "app_current"
    if (Test-Path $appCurrent) {
        Write-Host "Clearing previous app_current directory..." -ForegroundColor Yellow
        # We force clear files inside
        Remove-Item -Path "$appCurrent\*" -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        New-Item -ItemType Directory -Force -Path $appCurrent | Out-Null
    }

    # 10. Copy fresh files to app_current
    Write-Host "Copying fresh release to $appCurrent..." -ForegroundColor Yellow
    if (!(Test-Path "$root\release\win-unpacked")) {
        throw "Release build win-unpacked folder was not found at $root\release\win-unpacked!"
    }
    Copy-Item -Path "$root\release\win-unpacked\*" -Destination $appCurrent -Recurse -Force

    # 11. Write VERSION.txt and BUILD_INFO.json
    Write-Host "Writing version and build metadata files..." -ForegroundColor Yellow
    $packageJson = Get-Content -Raw -Path "$root\frontend\package.json" | ConvertFrom-Json
    $packageVersion = $packageJson.version
    $gitCommit = (git rev-parse --short HEAD).Trim()
    $gitBranch = (git rev-parse --abbrev-ref HEAD).Trim()
    $buildDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    $versionText = "Built At: $buildDate`r`nGit Commit: $gitCommit`r`nPackage Version: $packageVersion"
    $versionText | Out-File -FilePath "$appCurrent\VERSION.txt" -Encoding utf8

    $buildInfo = @{
        built_at = $buildDate
        git_sha = $gitCommit
        git_branch = $gitBranch
        frontend_version = $packageVersion
        backend_ready = $true
    }
    $buildInfo | ConvertTo-Json | Out-File -FilePath "$appCurrent\BUILD_INFO.json" -Encoding utf8

    # 12. Run fresh app
    Write-Host "Launching fresh JARVIS PC V2 from app_current..." -ForegroundColor Green
    Set-Location $root
    $appPath = Join-Path $appCurrent "JARVIS PC V2.exe"
    Start-Process -FilePath $appPath -WorkingDirectory $appCurrent

    Write-Host "JARVIS PC V2 successfully stabilized and launched!" -ForegroundColor Green
    Start-Sleep -Seconds 3
}
catch {
    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Red
    Write-Host "   STABILIZATION / BUILD / UPDATE ERROR DETECTED" -ForegroundColor Red
    Write-Host "==================================================" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Please fix the error above and press Enter to exit..." -ForegroundColor Cyan
    Read-Host
    Exit 1
}

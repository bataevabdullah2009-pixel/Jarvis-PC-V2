$ErrorActionPreference = "SilentlyContinue"

# Dynamic project root
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   JARVIS PC V2 - DUPLICATE DETECTOR" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Scanning system for old/duplicate versions of JARVIS..." -ForegroundColor Yellow
Write-Host ""

$duplicates = [System.Collections.Generic.List[PSCustomObject]]::new()

# Helper to retrieve file version
function Get-FileVersion {
    param ($filePath)
    if (Test-Path $filePath) {
        $info = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($filePath)
        if ($info.ProductVersion) { return $info.ProductVersion }
        if ($info.FileVersion) { return $info.FileVersion }
    }
    return "unknown"
}

# Helper to get shortcut target
function Get-ShortcutTarget {
    param ($shortcutPath)
    try {
        $wshell = New-Object -ComObject Wscript.Shell
        $shortcut = $wshell.CreateShortcut($shortcutPath)
        return $shortcut.TargetPath
    }
    catch {
        return $null
    }
}

# 1. Search shortcuts (Desktop & Start Menu)
$searchPaths = @(
    [System.Environment]::GetFolderPath("Desktop"),
    "C:\Users\Public\Desktop",
    [System.Environment]::GetFolderPath("StartMenu"),
    [System.Environment]::GetFolderPath("CommonStartMenu")
)

foreach ($path in $searchPaths) {
    if ($path -and (Test-Path $path)) {
        Get-ChildItem -Path $path -Filter "*Jarvis*.lnk" -Recurse | ForEach-Object {
            $target = Get-ShortcutTarget $_.FullName
            $action = "Points to inactive folder. Recreate/Delete"
            if ($target -like "*app_current\JARVIS PC V2.exe") {
                $action = "Keep (Valid active shortcut)"
            }
            $duplicates.Add([PSCustomObject]@{
                Path = $_.FullName
                Type = "Shortcut (Target: $target)"
                Version = "N/A"
                RecommendedAction = $action
            })
        }
    }
}

# 2. Search executables & build folders in current root
if (Test-Path $root) {
    # Check app_current folder - this is our active app!
    $appCurrentPath = Join-Path $root "app_current"
    if (Test-Path $appCurrentPath) {
        $duplicates.Add([PSCustomObject]@{
            Path = $appCurrentPath
            Type = "Current Active App Folder"
            Version = "N/A"
            RecommendedAction = "Keep (Active Production App)"
        })
    }

    # Check _archive folder
    $archivePath = Join-Path $root "_archive"
    if (Test-Path $archivePath) {
        Get-ChildItem -Path $archivePath -Filter "*.exe" -Recurse | ForEach-Object {
            $duplicates.Add([PSCustomObject]@{
                Path = $_.FullName
                Type = "Archived Executable"
                Version = Get-FileVersion $_.FullName
                RecommendedAction = "Archive (Safe to delete to free space)"
            })
        }
        # Also find old unpacked directories in archive
        Get-ChildItem -Path $archivePath -Directory -Recurse | Where-Object { $_.Name -eq "win-unpacked" } | ForEach-Object {
            $duplicates.Add([PSCustomObject]@{
                Path = $_.FullName
                Type = "Archived Release Folder"
                Version = "N/A"
                RecommendedAction = "Archive (Safe to delete to free space)"
            })
        }
    }

    # Check release folder in current root (is it active or old?)
    $releaseUnpacked = Join-Path $root "release\win-unpacked"
    if (Test-Path $releaseUnpacked) {
        $duplicates.Add([PSCustomObject]@{
            Path = $releaseUnpacked
            Type = "Release Build Output Folder"
            Version = "N/A"
            RecommendedAction = "Keep (Used during packaging)"
        })
    }
}

# 3. Scan C:\ drive roots and common directories (excluding our current root!)
$driveRoots = @(
    "C:\",
    [System.Environment]::GetFolderPath("ProgramFiles"),
    [System.Environment]::GetFolderPath("ProgramFilesX86"),
    "$env:LOCALAPPDATA\Programs"
)

foreach ($dir in $driveRoots) {
    if (Test-Path $dir) {
        # Scan immediate subdirectories or files matching *Jarvis* or *JARVIS*
        Get-ChildItem -Path $dir -Depth 1 | Where-Object { 
            ($_.Name -match "Jarvis" -or $_.Name -match "JARVIS") -and 
            $_.FullName -ne $root -and 
            $_.FullName -ne (Join-Path $root "app_current") -and
            $_.FullName -ne (Join-Path $root "release") -and
            $_.FullName -ne (Join-Path $root "_archive")
        } | ForEach-Object {
            $itemPath = $_.FullName
            $type = if ($_.PsIsContainer) { "Directory" } else { "File" }
            $version = "N/A"
            if ($type -eq "File" -and $_.Extension -eq ".exe") {
                $version = Get-FileVersion $itemPath
            }
            
            $duplicates.Add([PSCustomObject]@{
                Path = $itemPath
                Type = "External Duplicate $type"
                Version = $version
                RecommendedAction = "Duplicate (Consider deleting to clean up)"
            })
        }
    }
}

# 4. Display Results
if ($duplicates.Count -eq 0) {
    Write-Host "Success: No duplicate installations or old versions were found!" -ForegroundColor Green
} else {
    Write-Host "Found $($duplicates.Count) JARVIS related item(s):" -ForegroundColor Yellow
    Write-Host "--------------------------------------------------------------------------------" -ForegroundColor Gray
    foreach ($dup in $duplicates) {
        Write-Host "• Path:   " -NoNewline -ForegroundColor White
        Write-Host $dup.Path -ForegroundColor Cyan
        Write-Host "  Type:   " -NoNewline -ForegroundColor White
        Write-Host $dup.Type -NoNewline -ForegroundColor DarkGray
        Write-Host " | Version: " -NoNewline -ForegroundColor White
        Write-Host $dup.Version -NoNewline -ForegroundColor Yellow
        Write-Host " | Action: " -NoNewline -ForegroundColor White
        Write-Host $dup.RecommendedAction -ForegroundColor Green
        Write-Host ""
    }
    Write-Host "--------------------------------------------------------------------------------" -ForegroundColor Gray
}

Write-Host "==================================================" -ForegroundColor Cyan

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$frontend = Join-Path $root "frontend"
$release = Join-Path $root "release"
$archiveRoot = Join-Path $root "_archive\old_builds"
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm"

Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue

Write-Host "JARVIS PC V2 clean build"
Write-Host "Root: $root"

& (Join-Path $PSScriptRoot "kill_jarvis_processes.ps1")

if (Test-Path $release) {
  New-Item -ItemType Directory -Force -Path $archiveRoot | Out-Null
  $archiveTarget = Join-Path $archiveRoot $timestamp
  Write-Host "Archiving old release to $archiveTarget"
  Move-Item -LiteralPath $release -Destination $archiveTarget
}

$pathsToRemove = @(
  (Join-Path $frontend "dist"),
  (Join-Path $frontend "backend_package"),
  (Join-Path $root "build"),
  (Join-Path $root "dist")
)

foreach ($target in $pathsToRemove) {
  if (Test-Path $target) {
    $resolved = (Resolve-Path $target).Path
    if ($resolved.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
      Write-Host "Removing build artifact $resolved"
      Remove-Item -LiteralPath $resolved -Recurse -Force
    } else {
      throw "Refusing to remove path outside project: $resolved"
    }
  }
}

Push-Location $frontend
try {
  if (-not (Test-Path "node_modules")) {
    Write-Host "Installing frontend dependencies..."
    npm.cmd install
  } else {
    Write-Host "Frontend dependencies already installed."
  }

  Write-Host "Building frontend..."
  npm.cmd run build

  Write-Host "Building backend package..."
  npm.cmd run prepare:backend

  Write-Host "Packaging unpacked app..."
  npm.cmd run package:dir

  Write-Host "Packaging portable app..."
  npm.cmd run package:portable
}
finally {
  Pop-Location
}

$unpackedExe = Join-Path $release "win-unpacked\JARVIS PC V2.exe"
$portableExe = Join-Path $release "JARVIS-PC-V2-0.1.0-x64.exe"

Write-Host ""
Write-Host "Build complete."
Write-Host "Unpacked exe: $unpackedExe"
Write-Host "Portable exe: $portableExe"

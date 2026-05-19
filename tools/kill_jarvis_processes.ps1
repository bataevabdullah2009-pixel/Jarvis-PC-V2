$ErrorActionPreference = "SilentlyContinue"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue

Write-Host "Stopping JARVIS PC V2 processes..."

Get-Process -Name "JarvisBackend" -ErrorAction SilentlyContinue | Stop-Process -Force

Get-Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.ProcessName -like "JARVIS-PC-V2*" -or
    $_.ProcessName -eq "JARVIS PC V2"
  } |
  Stop-Process -Force

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    ($_.Name -match "^(node|electron)\.exe$") -and
    ($_.CommandLine -like "*$root*" -or $_.CommandLine -like "*Jarvis PC V2*")
  } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }

Write-Host "Process cleanup complete."

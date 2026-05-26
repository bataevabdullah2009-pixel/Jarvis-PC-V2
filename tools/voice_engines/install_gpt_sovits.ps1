$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$externalDir = Join-Path $root "external"
$targetDir = Join-Path $externalDir "GPT-SoVITS"

New-Item -ItemType Directory -Force -Path $externalDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $root "docs") | Out-Null

Write-Host "GPT-SoVITS is a heavy optional engine and is not installed into the main Jarvis runtime."
Write-Host ""
Write-Host "Official repository:"
Write-Host "https://github.com/RVC-Boss/GPT-SoVITS"
Write-Host ""
Write-Host "Suggested clone command:"
Write-Host "git clone https://github.com/RVC-Boss/GPT-SoVITS.git `"$targetDir`""
Write-Host ""
Write-Host "After you clone and configure GPT-SoVITS yourself, start its local API server."
Write-Host "Then set these .env values:"
Write-Host "JARVIS_GPT_SOVITS_ENABLED=true"
Write-Host "JARVIS_GPT_SOVITS_API_URL=http://127.0.0.1:9880"
Write-Host "JARVIS_GPT_SOVITS_REFER_WAV=path\to\reference.wav"
Write-Host "JARVIS_GPT_SOVITS_PROMPT_TEXT=reference prompt text"
Write-Host ""
Write-Host "Jarvis will use it only after you choose gpt_sovits_local in the voice profile UI."

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$engineDir = Join-Path $root "tools\voice_engines"
$modelDir = Join-Path $root "models\piper"

New-Item -ItemType Directory -Force -Path $engineDir | Out-Null
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null

Write-Host "Installing optional Piper package into the current Python environment..."
python -m pip install piper-tts

Write-Host ""
Write-Host "Piper package install requested."
Write-Host "This script does not download voices automatically."
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Download a Piper voice .onnx file and matching .onnx.json config."
Write-Host "2. Put them into: $modelDir"
Write-Host "3. Configure .env:"
Write-Host "   JARVIS_PIPER_ENABLED=true"
Write-Host "   JARVIS_PIPER_MODEL_PATH=models/piper/ru_RU.onnx"
Write-Host "   JARVIS_PIPER_CONFIG_PATH=models/piper/ru_RU.onnx.json"
Write-Host "   JARVIS_PIPER_EXE_PATH=path\to\piper.exe"
Write-Host ""
Write-Host "Jarvis will keep using Fish Audio unless you choose piper_local in the voice profile UI."

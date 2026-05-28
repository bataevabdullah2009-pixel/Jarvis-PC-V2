$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$engineDir = Join-Path $root "tools\voice_engines"
$modelDir = Join-Path $root "models\piper"
$modelName = "ru_RU-ruslan-medium"
$modelPath = Join-Path $modelDir "$modelName.onnx"
$configPath = Join-Path $modelDir "$modelName.onnx.json"
$modelUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/ruslan/medium/$modelName.onnx"
$configUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/ru/ru_RU/ruslan/medium/$modelName.onnx.json"

New-Item -ItemType Directory -Force -Path $engineDir | Out-Null
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null

Write-Host "Installing optional Piper package into the current Python environment..."
python -m pip install piper-tts

Write-Host ""
Write-Host "Downloading Russian Piper voice: $modelName"
if (-not (Test-Path $modelPath)) {
    Invoke-WebRequest -Uri $modelUrl -OutFile $modelPath
} else {
    Write-Host "Model already exists: $modelPath"
}

if (-not (Test-Path $configPath)) {
    Invoke-WebRequest -Uri $configUrl -OutFile $configPath
} else {
    Write-Host "Config already exists: $configPath"
}

$piperExe = (Get-Command piper -ErrorAction SilentlyContinue).Source

Write-Host ""
Write-Host "Piper package and Russian voice are ready."
Write-Host ""
Write-Host "Recommended .env values:"
Write-Host "   JARVIS_PIPER_ENABLED=true"
Write-Host "   JARVIS_PIPER_MODEL_PATH=models/piper/$modelName.onnx"
Write-Host "   JARVIS_PIPER_CONFIG_PATH=models/piper/$modelName.onnx.json"
if ($piperExe) {
    Write-Host "   JARVIS_PIPER_EXE_PATH=$piperExe"
} else {
    Write-Host "   JARVIS_PIPER_EXE_PATH=path\to\piper.exe"
}
Write-Host ""
Write-Host "Jarvis will keep using Fish Audio unless you choose piper_local in the voice profile UI."

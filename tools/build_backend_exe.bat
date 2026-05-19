@echo off
setlocal

cd /d "%~dp0.."
set "ROOT=%cd%"

python -m pip install pyinstaller
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --name JarvisBackend ^
  --paths "%ROOT%\backend" ^
  --hidden-import app.main ^
  --hidden-import uvicorn ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols ^
  --hidden-import uvicorn.protocols.http ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --exclude-module IPython ^
  --exclude-module jupyter ^
  --exclude-module matplotlib ^
  --exclude-module onnxruntime ^
  --exclude-module pandas ^
  --exclude-module pyarrow ^
  --exclude-module pytest ^
  --exclude-module scipy ^
  --exclude-module sklearn ^
  --exclude-module sympy ^
  --exclude-module tensorboard ^
  --exclude-module tensorflow ^
  --exclude-module torch ^
  --exclude-module torchaudio ^
  --exclude-module torchvision ^
  "%ROOT%\backend\run_backend.py"

if not exist "%ROOT%\dist\JarvisBackend.exe" (
  echo ERROR: PyInstaller did not create "%ROOT%\dist\JarvisBackend.exe".
  exit /b 1
)

python "%ROOT%\tools\prepare_backend_package.py"
if errorlevel 1 exit /b 1

copy /Y "%ROOT%\dist\JarvisBackend.exe" "%ROOT%\frontend\backend_package\JarvisBackend.exe"
if errorlevel 1 (
  echo ERROR: Failed to copy JarvisBackend.exe into frontend\backend_package.
  exit /b 1
)

if not exist "%ROOT%\frontend\backend_package\run_backend.py" (
  echo ERROR: backend_package is incomplete: run_backend.py is missing.
  exit /b 1
)

echo Backend executable prepared in frontend\backend_package.

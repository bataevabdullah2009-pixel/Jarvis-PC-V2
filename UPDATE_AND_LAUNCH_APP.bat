@echo off
cd /d "%~dp0"
echo WARNING: For normal use start START_JARVIS.bat
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\update_and_launch.ps1"
pause

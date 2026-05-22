@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "tools\update_and_launch.ps1"
pause

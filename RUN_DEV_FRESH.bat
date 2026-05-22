@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "tools\dev_run_fresh.ps1" -Pull
pause

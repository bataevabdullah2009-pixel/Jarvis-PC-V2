@echo off
setlocal

cd /d "%~dp0.."
set "ROOT=%cd%"

start "JARVIS PC V2 Backend" /D "%ROOT%\backend" cmd /k python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

cd /d "%ROOT%\frontend"
npm.cmd run dev

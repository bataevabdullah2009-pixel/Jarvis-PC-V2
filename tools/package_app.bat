@echo off
setlocal

cd /d "%~dp0.."
set "ROOT=%cd%"

cd /d "%ROOT%\frontend"
npm.cmd install
npm.cmd run package:installer
if errorlevel 1 exit /b 1

if exist "%ROOT%\release\win-unpacked" rmdir /S /Q "%ROOT%\release\win-unpacked"
if exist "%ROOT%\release\logs" rmdir /S /Q "%ROOT%\release\logs"
if exist "%ROOT%\release\*.blockmap" del /Q "%ROOT%\release\*.blockmap"
if exist "%ROOT%\release\builder-effective-config.yaml" del /Q "%ROOT%\release\builder-effective-config.yaml"

echo Installer package is in the release folder.

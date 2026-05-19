@echo off
setlocal

cd /d "%~dp0.."
set "ROOT=%cd%"

cd /d "%ROOT%\frontend"
npm.cmd install
npm.cmd run package:installer

echo Installer is in the release folder.

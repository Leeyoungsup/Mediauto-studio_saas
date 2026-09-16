@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0select.ps1"
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%

@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0native\bootstrap.ps1" -Gui
exit /b %ERRORLEVEL%

@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-local.ps1" -Launcher local_launch.py

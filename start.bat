@echo off
REM ============================================================
REM  MeDICus Studio SaaS - Server Start Script
REM  - conda env "yslee" activate
REM  - uvicorn FastAPI start
REM ============================================================
setlocal
cd /d "%~dp0backend"

set ENV_NAME=yslee
set HOST=0.0.0.0
set PORT=27070

where conda >nul 2>&1
if errorlevel 1 (
    echo [ERROR] conda not found. Install Miniconda/Anaconda first.
    pause
    exit /b 1
)

call conda env list | findstr /b /c:"%ENV_NAME% " >nul
if errorlevel 1 (
    echo [ERROR] conda env "%ENV_NAME%" not found.
    echo         Run install.bat first.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  MeDICus Studio SaaS
echo  URL: http://localhost:%PORT%
echo  Press Ctrl+C to stop.
echo ============================================================
echo.

call conda run --no-capture-output -n %ENV_NAME% python -m uvicorn main:app --host %HOST% --port %PORT%

endlocal

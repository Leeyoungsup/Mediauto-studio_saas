@echo off
REM ============================================================
REM  MeDICus Studio SaaS - Server Start Script
REM  - conda env "medicus-saas" activate
REM  - uvicorn FastAPI start
REM ============================================================
setlocal

cd /d "%~dp0backend"

set ENV_NAME=medicus-saas
if defined MEDIAUTO_CONDA_ENV set ENV_NAME=%MEDIAUTO_CONDA_ENV%
set HOST=0.0.0.0
if defined MEDIAUTO_HOST set HOST=%MEDIAUTO_HOST%
set PORT=8092
if defined MEDIAUTO_PORT set PORT=%MEDIAUTO_PORT%

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

REM --- Resolve conda env python path ---
for /f "tokens=*" %%i in ('conda run -n %ENV_NAME% python -c "import sys; print(sys.executable)"') do set ENV_PYTHON=%%i

if not exist "%ENV_PYTHON%" (
    echo [ERROR] python not found in conda env: %ENV_PYTHON%
    pause
    exit /b 1
)

REM --- Avoid pollution from any active .venv / user site-packages ---
set VIRTUAL_ENV=
set PYTHONHOME=
set PYTHONPATH=
set PYTHONNOUSERSITE=1

REM --- Background worker CPU policy. Existing environment values win. ---
if "%MEDIAUTO_CPU_TILE%"=="" set MEDIAUTO_CPU_TILE=6
if "%MEDIAUTO_TILE_WORKER_IDLE_PARALLELISM%"=="" set MEDIAUTO_TILE_WORKER_IDLE_PARALLELISM=2
if "%MEDIAUTO_TILE_WORKER_BUSY_PARALLELISM%"=="" set MEDIAUTO_TILE_WORKER_BUSY_PARALLELISM=1
if "%TILE_CACHE_QUOTA_BYTES%"=="" set TILE_CACHE_QUOTA_BYTES=1099511627776

echo.
echo ============================================================
echo  MeDICus Studio SaaS
echo  URL: http://localhost:%PORT%
echo  Press Ctrl+C to stop.
echo ============================================================
echo.

"%ENV_PYTHON%" -m uvicorn main:app --host %HOST% --port %PORT%

endlocal

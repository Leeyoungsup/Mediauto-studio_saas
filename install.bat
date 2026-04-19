@echo off
REM ============================================================
REM  MeDIAuto Studio SaaS - Dependency Install Script
REM  - Create/update conda env
REM  - Check MongoDB
REM  - Install PyTorch with CUDA
REM  - Install backend/requirements.txt
REM ============================================================
setlocal
cd /d "%~dp0"

set ENV_NAME=yslee
set PY_VER=3.12
set CUDA_TAG=cu121

where conda >nul 2>&1
if errorlevel 1 (
    echo [ERROR] conda not found. Install Miniconda/Anaconda first:
    echo         https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)

echo.
echo [STEP 1/4] Checking MongoDB ...
where mongod >nul 2>&1
if errorlevel 1 (
    echo [WARN] mongod not found in PATH.
    echo        MeDIAuto SaaS requires MongoDB ^(local or remote^).
    echo        Install: https://www.mongodb.com/try/download/community
    echo        Or configure MONGODB_URI in backend environment.
    echo.
    choice /C YN /M "Continue anyway"
    if errorlevel 2 exit /b 1
) else (
    echo [INFO] mongod found.
)

echo.
echo [STEP 2/4] Checking conda environment "%ENV_NAME%" ...
call conda env list | findstr /b /c:"%ENV_NAME% " >nul
if errorlevel 1 (
    echo [INFO] Creating new env: %ENV_NAME% ^(python %PY_VER%^)
    call conda create -y -n %ENV_NAME% python=%PY_VER%
    if errorlevel 1 (
        echo [ERROR] Failed to create conda env.
        pause
        exit /b 1
    )
) else (
    echo [INFO] Env "%ENV_NAME%" already exists.
)

echo.
echo [STEP 3/4] Installing PyTorch ^(CUDA %CUDA_TAG%^) ...
call conda run -n %ENV_NAME% pip install --upgrade pip
call conda run -n %ENV_NAME% pip install torch torchvision --index-url https://download.pytorch.org/whl/%CUDA_TAG%
if errorlevel 1 (
    echo [WARN] CUDA build failed. Falling back to CPU-only PyTorch ...
    call conda run -n %ENV_NAME% pip install torch torchvision
)

echo.
echo [STEP 4/4] Installing backend requirements ...
call conda run -n %ENV_NAME% pip install -r "%~dp0backend\requirements.txt"
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [DONE] Install complete.
echo.
echo  Run start.bat to launch the SaaS server.
echo.
echo  NOTE ^(OpenSlide on Windows^):
echo    openslide-python requires OpenSlide binary DLLs.
echo    Download: https://openslide.org/download/
echo    Place DLLs under a folder on PATH, or use official
echo    openslide-bin wheel if needed.
echo.
echo  NOTE ^(Migration^):
echo    When moving this install to another machine, copy:
echo      - backend/.secrets.json  ^(password pepper, AES key - CRITICAL^)
echo      - backend/uploads/        ^(WSI files, tile cache^)
echo      - backend/model/          ^(AI weights^)
echo      - MongoDB dump            ^(mongodump / mongorestore^)
echo    Losing .secrets.json breaks all existing user passwords.
echo ============================================================
pause
endlocal

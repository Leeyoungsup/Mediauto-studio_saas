@echo off
REM ============================================================
REM  MeDIAuto Studio SaaS - Dependency Install Script (Windows)
REM  - Install/configure PostgreSQL
REM  - Create/update conda env
REM  - Install PyTorch with CUDA
REM  - Install backend/requirements.txt
REM  - Apply PostgreSQL schema
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set ENV_NAME=medicus-saas
if defined MEDIAUTO_CONDA_ENV set ENV_NAME=%MEDIAUTO_CONDA_ENV%
set PY_VER=3.12
if defined MEDIAUTO_PYTHON_VERSION set PY_VER=%MEDIAUTO_PYTHON_VERSION%
set CUDA_TAG=cu121
if defined MEDIAUTO_CUDA_TAG set CUDA_TAG=%MEDIAUTO_CUDA_TAG%
set PHILIPS_ENV_NAME=philips-sdk-py37
if defined PHILIPS_CONDA_ENV set PHILIPS_ENV_NAME=%PHILIPS_CONDA_ENV%
set PHILIPS_PY_VER=3.7

where conda >nul 2>&1
if errorlevel 1 (
    echo [ERROR] conda not found. Install Miniconda/Anaconda first:
    echo         https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [STEP 1/7] Conda environment "%ENV_NAME%"
echo ============================================================
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
echo ============================================================
echo [STEP 2/7] PyTorch ^(CUDA %CUDA_TAG%^)
echo ============================================================
call conda run -n %ENV_NAME% pip install --upgrade pip
call conda run -n %ENV_NAME% pip install torch torchvision --index-url https://download.pytorch.org/whl/%CUDA_TAG%
if errorlevel 1 (
    echo [WARN] CUDA build failed. Falling back to CPU-only PyTorch ...
    call conda run -n %ENV_NAME% pip install torch torchvision
)

echo.
echo ============================================================
echo [STEP 3/7] Backend requirements
echo ============================================================
call conda run -n %ENV_NAME% pip install -r "%~dp0backend\requirements.txt"
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)
REM Reused environments may still contain the retired database drivers.
call conda run -n %ENV_NAME% python -m pip uninstall -y motor pymongo >nul 2>&1

echo.
echo ============================================================
echo [STEP 4/7] PostgreSQL environment and service
echo ============================================================
set "POSTGRES_ENV_FILE=%~dp0.env.postgres"
if defined MEDIAUTO_POSTGRES_ENV_FILE set "POSTGRES_ENV_FILE=%MEDIAUTO_POSTGRES_ENV_FILE%"
set POSTGRES_MODE=docker
if exist "!POSTGRES_ENV_FILE!" for /f "usebackq eol=# tokens=1,* delims==" %%A in ("!POSTGRES_ENV_FILE!") do if /I "%%A"=="POSTGRES_DEPLOYMENT" set POSTGRES_MODE=%%B
if defined MEDIAUTO_POSTGRES_MODE set POSTGRES_MODE=%MEDIAUTO_POSTGRES_MODE%
if defined POSTGRES_URI if not exist "!POSTGRES_ENV_FILE!" set POSTGRES_MODE=external
if "%MEDIAUTO_POSTGRES_EXTERNAL%"=="1" set POSTGRES_MODE=external
call conda run -n %ENV_NAME% python "%~dp0backend\scripts\configure_postgres_env.py" --env-file "!POSTGRES_ENV_FILE!" --mode !POSTGRES_MODE!
if errorlevel 1 (
    echo [ERROR] PostgreSQL environment setup failed.
    pause
    exit /b 1
)
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("!POSTGRES_ENV_FILE!") do set "%%A=%%B"

if /I "!POSTGRES_DEPLOYMENT!"=="native" (
    echo [ERROR] Native managed PostgreSQL is currently supported by install.sh on Linux.
    echo         On Windows use Docker, or install PostgreSQL separately and select external mode.
    pause
    exit /b 1
)
if /I "!POSTGRES_DEPLOYMENT!"=="external" goto POSTGRES_EXTERNAL_READY
where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Desktop with Compose is required for the default PostgreSQL deployment.
    echo         Install Docker Desktop, or set POSTGRES_URI and MEDIAUTO_POSTGRES_EXTERNAL=1.
    pause
    exit /b 1
)
docker compose version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Compose plugin is not available.
    pause
    exit /b 1
)
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Desktop is not running or is not accessible.
    pause
    exit /b 1
)
docker compose --env-file "!POSTGRES_ENV_FILE!" -f "%~dp0compose.postgres.yml" up -d
if errorlevel 1 (
    echo [ERROR] PostgreSQL container startup failed.
    pause
    exit /b 1
)
for /f "usebackq delims=" %%I in (`docker compose --env-file "!POSTGRES_ENV_FILE!" -f "%~dp0compose.postgres.yml" ps -q postgres`) do set POSTGRES_CONTAINER_ID=%%I
set POSTGRES_HEALTH=
for /L %%I in (1,1,60) do (
    for /f "usebackq delims=" %%H in (`docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" !POSTGRES_CONTAINER_ID! 2^>nul`) do set POSTGRES_HEALTH=%%H
    if /I "!POSTGRES_HEALTH!"=="healthy" goto POSTGRES_DOCKER_READY
    timeout /t 1 /nobreak >nul
)
echo [ERROR] PostgreSQL container did not become healthy. Status: !POSTGRES_HEALTH!
pause
exit /b 1

:POSTGRES_DOCKER_READY
echo [OK]   Persistent PostgreSQL container is healthy on 127.0.0.1:!POSTGRES_PORT!.
goto POSTGRES_SETUP_DONE

:POSTGRES_EXTERNAL_READY
echo [INFO] External PostgreSQL deployment selected; Docker startup skipped.

:POSTGRES_SETUP_DONE
echo.
echo ============================================================
echo [STEP 5/7] Optional Philips iSyntax environment
echo ============================================================
set PHILIPS_REQUESTED=0
if "%MEDIAUTO_ENABLE_PHILIPS%"=="1" set PHILIPS_REQUESTED=1
if defined MEDIAUTO_PHILIPS_SDK_SOURCE set PHILIPS_REQUESTED=1
if "!PHILIPS_REQUESTED!"=="1" (
    if not "%MEDIAUTO_ACCEPT_PHILIPS_EULA%"=="1" (
        echo [ERROR] Review the licensed Philips SDK EULA, then set MEDIAUTO_ACCEPT_PHILIPS_EULA=1.
        pause
        exit /b 1
    )
    call conda env list | findstr /b /c:"!PHILIPS_ENV_NAME! " >nul
    if errorlevel 1 (
        echo [INFO] Creating Philips env: !PHILIPS_ENV_NAME! ^(python %PHILIPS_PY_VER%^)
        call conda create -y -n !PHILIPS_ENV_NAME! python=%PHILIPS_PY_VER% pip
        if errorlevel 1 (
            echo [ERROR] Failed to create Philips SDK environment.
            pause
            exit /b 1
        )
    ) else (
        echo [INFO] Philips env "!PHILIPS_ENV_NAME!" already exists.
    )
    call conda run -n !PHILIPS_ENV_NAME! python "%~dp0backend\scripts\bootstrap_philips.py"
    if errorlevel 1 (
        echo [ERROR] Philips SDK environment setup failed.
        pause
        exit /b 1
    )
) else (
    echo [INFO] Philips setup skipped. Set MEDIAUTO_ENABLE_PHILIPS=1 and MEDIAUTO_PHILIPS_SDK_SOURCE to enable it.
)

echo.
echo ============================================================
echo [STEP 6/7] PostgreSQL connectivity and schema
echo ============================================================
call conda run -n %ENV_NAME% python "%~dp0backend\scripts\configure_postgres_env.py" --env-file "!POSTGRES_ENV_FILE!" --mode !POSTGRES_MODE! --check-connection
if errorlevel 1 (
    echo [ERROR] PostgreSQL connectivity failed. Check POSTGRES_URI and the database service.
    pause
    exit /b 1
)

pushd "%~dp0backend"
call conda run -n %ENV_NAME% python -m alembic upgrade head
set ALEMBIC_RESULT=!ERRORLEVEL!
popd
if not "!ALEMBIC_RESULT!"=="0" (
    echo [ERROR] PostgreSQL schema migration failed.
    pause
    exit /b 1
)
echo.
echo ============================================================
echo [STEP 7/7] Runtime bootstrap and preflight
echo ============================================================
set BOOTSTRAP_ARGS=
if "%MEDIAUTO_STRICT_MODELS%"=="1" set BOOTSTRAP_ARGS=!BOOTSTRAP_ARGS! --strict-models
if "%MEDIAUTO_STRICT_DB%"=="1" set BOOTSTRAP_ARGS=!BOOTSTRAP_ARGS! --strict-db
call conda run -n %ENV_NAME% python "%~dp0backend\scripts\bootstrap_runtime.py" !BOOTSTRAP_ARGS!
if errorlevel 1 (
    echo [ERROR] Runtime bootstrap failed. Resolve the errors above and rerun install.bat.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [DONE] Install complete.
echo.
echo  Run start.bat to launch the SaaS server.
echo  Conda env: %ENV_NAME% ^(override with MEDIAUTO_CONDA_ENV^)
echo  Model bundle: set MEDIAUTO_MODEL_SOURCE=C:\path\to\models-or-archive before install.
echo.
echo  NOTE ^(OpenSlide on Windows^):
echo    openslide-python requires OpenSlide binary DLLs.
echo    Download: https://openslide.org/download/
echo    Place DLLs under a folder on PATH, or use official
echo    openslide-bin wheel if needed.
echo.
echo  NOTE ^(Migration to another machine^):
echo    Copy these from the original install:
echo      - backend\.secrets.json   ^(password pepper, AES key - CRITICAL^)
echo      - backend\uploads\        ^(WSI files, tile cache^)
echo      - backend\model\          ^(AI weights^)
echo      - PostgreSQL backup       ^(all application database data^)
echo    Losing .secrets.json breaks all existing user passwords.
echo.
echo  PostgreSQL runtime:
echo    Environment = !POSTGRES_ENV_FILE!
echo    Backend     = postgresql
echo    Deployment  = !POSTGRES_DEPLOYMENT!
echo ============================================================
pause
endlocal

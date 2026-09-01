@echo off
REM ============================================================
REM  MeDIAuto Studio SaaS - Dependency Install Script (Windows)
REM  - Verify/start MongoDB
REM  - Create/update conda env
REM  - Install PyTorch with CUDA
REM  - Install backend/requirements.txt
REM  - Verify MongoDB connectivity
REM  - Optional: restore mongo_dump if present (migration)
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
set MONGO_SERVICE=MongoDB

where conda >nul 2>&1
if errorlevel 1 (
    echo [ERROR] conda not found. Install Miniconda/Anaconda first:
    echo         https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [STEP 1/8] MongoDB Setup
echo ============================================================
where mongod >nul 2>&1
if errorlevel 1 (
    echo [WARN] mongod not found in PATH.
    if defined MONGO_URI (
        echo [INFO] MONGO_URI is configured; local MongoDB installation is skipped.
        goto MONGO_SKIP_INSTALL
    )
    echo.
    echo  Install options:
    echo    1^) winget install MongoDB.Server         ^(recommended, Windows 10+/11^)
    echo    2^) Download installer:
    echo       https://www.mongodb.com/try/download/community
    echo    3^) Use a remote/managed MongoDB and set MONGO_URI env var.
    echo.
    if not "%MEDIAUTO_AUTO_INSTALL_DB%"=="1" (
        choice /C YN /M "Try 'winget install MongoDB.Server' now"
        if errorlevel 2 goto MONGO_SKIP_INSTALL
    )
    where winget >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] winget not available. Install manually from the URL above.
        pause
        exit /b 1
    )
    winget install --id MongoDB.Server -e --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo [ERROR] winget install failed. Install MongoDB manually and rerun this script.
        pause
        exit /b 1
    )
    REM PATH may not be picked up until shell restart. Let user know.
    echo [INFO] MongoDB installed. You may need to restart this terminal so 'mongod' is on PATH.
) else (
    echo [INFO] mongod found.
)

:MONGO_SKIP_INSTALL
REM Try to start the MongoDB Windows service (silently — fine if already running or no service).
echo.
echo [INFO] Ensuring MongoDB service is running ...
sc query "%MONGO_SERVICE%" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Windows service "%MONGO_SERVICE%" not registered.
    echo        If you used winget/installer with default settings the service name is "MongoDB".
    echo        If you run mongod manually you can ignore this warning.
) else (
    sc query "%MONGO_SERVICE%" | find "RUNNING" >nul
    if errorlevel 1 (
        echo [INFO] Starting service "%MONGO_SERVICE%" ^(may require admin^) ...
        net start "%MONGO_SERVICE%" >nul 2>&1
        if errorlevel 1 (
            echo [WARN] Could not start "%MONGO_SERVICE%". Try running this script as Administrator,
            echo        or start MongoDB manually: net start %MONGO_SERVICE%
        ) else (
            echo [OK]   "%MONGO_SERVICE%" started.
        )
    ) else (
        echo [OK]   "%MONGO_SERVICE%" already running.
    )
)

echo.
echo ============================================================
echo [STEP 2/8] Conda environment "%ENV_NAME%"
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
echo [STEP 3/8] PyTorch ^(CUDA %CUDA_TAG%^)
echo ============================================================
call conda run -n %ENV_NAME% pip install --upgrade pip
call conda run -n %ENV_NAME% pip install torch torchvision --index-url https://download.pytorch.org/whl/%CUDA_TAG%
if errorlevel 1 (
    echo [WARN] CUDA build failed. Falling back to CPU-only PyTorch ...
    call conda run -n %ENV_NAME% pip install torch torchvision
)

echo.
echo ============================================================
echo [STEP 4/8] Backend requirements
echo ============================================================
call conda run -n %ENV_NAME% pip install -r "%~dp0backend\requirements.txt"
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [STEP 5/8] Optional Philips iSyntax environment
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
echo [STEP 6/8] MongoDB connectivity test
echo ============================================================
REM Use the same default URI as backend/app/config.py — env var override respected.
call conda run -n %ENV_NAME% python -c "import os; from pymongo import MongoClient; uri=os.environ.get('MONGO_URI','mongodb://localhost:27017'); MongoClient(uri, serverSelectionTimeoutMS=3000).admin.command('ping'); print('[OK] MongoDB ping succeeded @', uri)"
if errorlevel 1 (
    echo [WARN] MongoDB ping failed.
    echo        Causes:
    echo          - service not running          ^(net start %MONGO_SERVICE%^)
    echo          - wrong URI                    ^(set MONGO_URI=mongodb://host:port^)
    echo          - firewall / auth required     ^(check mongod logs^)
    echo        Backend will still install but won't start without a reachable MongoDB.
)

echo.
echo ============================================================
echo [STEP 7/8] Optional: restore MongoDB dump
echo ============================================================
set DUMP_DB_NAME=medicus_studio
if defined MONGO_DB_NAME set DUMP_DB_NAME=%MONGO_DB_NAME%
set DUMP_FOLDER=%~dp0mongo_dump\%DUMP_DB_NAME%
set DUMP_ARCHIVE_GZ=%~dp0mongo_dump.archive.gz
set DUMP_ARCHIVE=%~dp0mongo_dump.archive
set DUMP_TYPE=
set DUMP_PATH=
if exist "%DUMP_FOLDER%\" (
    set DUMP_TYPE=folder
    set DUMP_PATH=%DUMP_FOLDER%
) else if exist "%DUMP_ARCHIVE_GZ%" (
    set DUMP_TYPE=archive_gz
    set DUMP_PATH=%DUMP_ARCHIVE_GZ%
) else if exist "%DUMP_ARCHIVE%" (
    set DUMP_TYPE=archive
    set DUMP_PATH=%DUMP_ARCHIVE%
)

if defined DUMP_PATH if not exist "%~dp0backend\.secrets.json" (
    if not defined JWT_SECRET_KEY goto MISSING_RESTORE_SECRETS
    if not defined FIELD_ENCRYPTION_KEY goto MISSING_RESTORE_SECRETS
    if not defined AUTH_PEPPER goto MISSING_RESTORE_SECRETS
)
goto RESTORE_SECRETS_OK

:MISSING_RESTORE_SECRETS
echo [ERROR] A MongoDB dump was found, but its matching application secrets are missing.
echo         Restore backend\.secrets.json from the source server, or set
echo         JWT_SECRET_KEY, FIELD_ENCRYPTION_KEY, and AUTH_PEPPER before retrying.
echo         Continuing with new keys would break existing passwords/MFA data.
pause
exit /b 1

:RESTORE_SECRETS_OK

if not defined DUMP_PATH (
    echo [INFO] No dump found at expected locations — skipping restore.
    echo        Looked for:
    echo          %DUMP_FOLDER%\
    echo          %DUMP_ARCHIVE_GZ%
    echo          %DUMP_ARCHIVE%
    goto AFTER_RESTORE
)

where mongorestore >nul 2>&1
if errorlevel 1 (
    echo [WARN] Found dump at !DUMP_PATH! but mongorestore is not installed.
    echo        Install MongoDB Database Tools:
    echo          winget install MongoDB.DatabaseTools
    echo        Or download: https://www.mongodb.com/try/download/database-tools
    echo        Then re-run this script, or restore manually.
    goto AFTER_RESTORE
)

REM Count existing collections in target DB — guard against accidental --drop on live data.
set EXISTING_COUNT=0
for /f "usebackq delims=" %%i in (`call conda run -n %ENV_NAME% python -c "import os; from pymongo import MongoClient; uri=os.environ.get('MONGO_URI','mongodb://localhost:27017'); db=os.environ.get('MONGO_DB_NAME','%DUMP_DB_NAME%'); print(len(MongoClient(uri,serverSelectionTimeoutMS=3000)[db].list_collection_names()))" 2^>nul`) do set EXISTING_COUNT=%%i

echo [INFO] Found dump: !DUMP_PATH! ^(!DUMP_TYPE!^)
if not "%EXISTING_COUNT%"=="0" (
    echo [WARN] Target DB "%DUMP_DB_NAME%" already has %EXISTING_COUNT% collections.
    echo        Restoring with --drop will WIPE existing data.
    choice /C YN /M "Drop existing and restore from dump"
    if errorlevel 2 (
        echo [INFO] Restore skipped. Existing data preserved.
        goto AFTER_RESTORE
    )
) else (
    choice /C YN /M "Restore %DUMP_DB_NAME% from dump"
    if errorlevel 2 (
        echo [INFO] Restore skipped.
        goto AFTER_RESTORE
    )
)

set MONGO_URI_USE=mongodb://localhost:27017
if defined MONGO_URI set MONGO_URI_USE=%MONGO_URI%

if "!DUMP_TYPE!"=="folder" (
    mongorestore --uri="!MONGO_URI_USE!" --db=%DUMP_DB_NAME% --drop "!DUMP_PATH!"
) else if "!DUMP_TYPE!"=="archive_gz" (
    mongorestore --uri="!MONGO_URI_USE!" --archive="!DUMP_PATH!" --gzip --drop --nsInclude=%DUMP_DB_NAME%.*
) else if "!DUMP_TYPE!"=="archive" (
    mongorestore --uri="!MONGO_URI_USE!" --archive="!DUMP_PATH!" --drop --nsInclude=%DUMP_DB_NAME%.*
)
if errorlevel 1 (
    echo [WARN] mongorestore exited with non-zero status — check output above.
) else (
    echo [OK]   Restore complete.
)

:AFTER_RESTORE

echo.
echo ============================================================
echo [STEP 8/8] Runtime bootstrap and preflight
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
echo      - MongoDB dump            ^(see below^)
echo    Losing .secrets.json breaks all existing user passwords.
echo.
echo    Dump on the OLD machine ^(any of these formats^):
echo      mongodump --uri=mongodb://localhost:27017 --db=medicus_studio --out=./mongo_dump
echo      mongodump --uri=mongodb://localhost:27017 --db=medicus_studio --archive=./mongo_dump.archive --gzip
echo.
echo    Then on the NEW machine, drop the dump folder/archive at the project root
echo    and re-run this script - STEP 7 will auto-restore.
echo.
echo  MongoDB defaults:
echo    URI    = mongodb://localhost:27017   ^(override: set MONGO_URI=...^)
echo    DB     = medicus_studio              ^(override: set MONGO_DB_NAME=...^)
echo ============================================================
pause
endlocal

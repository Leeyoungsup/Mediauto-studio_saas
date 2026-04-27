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

set ENV_NAME=yslee
set PY_VER=3.12
set CUDA_TAG=cu121
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
echo [STEP 1/6] MongoDB Setup
echo ============================================================
where mongod >nul 2>&1
if errorlevel 1 (
    echo [WARN] mongod not found in PATH.
    echo.
    echo  Install options:
    echo    1^) winget install MongoDB.Server         ^(recommended, Windows 10+/11^)
    echo    2^) Download installer:
    echo       https://www.mongodb.com/try/download/community
    echo    3^) Use a remote/managed MongoDB and set MONGO_URI env var.
    echo.
    choice /C YN /M "Try 'winget install MongoDB.Server' now"
    if errorlevel 2 goto MONGO_SKIP_INSTALL
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
echo [STEP 2/6] Conda environment "%ENV_NAME%"
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
echo [STEP 3/6] PyTorch ^(CUDA %CUDA_TAG%^)
echo ============================================================
call conda run -n %ENV_NAME% pip install --upgrade pip
call conda run -n %ENV_NAME% pip install torch torchvision --index-url https://download.pytorch.org/whl/%CUDA_TAG%
if errorlevel 1 (
    echo [WARN] CUDA build failed. Falling back to CPU-only PyTorch ...
    call conda run -n %ENV_NAME% pip install torch torchvision
)

echo.
echo =========================================ㄴ===================
echo [STEP 4/6] Backend requirements
echo ============================================================
call conda run -n %ENV_NAME% pip install -r "%~dp0backend\requirements.txt"
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [STEP 5/6] MongoDB connectivity test
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
echo [STEP 6/6] Optional: restore MongoDB dump
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
echo    and re-run this script - STEP 6 will auto-restore.
echo.
echo  MongoDB defaults:
echo    URI    = mongodb://localhost:27017   ^(override: set MONGO_URI=...^)
echo    DB     = medicus_studio              ^(override: set MONGO_DB_NAME=...^)
echo ============================================================
pause
endlocal

@echo off
setlocal EnableDelayedExpansion
title Positron Urban Delivery Simulator — Setup

:: =============================================================================
::  Positron Urban Delivery Simulator — Windows Setup Script
::
::  Usage:
::    setup.bat [MODE] [OPTIONS]
::
::  Modes:
::    dev      Development mode — venv + deps + profiles + tests (default)
::    prod     Production mode — builds frontend, deploys to backend\static\
::    docker   Build and run Docker container
::    clean    Remove all generated files (venv, node_modules, dist, profiles)
::    fresh    Clean everything then run dev (full fresh install)
::
::  Options:
::    --no-tests    Skip running the test suite
::    --port PORT   Backend port (default: 8000)
::    --help        Show this help message
::
::  Examples:
::    setup.bat
::    setup.bat dev
::    setup.bat prod
::    setup.bat fresh
::    setup.bat clean
::    setup.bat docker
::    setup.bat dev --no-tests
::    setup.bat dev --port 9000
:: =============================================================================

:: ── Default values ─────────────────────────────────────────────────────────
set MODE=dev
set RUN_TESTS=true
set PORT=8000
set PYTHON=

:: ── Argument parsing ────────────────────────────────────────────────────────
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="dev"        set MODE=dev    & shift & goto :parse_args
if /i "%~1"=="--dev"      set MODE=dev    & shift & goto :parse_args
if /i "%~1"=="prod"       set MODE=prod   & shift & goto :parse_args
if /i "%~1"=="--prod"     set MODE=prod   & shift & goto :parse_args
if /i "%~1"=="docker"     set MODE=docker & shift & goto :parse_args
if /i "%~1"=="--docker"   set MODE=docker & shift & goto :parse_args
if /i "%~1"=="clean"      set MODE=clean  & shift & goto :parse_args
if /i "%~1"=="--clean"    set MODE=clean  & shift & goto :parse_args
if /i "%~1"=="fresh"      set MODE=fresh  & shift & goto :parse_args
if /i "%~1"=="--fresh"    set MODE=fresh  & shift & goto :parse_args
if /i "%~1"=="--no-tests" set RUN_TESTS=false & shift & goto :parse_args
if /i "%~1"=="--port"     shift & set PORT=%~1 & shift & goto :parse_args
if /i "%~1"=="--help"     goto :show_help
if /i "%~1"=="/?"         goto :show_help
echo [WARN] Unknown argument: %~1 (ignored)
shift
goto :parse_args
:args_done

:: ── Script directory ─────────────────────────────────────────────────────────
set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%
cd /d "%SCRIPT_DIR%"

:: ── Banner ───────────────────────────────────────────────────────────────────
echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║        Positron Urban Delivery Simulator         ║
echo  ║        AI Search Algorithm Simulator v0.1        ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  [INFO] Mode   : %MODE%
echo  [INFO] Port   : %PORT%
echo  [INFO] Tests  : %RUN_TESTS%
echo.

:: =============================================================================
::  CLEAN MODE
:: =============================================================================
if /i "%MODE%"=="clean" goto :do_clean
if /i "%MODE%"=="fresh" goto :do_fresh
goto :skip_clean

:do_fresh
call :do_clean_fn
set MODE=dev
goto :skip_clean

:do_clean
call :do_clean_fn
echo.
echo  [OK] Clean complete. Run 'setup.bat dev' to reinstall.
pause
exit /b 0

:do_clean_fn
echo.
echo ══════════════════════════════════════
echo   Cleaning generated artifacts
echo ══════════════════════════════════════
if exist ".venv"                   rmdir /s /q ".venv"                  && echo  [OK] Removed .venv\
if exist "frontend\node_modules"   rmdir /s /q "frontend\node_modules"  && echo  [OK] Removed frontend\node_modules\
if exist "frontend\dist"           rmdir /s /q "frontend\dist"          && echo  [OK] Removed frontend\dist\
if exist "backend\static"          rmdir /s /q "backend\static"         && echo  [OK] Removed backend\static\
if exist ".env"                    del /f /q ".env"                     && echo  [OK] Removed .env
for %%f in (backend\profiles\*.json) do del /f /q "%%f" 2>nul
echo  [OK] Cleared backend\profiles\*.json
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
for /d /r . %%d in (.pytest_cache) do @if exist "%%d" rd /s /q "%%d" 2>nul
for /r . %%f in (*.pyc) do @del /f /q "%%f" 2>nul
echo  [OK] Cleared Python cache files
goto :eof

:skip_clean

:: =============================================================================
::  DOCKER MODE
:: =============================================================================
if /i not "%MODE%"=="docker" goto :skip_docker

echo.
echo ══════════════════════════════════════
echo   Docker build and run
echo ══════════════════════════════════════

where docker >nul 2>&1
if errorlevel 1 (
    echo  [FAIL] Docker not found. Install from https://docs.docker.com/get-docker/
    pause & exit /b 1
)

for /f "tokens=*" %%v in ('docker --version') do set DOCKER_VER=%%v
echo  [OK] !DOCKER_VER!

echo  [INFO] Building Docker image: positron:latest
docker build -t positron:latest .
if errorlevel 1 (
    echo  [FAIL] Docker build failed.
    pause & exit /b 1
)
echo  [OK] Image built successfully

docker stop positron-app >nul 2>&1
docker rm positron-app   >nul 2>&1

echo  [INFO] Starting container on port %PORT%...
docker run -d --name positron-app -p %PORT%:8000 --restart unless-stopped positron:latest
if errorlevel 1 (
    echo  [FAIL] Container failed to start.
    pause & exit /b 1
)

echo.
echo  [OK] Container started!
echo.
echo  [INFO]  App:    http://localhost:%PORT%
echo  [INFO]  API:    http://localhost:%PORT%/docs
echo  [INFO]  Health: http://localhost:%PORT%/health
echo.
echo  [INFO]  Logs:   docker logs -f positron-app
echo  [INFO]  Stop:   docker stop positron-app
echo.
pause
exit /b 0

:skip_docker

:: =============================================================================
::  PREREQUISITES
:: =============================================================================
echo.
echo ══════════════════════════════════════
echo   Checking prerequisites
echo ══════════════════════════════════════

:: Python 3.11+
echo  [....] Checking Python 3.11+...
set PYTHON=
for %%cmd in (python3.13 python3.12 python3.11 python3 python) do (
    if "!PYTHON!"=="" (
        where %%cmd >nul 2>&1
        if not errorlevel 1 (
            for /f "tokens=2" %%v in ('%%cmd --version 2^>^&1') do (
                set PYVER=%%v
                for /f "tokens=1,2 delims=." %%a in ("%%v") do (
                    set PYMAJ=%%a
                    set PYMIN=%%b
                )
            )
            if !PYMAJ! GEQ 3 (
                if !PYMIN! GEQ 11 (
                    set PYTHON=%%cmd
                    echo  [OK]  Python !PYVER! ^(%%cmd^)
                )
            )
        )
    )
)

if "!PYTHON!"=="" (
    echo  [FAIL] Python 3.11+ not found.
    echo         Download from: https://python.org
    echo         Or install via winget: winget install Python.Python.3.12
    pause & exit /b 1
)

:: Node.js 18+
echo  [....] Checking Node.js 18+...
where node >nul 2>&1
if errorlevel 1 (
    echo  [FAIL] Node.js not found.
    echo         Download from: https://nodejs.org  ^(v18+^)
    pause & exit /b 1
)
for /f %%v in ('node --version') do set NODEVER=%%v
set NODEMAJ=%NODEVER:~1,2%
if %NODEMAJ% LSS 18 (
    echo  [FAIL] Node.js %NODEVER% found but v18+ required.
    pause & exit /b 1
)
echo  [OK]  Node.js %NODEVER%

:: pnpm
echo  [....] Checking pnpm...
where pnpm >nul 2>&1
if errorlevel 1 (
    echo  [WARN] pnpm not found. Attempting npm install -g pnpm...
    where npm >nul 2>&1
    if errorlevel 1 (
        echo  [FAIL] Neither pnpm nor npm found.
        echo         Install pnpm: https://pnpm.io/installation
        pause & exit /b 1
    )
    npm install -g pnpm --silent
    if errorlevel 1 (
        echo  [FAIL] Failed to install pnpm via npm.
        pause & exit /b 1
    )
    echo  [OK]  pnpm installed via npm
) else (
    for /f %%v in ('pnpm --version') do echo  [OK]  pnpm %%v
)

:: =============================================================================
::  DIRECTORY STRUCTURE
:: =============================================================================
echo.
echo ══════════════════════════════════════
echo   Ensuring directory structure
echo ══════════════════════════════════════
if not exist "backend\profiles" mkdir "backend\profiles"
if not exist "backend\schemas"  mkdir "backend\schemas"
if not exist "backend\static"   mkdir "backend\static"
if not exist "backend\tests"    mkdir "backend\tests"
echo  [OK]  Directories ready

:: =============================================================================
::  PYTHON VIRTUAL ENVIRONMENT
:: =============================================================================
echo.
echo ══════════════════════════════════════
echo   Python virtual environment
echo ══════════════════════════════════════

if not exist ".venv" (
    echo  [INFO] Creating .venv\ ...
    !PYTHON! -m venv .venv
    if errorlevel 1 (
        echo  [FAIL] Failed to create virtual environment.
        pause & exit /b 1
    )
    echo  [OK]  Virtual environment created
) else (
    echo  [OK]  .venv\ exists — reusing
)

call .venv\Scripts\activate.bat
echo  [OK]  Activated .venv

echo  [INFO] Upgrading pip...
python -m pip install --upgrade pip --quiet --no-warn-script-location
echo  [OK]  pip upgraded

echo  [INFO] Installing Python dependencies...
pip install -r backend\requirements.txt --quiet --no-warn-script-location
if errorlevel 1 (
    echo  [FAIL] pip install failed. Check backend\requirements.txt
    pause & exit /b 1
)
echo  [OK]  Python dependencies installed

:: =============================================================================
::  NODE.JS DEPENDENCIES
:: =============================================================================
echo.
echo ══════════════════════════════════════
echo   Node.js dependencies (frontend)
echo ══════════════════════════════════════

cd frontend
echo  [INFO] Installing frontend dependencies...
call pnpm install --frozen-lockfile --silent >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo  [OK]  Dependencies installed ^(frozen lockfile^)
) else (
    echo  [WARN] Lockfile mismatch — updating lockfile...
    call pnpm install --silent
    if errorlevel 1 (
        echo  [FAIL] pnpm install failed.
        cd ..
        pause & exit /b 1
    )
    echo  [OK]  Dependencies installed ^(lockfile updated^)
)
cd ..

:: =============================================================================
::  SCHEMA VALIDATION
:: =============================================================================
echo.
echo ══════════════════════════════════════
echo   Validating schema files
echo ══════════════════════════════════════

set SCHEMAS=cell.schema.json city_profile.schema.json algorithm_config.schema.json robot_config.schema.json deliver_sequence.schema.json metrics_summary.schema.json trace_event.schema.json

for %%s in (%SCHEMAS%) do (
    if exist "backend\schemas\%%s" (
        echo  [OK]  %%s
    ) else (
        echo  [WARN] Missing schema: backend\schemas\%%s
    )
)

:: =============================================================================
::  DEFAULT CITY PROFILES
:: =============================================================================
echo.
echo ══════════════════════════════════════
echo   Generating default city profiles
echo ══════════════════════════════════════

set PYTHONPATH=%SCRIPT_DIR%

python -c "^
import sys, pathlib; ^
sys.path.insert(0, '.'); ^
from backend.engine.profile_manager import ProfileManager; ^
mgr = ProfileManager(); ^
profiles = [(1,'alpha','Balanced'),(42,'roundtrip','Loop deliveries'),(7,'dense_city','High density'),(100,'open_grid','Open grid')]; ^
[print(f'  [OK]  {name} - already exists') if pathlib.Path(f'backend/profiles/{name}.json').exists() else (mgr.save(mgr.generate(seed, name), name), print(f'  [OK]  {name} - generated ({desc})')) for seed, name, desc in profiles] ^
"
if errorlevel 1 (
    echo  [WARN] Profile generation had issues. You can generate via API: POST /profiles/generate
)

:: =============================================================================
::  FRONTEND BUILD (prod only)
:: =============================================================================
if /i not "%MODE%"=="prod" goto :skip_prod_build

echo.
echo ══════════════════════════════════════
echo   Building frontend (production)
echo ══════════════════════════════════════

cd frontend
echo  [INFO] Running pnpm build...
call pnpm run build
if errorlevel 1 (
    echo  [FAIL] pnpm build failed.
    cd ..
    pause & exit /b 1
)
cd ..
echo  [OK]  Frontend built to frontend\dist\

if exist "backend\static" rmdir /s /q "backend\static"
mkdir backend\static
xcopy /E /I /Y "frontend\dist\*" "backend\static\" >nul
echo  [OK]  Assets deployed to backend\static\

:skip_prod_build

:: =============================================================================
::  WRITE .ENV FILE
:: =============================================================================
echo.
echo ══════════════════════════════════════
echo   Writing environment file
echo ══════════════════════════════════════

(
  echo # Positron Urban Delivery Simulator
  echo POSITRON_HOST=0.0.0.0
  echo POSITRON_PORT=%PORT%
  echo POSITRON_ENV=%MODE%
  echo PYTHONPATH=%SCRIPT_DIR%
) > .env
echo  [OK]  .env written

:: =============================================================================
::  TEST SUITE
:: =============================================================================
if /i "%RUN_TESTS%"=="false" goto :skip_tests

echo.
echo ══════════════════════════════════════
echo   Running test suite
echo ══════════════════════════════════════

set PYTHONPATH=%SCRIPT_DIR%
python -m pytest backend\tests\ -q --tb=short
if errorlevel 1 (
    echo  [WARN] Some tests failed — investigate before deploying
) else (
    echo  [OK]  All tests passed
)

:skip_tests

:: =============================================================================
::  GENERATE LAUNCH SCRIPTS
:: =============================================================================
echo.
echo ══════════════════════════════════════
echo   Writing launch helper scripts
echo ══════════════════════════════════════

:: run_backend.bat
(
  echo @echo off
  echo :: Positron Backend — Development server with hot reload
  echo cd /d "%SCRIPT_DIR%"
  echo call .venv\Scripts\activate.bat
  echo set PYTHONPATH=%SCRIPT_DIR%
  echo uvicorn backend.websocket.web_server:app --reload --host 0.0.0.0 --port %PORT% --log-level info
) > run_backend.bat
echo  [OK]  run_backend.bat

:: run_frontend.bat
(
  echo @echo off
  echo :: Positron Frontend — Vite development server with HMR
  echo cd /d "%SCRIPT_DIR%\frontend"
  echo call pnpm dev
) > run_frontend.bat
echo  [OK]  run_frontend.bat

if /i "%MODE%"=="prod" (
  :: run_prod.bat
  (
    echo @echo off
    echo :: Positron Production Server — serves frontend and backend on one port
    echo cd /d "%SCRIPT_DIR%"
    echo call .venv\Scripts\activate.bat
    echo set PYTHONPATH=%SCRIPT_DIR%
    echo uvicorn backend.websocket.web_server:app --host 0.0.0.0 --port %PORT% --workers 1 --log-level info
  ) > run_prod.bat
  echo  [OK]  run_prod.bat
)

:: =============================================================================
::  COMPLETION SUMMARY
:: =============================================================================
echo.
echo ══════════════════════════════════════
echo   Setup complete!
echo ══════════════════════════════════════
echo.

if /i "%MODE%"=="dev" (
    echo  Development mode — two servers required:
    echo.
    echo  [Terminal 1 - Backend]
    echo    run_backend.bat
    echo.
    echo  [Terminal 2 - Frontend]
    echo    run_frontend.bat
    echo.
    echo  Then open: http://localhost:5173
    echo  API docs:  http://localhost:%PORT%/docs
)

if /i "%MODE%"=="prod" (
    echo  Production mode — single server:
    echo.
    echo  [Start]
    echo    run_prod.bat
    echo.
    echo  Then open: http://localhost:%PORT%
    echo  API docs:  http://localhost:%PORT%/docs
)

echo.
pause
exit /b 0

:: =============================================================================
::  HELP
:: =============================================================================
:show_help
echo.
echo  Positron Urban Delivery Simulator — Setup Script
echo.
echo  Usage: setup.bat [MODE] [OPTIONS]
echo.
echo  Modes:
echo    dev      Development mode ^(default^)
echo    prod     Production mode — builds frontend
echo    docker   Docker build + run
echo    clean    Remove all generated artifacts
echo    fresh    Clean then install fresh
echo.
echo  Options:
echo    --no-tests    Skip the test suite
echo    --port PORT   Backend port ^(default: 8000^)
echo    --help        Show this help
echo.
echo  Examples:
echo    setup.bat
echo    setup.bat prod
echo    setup.bat fresh
echo    setup.bat dev --no-tests --port 9000
echo.
pause
exit /b 0

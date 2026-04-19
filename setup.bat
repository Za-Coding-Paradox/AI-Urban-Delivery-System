@echo off
setlocal EnableDelayedExpansion
title Positron Urban Delivery Simulator — Setup

:: =============================================================================
::  Positron Urban Delivery Simulator — Windows Setup Script
::  Usage:  setup.bat [dev | prod]
::  Default: dev
:: =============================================================================

set MODE=dev
if "%~1"=="prod" set MODE=prod
if "%~1"=="--prod" set MODE=prod
if "%~1"=="--dev" set MODE=dev
if "%~1"=="--help" goto :show_help
if "%~1"=="/?" goto :show_help

:: ── Banner ────────────────────────────────────────────────────────────────────
echo.
echo  [Positron] Urban Delivery Simulator
echo  [Positron] AI Search Algorithm Simulator v0.1
echo  [Positron] Mode: %MODE%
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
echo [1/8] Checking Python 3.11+...
python --version >nul 2>&1
if errorlevel 1 (
    python3 --version >nul 2>&1
    if errorlevel 1 (
        echo [FAIL] Python not found. Download from https://python.org
        pause & exit /b 1
    )
    set PYTHON=python3
) else (
    set PYTHON=python
)

for /f "tokens=2" %%v in ('!PYTHON! --version 2^>^&1') do set PYVER=%%v
echo [OK] Python !PYVER!

:: ── Check Node ───────────────────────────────────────────────────────────────
echo [2/8] Checking Node.js 18+...
node --version >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Node.js not found. Download from https://nodejs.org
    pause & exit /b 1
)
for /f %%v in ('node --version') do set NODEVER=%%v
echo [OK] Node.js !NODEVER!

:: ── Virtual environment ───────────────────────────────────────────────────────
echo [3/8] Setting up Python virtual environment...
if not exist ".venv" (
    !PYTHON! -m venv .venv
    echo [OK] Created .venv/
) else (
    echo [OK] .venv/ exists
)

call .venv\Scripts\activate.bat
echo [OK] Activated .venv

:: ── Upgrade pip ───────────────────────────────────────────────────────────────
echo [4/8] Upgrading pip...
pip install --upgrade pip --quiet
echo [OK] pip upgraded

:: ── Python dependencies ───────────────────────────────────────────────────────
echo [5/8] Installing Python dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [FAIL] pip install failed. Check requirements.txt
    pause & exit /b 1
)
echo [OK] Python packages installed

:: ── Node dependencies ─────────────────────────────────────────────────────────
echo [6/8] Installing Node.js dependencies...
if exist "package-lock.json" (
    npm ci --silent
) else (
    npm install --silent
)
if errorlevel 1 (
    echo [FAIL] npm install failed
    pause & exit /b 1
)
echo [OK] Node.js packages installed

:: ── Directory structure ───────────────────────────────────────────────────────
echo [7/8] Ensuring directories...
if not exist "backend\profiles" mkdir backend\profiles
if not exist "backend\schemas"  mkdir backend\schemas
if not exist "backend\static"   mkdir backend\static
echo [OK] Directories ready

:: ── Generate profiles ─────────────────────────────────────────────────────────
echo [7b] Generating default city profiles...
!PYTHON! -c "
import sys
sys.path.insert(0, '.')
try:
    from backend.engine.profile_manager import ProfileManager
    import pathlib
    mgr = ProfileManager()
    for seed, name in [(1,'alpha'),(42,'roundtrip'),(7,'dense_city'),(100,'open_grid')]:
        p = pathlib.Path(f'backend/profiles/{name}.json')
        if p.exists():
            print(f'  OK  {name} (exists)')
        else:
            prof = mgr.generate(seed, name)
            mgr.save(prof, name)
            print(f'  OK  {name} (seed={seed})')
except Exception as e:
    print(f'  WARN  profiles: {e}')
"

:: ── Production build ─────────────────────────────────────────────────────────
if "%MODE%"=="prod" (
    echo [8/8] Building frontend for production...
    npm run build
    if errorlevel 1 (
        echo [FAIL] npm run build failed
        pause & exit /b 1
    )
    echo [OK] Frontend built to dist/

    :: Copy dist to backend/static
    xcopy /E /I /Y dist\* backend\static\ >nul
    echo [OK] Assets deployed to backend\static\
) else (
    echo [8/8] Skipping production build (dev mode)
)

:: ── Run tests ─────────────────────────────────────────────────────────────────
echo.
echo [Tests] Running backend test suite...
!PYTHON! -m pytest backend\tests\ -q --tb=short 2>&1 | tail /n 5
echo.

:: ── Write launch scripts ──────────────────────────────────────────────────────
echo @echo off > run_backend.bat
echo call .venv\Scripts\activate.bat >> run_backend.bat
echo uvicorn backend.websocket.web_server:app --reload --host 0.0.0.0 --port 8000 >> run_backend.bat
echo [OK] run_backend.bat created

echo @echo off > run_frontend.bat
echo npm run dev >> run_frontend.bat
echo [OK] run_frontend.bat created

if "%MODE%"=="prod" (
    echo @echo off > run_prod.bat
    echo call .venv\Scripts\activate.bat >> run_prod.bat
    echo uvicorn backend.websocket.web_server:app --host 0.0.0.0 --port 8000 >> run_prod.bat
    echo [OK] run_prod.bat created
)

:: ── Done ──────────────────────────────────────────────────────────────────────
echo.
echo ════════════════════════════════════════
echo  Setup complete!
echo ════════════════════════════════════════
echo.
if "%MODE%"=="dev" (
    echo  Development mode:
    echo.
    echo  Terminal 1 (backend):
    echo    run_backend.bat
    echo.
    echo  Terminal 2 (frontend):
    echo    run_frontend.bat
    echo.
    echo  Then open: http://localhost:5173
) else (
    echo  Production mode:
    echo.
    echo  Start server:
    echo    run_prod.bat
    echo.
    echo  Then open: http://localhost:8000
)
echo.
pause
exit /b 0

:show_help
echo.
echo  Usage: setup.bat [dev ^| prod]
echo.
echo    dev    Development mode — Vite dev server + uvicorn reload
echo    prod   Production mode  — build frontend, serve via uvicorn
echo.
pause
exit /b 0

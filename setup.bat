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

:: ── Check Node & PNPM ────────────────────────────────────────────────────────
echo [2/8] Checking Node.js 18+ and pnpm...
node --version >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Node.js not found. Download from https://nodejs.org
    pause & exit /b 1
)
for /f %%v in ('node --version') do set NODEVER=%%v
echo [OK] Node.js !NODEVER!

call pnpm --version >nul 2>&1
if errorlevel 1 (
    echo [FAIL] pnpm not found. Please run 'npm install -g pnpm'
    pause & exit /b 1
)
echo [OK] pnpm found

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

:: ── Upgrade pip & Dependencies ────────────────────────────────────────────────
echo [4/8] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo [OK] pip upgraded

echo [5/8] Installing Python dependencies...
:: Ensure httpx is in requirements for testing
findstr /C:"httpx" backend\requirements.txt >nul
if errorlevel 1 (
    echo httpx>> backend\requirements.txt
)
pip install -r backend\requirements.txt --quiet
if errorlevel 1 (
    echo [FAIL] pip install failed. Check backend\requirements.txt
    pause & exit /b 1
)
echo [OK] Python packages installed

:: ── Node dependencies (Bulletproof) ──────────────────────────────────────────
echo [6/8] Setting up Node.js environment (frontend)...
cd frontend
echo   ^> Attempting strict install (frozen-lockfile)...
call pnpm install --frozen-lockfile --silent >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo   [OK] Dependencies installed successfully.
) else (
    echo   [WARN] Lockfile mismatch detected. Auto-fixing and updating lockfile...
    call pnpm install --silent
    if errorlevel 1 (
        echo   [FAIL] pnpm install failed.
        cd ..
        pause & exit /b 1
    )
    echo   [OK] Dependencies installed and lockfile updated.
)
cd ..

:: ── Directory structure ───────────────────────────────────────────────────────
echo [7/8] Ensuring directories...
if not exist "backend\profiles" mkdir backend\profiles
if not exist "backend\schemas"  mkdir backend\schemas
if not exist "backend\static"   mkdir backend\static
echo [OK] Directories ready

:: ── Generate profiles ─────────────────────────────────────────────────────────
echo [7b] Generating default city profiles...
set PYTHONPATH=%cd%
!PYTHON! -c "import sys, pathlib; sys.path.insert(0, '.'); from backend.engine.profile_manager import ProfileManager; mgr = ProfileManager(); [mgr.save(mgr.generate(seed, name), name) for seed, name in [(1,'alpha'),(42,'roundtrip'),(7,'dense_city'),(100,'open_grid')] if not pathlib.Path(f'backend/profiles/{name}.json').exists()]"
echo [OK] Profiles validated

:: ── Production build ─────────────────────────────────────────────────────────
if "%MODE%"=="prod" (
    echo [8/8] Building frontend for production...
    cd frontend
    call pnpm run build
    if errorlevel 1 (
        echo [FAIL] pnpm run build failed
        cd ..
        pause & exit /b 1
    )
    cd ..
    echo [OK] Frontend built to frontend\dist\

    xcopy /E /I /Y frontend\dist\* backend\static\ >nul
    echo [OK] Assets deployed to backend\static\
) else (
    echo [8/8] Skipping production build (dev mode)
)

:: ── Run tests ─────────────────────────────────────────────────────────────────
echo.
echo [Tests] Running backend test suite...
set PYTHONPATH=%cd%
!PYTHON! -m pytest backend\tests\ -q --tb=short
echo.

:: ── Write launch scripts ──────────────────────────────────────────────────────
echo @echo off > run_backend.bat
echo call .venv\Scripts\activate.bat >> run_backend.bat
echo set PYTHONPATH=%%cd%% >> run_backend.bat
echo uvicorn backend.websocket.web_server:app --reload --host 0.0.0.0 --port 8000 >> run_backend.bat

echo @echo off > run_frontend.bat
echo cd frontend >> run_frontend.bat
echo call pnpm run dev >> run_frontend.bat

if "%MODE%"=="prod" (
    echo @echo off > run_prod.bat
    echo call .venv\Scripts\activate.bat >> run_prod.bat
    echo set PYTHONPATH=%%cd%% >> run_prod.bat
    echo uvicorn backend.websocket.web_server:app --host 0.0.0.0 --port 8000 >> run_prod.bat
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

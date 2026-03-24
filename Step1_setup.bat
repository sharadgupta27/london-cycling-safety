@echo off
:: ============================================================
:: London Cycling Safety — Step 1: Environment Setup
:: ============================================================
:: Run this ONCE before running Step2_run_dev.bat or
:: Step2_run_prod.bat.  It handles:
::
::   1. Check Python 3.11+ is on PATH
::   2. Create / locate .venv  (parent dir first, then project-local)
::   3. Install Python dependencies from requirements.txt
::   4. Create .env from .env.example if .env does not exist
::
:: .venv search order:
::   1. <parent_dir>\.venv  (shared venv one level above project)
::   2. <project>\.venv     (project-local venv, created on demand)
::
:: Requirements: Python 3.11+ on PATH, uv on PATH, internet connection
:: ============================================================

setlocal EnableDelayedExpansion

:: ── Locate the directory this .bat lives in ──────────────────────────────────
set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

:: ── Resolve .venv ─────────────────────────────────────────────────────────────
:: Priority 1: <parent_dir>\.venv  (shared venv one level above project)
:: Priority 2: <project>\.venv     (project-local venv, created on demand)
for %%I in ("%PROJECT_DIR%\..") do set "PARENT_DIR=%%~fI"
set "HOME_VENV=%PARENT_DIR%\.venv"
set "PROJECT_VENV=%PROJECT_DIR%\.venv"

if exist "%HOME_VENV%\Scripts\python.exe" (
    set "VENV_DIR=%HOME_VENV%"
    set "VENV_SOURCE=parent directory (%PARENT_DIR%\.venv)"
) else (
    set "VENV_DIR=%PROJECT_VENV%"
    set "VENV_SOURCE=project directory (.venv)"
)

set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

echo.
echo ============================================================
echo  London Cycling Safety — Step 1: Environment Setup
echo ============================================================
echo  Project: %PROJECT_DIR%
echo.

:: ── Step 1: Python check ─────────────────────────────────────────────────────
echo [1/3] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python is not on PATH.
    echo  Please install Python 3.11+ from https://python.org and re-run.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  Found: %%v

:: ── Step 2: Virtual environment ──────────────────────────────────────────────
echo.
echo [2/3] Setting up virtual environment...
if exist "%HOME_VENV%\Scripts\python.exe" (
    echo  Using existing parent-level venv: %HOME_VENV%
    echo  Checking dependencies are installed...
    uv pip install -r "%PROJECT_DIR%\requirements.txt" --python "%PYTHON_EXE%" --quiet
    if errorlevel 1 (
        echo  ERROR: uv pip install failed.
        pause
        exit /b 1
    )
) else if not exist "%PYTHON_EXE%" (
    echo  No parent-directory .venv found. Creating project-local .venv ...
    uv venv "%VENV_DIR%"
    if errorlevel 1 (
        echo  ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  Installing dependencies from requirements.txt ...
    uv pip install -r "%PROJECT_DIR%\requirements.txt" --python "%PYTHON_EXE%"
    if errorlevel 1 (
        echo  ERROR: uv pip install failed.
        pause
        exit /b 1
    )
) else (
    echo  Using existing project-local venv: %VENV_DIR%
    echo  Checking for dependency updates...
    uv pip install -r "%PROJECT_DIR%\requirements.txt" --python "%PYTHON_EXE%" --quiet
)
echo  Active venv: %VENV_SOURCE%
echo  OK

:: ── Step 3: .env file ────────────────────────────────────────────────────────
echo.
echo [3/3] Checking .env file...
if not exist "%PROJECT_DIR%\.env" (
    if exist "%PROJECT_DIR%\.env.example" (
        echo  .env not found — copying from .env.example
        copy /Y "%PROJECT_DIR%\.env.example" "%PROJECT_DIR%\.env" >nul
        echo  Created .env — using default DuckDB settings.
        echo  Edit .env with your GCP values if you plan to run the production pipeline.
    ) else (
        echo  WARNING: No .env or .env.example found. Continuing with defaults.
    )
) else (
    echo  .env found.
)

echo.
echo ============================================================
echo  Setup complete!
echo.
echo  Next steps — choose ONE of:
echo    Step2_run_dev.bat   — run the local DuckDB pipeline + dashboard
echo    Step2_run_prod.bat  — run the production pipeline (Google BigQuery)
echo.
echo  For BigQuery, first edit .env with your GCP credentials.
echo ============================================================
pause

endlocal

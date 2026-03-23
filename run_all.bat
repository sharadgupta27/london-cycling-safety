@echo off
:: ============================================================
:: London Cycling Safety — One-Click Runner (Windows)
:: ============================================================
:: Double-click or run from cmd/PowerShell to:
::   1. Locate .venv  (home directory first, then project directory)
::   2. Install Python dependencies
::   3. Ingest TFL + STATS19 data  (dlt → DuckDB)
::   4. Run DuckDB spatial transforms
::   5. Run dbt build  (seeds → staging → intermediate → marts + tests)
::   6. Launch the Streamlit dashboard at http://localhost:8501
::
:: .venv search order:
::   1. <dataengg_local>\.venv  (shared workspace venv, one level up)
::   2. <project>\.venv          (project-local venv, created if missing)
::
:: Requirements: Python 3.11+ on PATH, internet connection
:: ============================================================

setlocal EnableDelayedExpansion

:: ── Locate the directory this .bat lives in ──────────────────────────────────
set "PROJECT_DIR=%~dp0"
:: Remove trailing backslash
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

:: ── Resolve .venv: workspace-level venv wins over project-local ───────────────
:: Priority 1: <dataengg_local>\.venv  (shared venv one level above project)
:: Priority 2: <project>\.venv         (project-local venv, created on demand)
for %%I in ("%PROJECT_DIR%\..") do set "DATAENGG_LOCAL=%%~fI"
set "HOME_VENV=%DATAENGG_LOCAL%\.venv"
set "PROJECT_VENV=%PROJECT_DIR%\.venv"

if exist "%HOME_VENV%\Scripts\python.exe" (
    set "VENV_DIR=%HOME_VENV%"
    set "VENV_SOURCE=workspace directory (%DATAENGG_LOCAL%\.venv)"
) else (
    set "VENV_DIR=%PROJECT_VENV%"
    set "VENV_SOURCE=project directory (.venv)"
)

set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "STREAMLIT_EXE=%VENV_DIR%\Scripts\streamlit.exe"

echo.
echo ============================================================
echo  London Cycling Safety Pipeline
echo ============================================================
echo  Project: %PROJECT_DIR%
echo.

:: ── Step 1: Python check ──────────────────────────────────────────────────────
echo [1/5] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python is not on PATH.
    echo  Please install Python 3.11+ from https://python.org and re-run.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  Found: %%v

:: ── Step 2: Virtual environment ───────────────────────────────────────────────
echo.
echo [2/5] Setting up virtual environment...
if exist "%HOME_VENV%\Scripts\python.exe" (
    echo  Using existing workspace-level venv: %HOME_VENV%
    echo  Checking dependencies are installed...
    uv pip install -r "%PROJECT_DIR%\requirements.txt" --python "%PYTHON_EXE%" --quiet
    if errorlevel 1 (
        echo  ERROR: uv pip install failed.
        pause
        exit /b 1
    )
) else if not exist "%PYTHON_EXE%" (
    echo  No home-directory .venv found. Creating project-local .venv ...
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

:: ── Step 3: .env file ─────────────────────────────────────────────────────────
echo.
echo [3/5] Checking .env file...
if not exist "%PROJECT_DIR%\.env" (
    if exist "%PROJECT_DIR%\.env.example" (
        echo  .env not found — copying from .env.example
        copy /Y "%PROJECT_DIR%\.env.example" "%PROJECT_DIR%\.env" >nul
        echo  Created .env — using default DuckDB settings.
    ) else (
        echo  WARNING: No .env or .env.example found. Continuing with defaults.
    )
) else (
    echo  .env found.
)

:: ── Step 4: Run the pipeline ──────────────────────────────────────────────────
echo.
echo [4/5] Running pipeline (ingest + transforms + dbt build) ...
echo  This may take 5-15 minutes on first run.
echo.
"%PYTHON_EXE%" "%PROJECT_DIR%\run_pipeline.py"
if errorlevel 1 (
    echo.
    echo  ERROR: Pipeline did not complete successfully.
    echo  Check the output above for details.
    echo  You can re-run individual steps — see DEPLOYMENT.md for commands.
    pause
    exit /b 1
)

:: ── Step 5: Launch dashboard ──────────────────────────────────────────────────
echo.
echo [5/5] Launching Streamlit dashboard...
echo  Opening http://localhost:8501 in your browser.
echo  Press Ctrl+C in this window to stop the dashboard.
echo.
"%STREAMLIT_EXE%" run "%PROJECT_DIR%\dashboard\app.py" ^
    --server.port 8501 ^
    --server.headless false ^
    --browser.serverAddress localhost

endlocal

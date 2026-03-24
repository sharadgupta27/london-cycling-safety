@echo off
:: ============================================================
:: London Cycling Safety - Step 2: Development Pipeline (DuckDB)
:: ============================================================
:: Prerequisite: run Step1_setup.bat at least once first.
::
:: Runs the local development pipeline:
::   1. Ingest TFL + STATS19 data  (dlt → DuckDB)
::   2. Run DuckDB spatial transforms
::   3. Run dbt build  (seeds → staging → intermediate → marts + tests)
::   4. Launch the Streamlit dashboard at http://localhost:8501
::
:: No cloud account required - everything runs locally in DuckDB.
::
:: .venv search order (same as Step1_setup.bat):
::   1. <parent_dir>\.venv  (shared venv one level above project)
::   2. <project>\.venv     (project-local venv)
:: ============================================================

setlocal EnableDelayedExpansion

:: ── Locate the directory this .bat lives in ──────────────────────────────────
set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

:: ── Resolve .venv ─────────────────────────────────────────────────────────────
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
set "STREAMLIT_EXE=%VENV_DIR%\Scripts\streamlit.exe"

echo.
echo ============================================================
echo  London Cycling Safety - Step 2: Development Pipeline
echo ============================================================
echo  Project: %PROJECT_DIR%
echo.

:: ── Check venv ────────────────────────────────────────────────────────────────
echo  Using venv: %VENV_SOURCE%
if not exist "%PYTHON_EXE%" (
    echo  ERROR: Virtual environment not found.
    echo  Please run Step1_setup.bat first to create the environment.
    pause
    exit /b 1
)
echo  OK

:: ── Check .env ────────────────────────────────────────────────────────────────
echo.
if not exist "%PROJECT_DIR%\.env" (
    echo  WARNING: .env not found. Run Step1_setup.bat first.
    echo  Continuing with defaults...
) else (
    echo  .env found.
)

:: ── Run the dev pipeline ──────────────────────────────────────────────────────
echo.
echo [1/2] Running development pipeline (ingest + transforms + dbt build) ...
echo  Target: DuckDB (local)
echo  This may take 5-15 minutes on first run.
echo.
"%PYTHON_EXE%" "%PROJECT_DIR%\run_pipeline.py"
if errorlevel 1 (
    echo.
    echo  ERROR: Pipeline did not complete successfully.
    echo  Check the output above for details.
    echo  You can re-run individual steps - see DEPLOYMENT.md for commands.
    pause
    exit /b 1
)

:: ── Launch dashboard ─────────────────────────────────────────────────────────
echo.
echo [2/2] Launching Streamlit dashboard...
echo  Opening http://localhost:8501 in your browser.
echo  Press Ctrl+C in this window to stop the dashboard.
echo.
"%STREAMLIT_EXE%" run "%PROJECT_DIR%\dashboard\app.py" ^
    --server.port 8501 ^
    --server.headless false ^
    --browser.serverAddress localhost

endlocal

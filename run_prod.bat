@echo off
:: ============================================================
:: London Cycling Safety — Production Runner (BigQuery)
:: ============================================================
:: Runs the full production pipeline:
::   1. Validate GCP credentials (checks GOOGLE_APPLICATION_CREDENTIALS)
::   2. Ingest TFL + STATS19 → Google BigQuery  (dlt)
::   3. Run dbt build --target prod             (BigQuery GIS)
::
:: Prerequisites:
::   - Python venv at <dataengg_local>\.venv  (or project-local .venv)
::   - .env file with GCP_PROJECT_ID, GCP_BQ_DATASET, GCP_BQ_LOCATION,
::     GOOGLE_APPLICATION_CREDENTIALS
::   - credentials\service_account.json  (your GCP JSON key)
::
:: .venv search order:
::   1. <dataengg_local>\.venv  (shared workspace venv, one level up)
::   2. <project>\.venv         (project-local venv, created if missing)
:: ============================================================

setlocal EnableDelayedExpansion

set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

:: ── Resolve .venv: workspace-level venv wins over project-local ──────────────
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

echo.
echo ============================================================
echo  London Cycling Safety — Production Pipeline (BigQuery)
echo ============================================================
echo  Project: %PROJECT_DIR%
echo.

:: ── Check venv ───────────────────────────────────────────────────────────────
echo  Using venv: %VENV_SOURCE%
if not exist "%PYTHON_EXE%" (
    echo  ERROR: Virtual environment not found.
    echo  Run run_all.bat first to set up the environment, then re-run this script.
    pause
    exit /b 1
)

:: ── Install BigQuery extras if not present ───────────────────────────────────
echo [1/3] Checking BigQuery dependencies...
uv pip install "dlt[bigquery]>=0.5.0" "dbt-bigquery>=1.8.0" --python "%PYTHON_EXE%" --quiet
echo  OK

:: ── Check .env and credentials ───────────────────────────────────────────────
echo.
echo [2/3] Checking .env and credentials...
if not exist "%PROJECT_DIR%\.env" (
    echo  ERROR: .env file not found.
    echo  Copy .env.example to .env and fill in your GCP values.
    pause
    exit /b 1
)
if not exist "%PROJECT_DIR%\credentials\service_account.json" (
    echo  WARNING: credentials\service_account.json not found.
    echo  If GOOGLE_APPLICATION_CREDENTIALS in .env points elsewhere, ignore this.
)
echo  .env found. Continuing...

:: ── Run production pipeline ──────────────────────────────────────────────────
echo.
echo [3/3] Running production pipeline (target=prod) ...
echo  Data will be written to Google BigQuery.
echo.
echo  Extra flags: %*
echo  Tip: pass --skip-ingest to re-run only dbt (skips TFL + accidents ingest)
echo.
"%PYTHON_EXE%" "%PROJECT_DIR%\orchestration\pipeline.py" --target prod %*
if errorlevel 1 (
    echo.
    echo  ERROR: Production pipeline failed.
    echo  Check output above. Common issues:
    echo    - GOOGLE_APPLICATION_CREDENTIALS path wrong in .env
    echo    - Service account missing BigQuery Data Editor / Job User roles
    echo    - GCP_PROJECT_ID not set or incorrect
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Production pipeline complete!
echo  Check Google BigQuery console for new data:
echo    Dataset: raw         (ingested tables)
echo    Dataset: (GCP_BQ_DATASET in .env)  (dbt output tables)
echo ============================================================
pause

endlocal

@echo off
:: ============================================================
:: London Cycling Safety — Step 2: Production Pipeline (BigQuery)
:: ============================================================
:: Prerequisite: run Step1_setup.bat at least once first.
::
:: Runs the full production pipeline:
::   1. Install BigQuery extras  (dlt[bigquery], dbt-bigquery)
::   2. Validate .env and GCP credentials
::   3. Ingest TFL + STATS19 → Google BigQuery  (dlt)
::      + Run dbt build --target prod           (BigQuery GIS)
::   4. Launch the Streamlit dashboard at http://localhost:8501
::      (dashboard reads from BigQuery when target=prod is active)
::
:: Before running, ensure .env contains:
::   GOOGLE_APPLICATION_CREDENTIALS=<path to service_account.json>
::   GCP_PROJECT_ID=<your-gcp-project-id>
::   GCP_BQ_DATASET=dbt_london_cycling
::   GCP_BQ_LOCATION=EU
::
:: Place the GCP JSON key at:  credentials\service_account.json
::
:: .venv search order (same as Step1_setup.bat):
::   1. <parent_dir>\.venv  (shared venv one level above project)
::   2. <project>\.venv     (project-local venv)
::
:: Tip: pass --skip-ingest to re-run only dbt (skips TFL + accidents ingest)
::   Step2_run_prod.bat --skip-ingest
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
echo  London Cycling Safety — Step 2: Production Pipeline (BigQuery)
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

:: ── Install BigQuery extras if not already present ───────────────────────────
echo.
echo [1/3] Checking BigQuery dependencies...
uv pip install "dlt[bigquery]>=0.5.0" "dbt-bigquery>=1.8.0" --python "%PYTHON_EXE%" --quiet
if errorlevel 1 (
    echo  ERROR: Failed to install BigQuery dependencies.
    pause
    exit /b 1
)
echo  OK

:: ── Validate .env and credentials ────────────────────────────────────────────
echo.
echo [2/3] Checking .env and credentials...
if not exist "%PROJECT_DIR%\.env" (
    echo  ERROR: .env file not found.
    echo  Run Step1_setup.bat first, then edit .env with your GCP values.
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
echo [3/4] Running production pipeline (target=prod) ...
echo  Target: Google BigQuery
echo.
echo  Extra flags: %*
echo  Tip: pass --skip-ingest to re-run only dbt (skips TFL + accidents ingest)
echo.
"%PYTHON_EXE%" "%PROJECT_DIR%\orchestration\pipeline.py" --target prod %*
if errorlevel 1 (
    echo.
    echo  ERROR: Production pipeline failed.
    echo  Check output above. Common issues:
    echo    - GOOGLE_APPLICATION_CREDENTIALS path wrong or missing in .env
    echo    - Service account missing BigQuery Data Editor / Job User roles
    echo    - GCP_PROJECT_ID not set or incorrect
    echo  See DEPLOYMENT.md §6 for full setup instructions.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Production pipeline complete!
echo  Check Google BigQuery console for new data:
echo    Dataset: raw                    (ingested tables)
echo    Dataset: (GCP_BQ_DATASET in .env)  (dbt output tables)
echo ============================================================

:: ── Launch dashboard ─────────────────────────────────────────────────────────
echo.
echo [4/4] Launching Streamlit dashboard...
echo  Opening http://localhost:8501 in your browser.
echo  The dashboard reads from BigQuery when configured with target=prod.
echo  Press Ctrl+C in this window to stop the dashboard.
echo.
"%STREAMLIT_EXE%" run "%PROJECT_DIR%\dashboard\app.py" ^
    --server.port 8501 ^
    --server.headless false ^
    --browser.serverAddress localhost

endlocal

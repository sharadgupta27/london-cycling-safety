@echo off
:: ============================================================
:: London Cycling Safety - Project Cleaner (Windows)
:: ============================================================
:: Removes all generated / temporary artefacts:
::   • DuckDB database  (london_cycling.duckdb)
::   • dbt build output (target/)
::   • dbt packages     (dbt_packages/)
::   • Log files        (logs/)
::   • Python caches    (__pycache__/, *.pyc, .pytest_cache/)
::
:: Safe to re-run — only deletes generated files, never source code.
:: After cleaning, run run_all.bat to rebuild everything from scratch.
:: ============================================================

setlocal EnableDelayedExpansion

:: ── Locate the directory this .bat lives in ──────────────────────────────────
set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

echo.
echo ============================================================
echo  London Cycling Safety - Clean
echo ============================================================
echo  Project: %PROJECT_DIR%
echo.

:: ── Confirm before destructive delete ────────────────────────────────────────
set /p CONFIRM="This will delete the database and all generated files. Continue? [y/N] "
if /i not "%CONFIRM%"=="y" (
    echo  Aborted.
    goto :end
)

echo.

:: ── 1. DuckDB database ───────────────────────────────────────────────────────
echo [1/5] Removing DuckDB database...
if exist "%PROJECT_DIR%\london_cycling.duckdb" (
    del /f /q "%PROJECT_DIR%\london_cycling.duckdb"
    echo  Deleted: london_cycling.duckdb
) else (
    echo  Not found: london_cycling.duckdb  (skipping)
)
:: Also remove any WAL / lock files left by DuckDB
if exist "%PROJECT_DIR%\london_cycling.duckdb.wal" (
    del /f /q "%PROJECT_DIR%\london_cycling.duckdb.wal"
    echo  Deleted: london_cycling.duckdb.wal
)

:: ── 2. dbt target directory ───────────────────────────────────────────────────
echo.
echo [2/5] Removing dbt build artefacts (target/)...
if exist "%PROJECT_DIR%\target" (
    rmdir /s /q "%PROJECT_DIR%\target"
    echo  Deleted: target\
) else (
    echo  Not found: target\  (skipping)
)

:: ── 3. dbt packages ───────────────────────────────────────────────────────────
echo.
echo [3/5] Removing dbt packages (dbt_packages/)...
if exist "%PROJECT_DIR%\dbt_packages" (
    rmdir /s /q "%PROJECT_DIR%\dbt_packages"
    echo  Deleted: dbt_packages\
) else (
    echo  Not found: dbt_packages\  (skipping)
)

:: ── 4. Log files ──────────────────────────────────────────────────────────────
echo.
echo [4/5] Removing log files (logs/)...
if exist "%PROJECT_DIR%\logs" (
    rmdir /s /q "%PROJECT_DIR%\logs"
    echo  Deleted: logs\
) else (
    echo  Not found: logs\  (skipping)
)

:: ── 5. Python caches ──────────────────────────────────────────────────────────
echo.
echo [5/5] Removing Python caches (__pycache__, *.pyc, .pytest_cache)...

:: .pytest_cache
if exist "%PROJECT_DIR%\.pytest_cache" (
    rmdir /s /q "%PROJECT_DIR%\.pytest_cache"
    echo  Deleted: .pytest_cache\
)

:: All __pycache__ directories recursively
for /d /r "%PROJECT_DIR%" %%d in (__pycache__) do (
    if exist "%%d" (
        rmdir /s /q "%%d"
        echo  Deleted: %%d
    )
)

:: All .pyc files recursively
set "PYC_COUNT=0"
for /r "%PROJECT_DIR%" %%f in (*.pyc) do (
    del /f /q "%%f"
    set /a PYC_COUNT+=1
)
if !PYC_COUNT! gtr 0 echo  Deleted !PYC_COUNT! .pyc file(s)

echo.
echo ============================================================
echo  Clean complete.
echo  Run run_all.bat to rebuild the pipeline from scratch.
echo ============================================================
echo.

:end
endlocal
pause

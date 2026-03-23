@echo off
:: ==============================================================================
:: upload_flows.bat
:: Upload (or update) all Kestra flow YAMLs to the locally running Kestra server.
::
:: Prerequisites
::   - Kestra is running on http://localhost:8080  (docker compose up -d)
::   - curl is available (built into Windows 10 1803+)
::
:: Usage
::   cd kestra
::   upload_flows.bat
::
:: The Kestra API accepts both create and update via POST /api/v1/flows.
:: If a flow with the same id + namespace already exists it is updated in-place.
:: ==============================================================================

setlocal enabledelayedexpansion

set KESTRA_URL=http://localhost:8888
set FLOWS_DIR=%~dp0flows

echo.
echo ============================================================
echo  Uploading Kestra flows to %KESTRA_URL%
echo  Source: %FLOWS_DIR%
echo ============================================================
echo.

:: Check Kestra is reachable before trying to upload (/api/v1/flows/search supports GET)
curl --silent --fail --max-time 5 "%KESTRA_URL%/api/v1/flows/search" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Cannot reach Kestra at %KESTRA_URL%
    echo         Make sure Kestra is running:
    echo           cd kestra
    echo           docker compose up -d
    echo.
    exit /b 1
)

set upload_count=0
set error_count=0

for %%f in ("%FLOWS_DIR%\*.yml") do (
    echo Uploading %%~nxf ...
    curl --silent --show-error --fail ^
         --request POST "%KESTRA_URL%/api/v1/flows" ^
         --header "Content-Type: application/x-yaml" ^
         --data-binary "@%%f"

    if !ERRORLEVEL! equ 0 (
        echo   [OK] %%~nxf
        set /a upload_count+=1
    ) else (
        echo   [FAILED] %%~nxf  ^(see error above^)
        set /a error_count+=1
    )
    echo.
)

echo ============================================================
echo  Done.  Uploaded: %upload_count%   Failed: %error_count%
echo.
echo  Open the Kestra UI to verify:
echo    %KESTRA_URL%
echo ============================================================
echo.

if %error_count% gtr 0 exit /b 1
exit /b 0

@echo off
title LMS QA Automation - Online Public Dashboard (Edufic Digital)
cd /d "%~dp0"

echo ======================================================================
echo    LMS QA AUTOMATION - PUBLIC ONLINE DASHBOARD (EDUFIC DIGITAL)
echo    Public Link: https://lms-qa-eduficdigital.loca.lt
echo ======================================================================
echo.

:: 1. Check if python dashboard is running on port 8080
netstat -ano | findstr :8080 | findstr LISTENING >nul
if errorlevel 1 (
    echo [*] Starting local Web Dashboard server on port 8080...
    if exist ".\.venv\Scripts\python.exe" (
        start "LMS QA Local Server" /min .\.venv\Scripts\python.exe web_dashboard_server.py --port 8080 --no-browser
    ) else (
        start "LMS QA Local Server" /min python web_dashboard_server.py --port 8080 --no-browser
    )
    timeout /t 3 >nul
) else (
    echo [OK] Local Web Dashboard server is already active on port 8080.
)

echo.
echo [*] Generating secure public HTTPS link via LocalTunnel...
echo [*] Your fixed public link will be:
echo     https://lms-qa-eduficdigital.loca.lt
echo ======================================================================
echo.

:: 2. Launch LocalTunnel with fixed subdomain
npx --yes localtunnel --port 8080 --subdomain lms-qa-eduficdigital

pause

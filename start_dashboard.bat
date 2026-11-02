@echo off
title LMS QA Automation Web Dashboard
cd /d "%~dp0"

echo ========================================================
echo    LMS QA Automation Tool - Web Dashboard Launcher
echo ========================================================
echo.

if exist ".\.venv\Scripts\python.exe" (
    echo [*] Starting Web Dashboard using .venv Python 3.12...
    .\.venv\Scripts\python.exe web_dashboard_server.py --port 8080
) else if exist "C:\Users\ashok\AppData\Roaming\uv\python\cpython-3.12.12-windows-x86_64-none\python.exe" (
    echo [*] Starting Web Dashboard using Python 3.12...
    "C:\Users\ashok\AppData\Roaming\uv\python\cpython-3.12.12-windows-x86_64-none\python.exe" web_dashboard_server.py --port 8080
) else (
    echo [*] Trying system python...
    python web_dashboard_server.py --port 8080
)

pause

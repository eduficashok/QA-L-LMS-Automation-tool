#!/bin/bash
# ==============================================================================
#  LMS QA Automation Tool - One-Click Launcher for macOS
#  Designed for Non-Technical Users: Just double-click to run!
# ==============================================================================

# Move to the script's directory
cd "$(dirname "$0")"

echo "======================================================================"
echo "    LMS QA AUTOMATION TOOL - STARTING WEB CONTROL DASHBOARD"
echo "======================================================================"
echo ""

# 1. Check for Python 3 on Mac
if command -v python3 &>/dev/null; then
    PY_CMD="python3"
elif command -v python &>/dev/null; then
    PY_CMD="python"
else
    echo "[!] Error: Python 3 is not installed on this Mac."
    echo "    Please install Python 3 from https://www.python.org/downloads/macos/"
    echo "    or run: brew install python"
    read -p "Press Enter to exit..."
    exit 1
fi

echo "[*] Found Python: $($PY_CMD --version)"

# 2. Setup Virtual Environment if not already present
if [ ! -d ".venv" ]; then
    echo "[*] First-time setup: Creating virtual environment..."
    $PY_CMD -m venv .venv
    echo "[*] Installing required packages (Playwright)..."
    ./.venv/bin/pip install --upgrade pip -q
    ./.venv/bin/pip install -r requirements.txt -q
    echo "[*] Installing browser engine (Chromium)..."
    ./.venv/bin/python -m playwright install chromium
    echo "[✓] Setup completed successfully!"
    echo ""
fi

# 3. Start Web Dashboard Server & Auto-open Browser
echo "[*] Launching LMS QA Automation Web Dashboard..."
echo "[*] Server will start at http://127.0.0.1:8080"
echo "======================================================================"
echo ""

./.venv/bin/python web_dashboard_server.py --port 8080

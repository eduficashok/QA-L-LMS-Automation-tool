$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
py -3 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python setup failed. Install Python 3.12 and reopen PowerShell.' }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& .\.venv\Scripts\python.exe -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw 'Test browser installation failed.' }
Write-Host 'Setup complete. Run: .\.venv\Scripts\python.exe run_tests.py'

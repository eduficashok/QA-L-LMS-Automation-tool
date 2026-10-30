Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path .\.venv\Scripts\python.exe)) { throw 'Run setup.ps1 first.' }
& .\.venv\Scripts\python.exe run_workflow.py --browser msedge
exit $LASTEXITCODE

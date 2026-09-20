$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
& ".\.venv\Scripts\python.exe" ".\factory_agent.py"

$ErrorActionPreference="Stop"
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
if (!(Get-Command python -ErrorAction SilentlyContinue)) { Write-Host "Install Python 3.11+ first." -ForegroundColor Red; exit 1 }
if (!(Test-Path ".\.venv")) { python -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
New-Item -ItemType Directory -Force logs,factory_print | Out-Null
if (!(Test-Path ".\.env")) { Copy-Item config.example.env .env; Write-Host "Created .env - edit it before running." -ForegroundColor Yellow }
Write-Host "Factory Agent installed." -ForegroundColor Green

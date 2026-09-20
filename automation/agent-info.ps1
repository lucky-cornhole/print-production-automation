$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
$V=(Get-Content (Join-Path $Root "VERSION") -Raw).Trim()
$H=(Get-FileHash (Join-Path $Root "factory_agent.py") -Algorithm SHA256).Hash.ToLower()
Write-Host "Lucky Bags Factory Agent"; Write-Host "Version : $V"; Write-Host "SHA256  : $H"

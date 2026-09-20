param([Parameter(Mandatory=$true)][string]$ZipPath,[Parameter(Mandatory=$true)][string]$ExpectedSha256)
$ErrorActionPreference="Stop"
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
$Actual=(Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLower()
if ($Actual -ne $ExpectedSha256.ToLower()) { Write-Host "UPDATE BLOCKED: checksum mismatch." -ForegroundColor Red; exit 1 }
$Tmp=Join-Path $env:TEMP ("LBFactory-"+[guid]::NewGuid()); New-Item -ItemType Directory $Tmp | Out-Null
Expand-Archive $ZipPath $Tmp -Force
$Preserve=@(".env",".venv","factory_print","logs","service-account.json")
Get-ChildItem $Tmp | ForEach-Object { if ($Preserve -notcontains $_.Name) { Copy-Item $_.FullName $Root -Recurse -Force } }
Remove-Item $Tmp -Recurse -Force
Write-Host "Agent update verified and installed." -ForegroundColor Green

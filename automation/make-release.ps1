param([string]$OutputDir=".\dist")
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path; Set-Location $Root
$V=(Get-Content VERSION -Raw).Trim(); New-Item -ItemType Directory -Force $OutputDir | Out-Null
$Zip=Join-Path $OutputDir "LuckyBags-Factory-Agent-v$V.zip"
$Include=@("factory_agent.py","requirements.txt","VERSION","config.example.env","install.ps1","run-agent.ps1","run-once.ps1","install-autostart.ps1","uninstall-autostart.ps1","agent-info.ps1","update-agent.ps1","README.md")
Compress-Archive $Include $Zip -Force
$H=(Get-FileHash $Zip -Algorithm SHA256).Hash.ToLower()
"$H  LuckyBags-Factory-Agent-v$V.zip" | Set-Content (Join-Path $OutputDir "LuckyBags-Factory-Agent-v$V.sha256.txt")
Write-Host "Created $Zip"; Write-Host "SHA256: $H"

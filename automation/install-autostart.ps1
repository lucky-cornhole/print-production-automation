$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
$Task="LuckyBagsFactoryAgent"; $Script=Join-Path $Root "run-agent.ps1"
$Action=New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`""
$Trigger=New-ScheduledTaskTrigger -AtStartup
$Settings=New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
Register-ScheduledTask -TaskName $Task -Action $Action -Trigger $Trigger -Settings $Settings -RunLevel Highest -Force | Out-Null
Write-Host "Installed startup task: $Task" -ForegroundColor Green

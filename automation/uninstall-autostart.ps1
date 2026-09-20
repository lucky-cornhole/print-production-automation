$Task="LuckyBagsFactoryAgent"
if (Get-ScheduledTask -TaskName $Task -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $Task -Confirm:$false }
Write-Host "Factory Agent startup task removed."

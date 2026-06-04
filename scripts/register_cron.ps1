# register_cron.ps1
# Registers the cron_dream.ps1 script into Windows Task Scheduler

$Action = New-ScheduledTaskAction -Execute "Powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File ""$PSScriptRoot\cron_dream.ps1"""
$Trigger = New-ScheduledTaskTrigger -Daily -At 2:00AM
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName "JarvisGBrainDream" -Action $Action -Trigger $Trigger -Principal $Principal -Description "Nightly memory consolidation for Jarvis GBrain"

Write-Output "Successfully registered scheduled task 'JarvisGBrainDream' to run at 2 AM daily."

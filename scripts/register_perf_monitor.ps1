# register_perf_monitor.ps1
# Registers the performance optimizer script to run every 5 minutes in Windows Task Scheduler

$PROJECT = Split-Path $PSScriptRoot -Parent
$scriptPath = "$PSScriptRoot\run_perf_monitor.ps1"

# Remove old task if it exists
Unregister-ScheduledTask -TaskName "JarvisPerfMonitor" -Confirm:$false -ErrorAction SilentlyContinue

$Action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$PSScriptRoot\perf_monitor.vbs`""
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "JarvisPerfMonitor" -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description "Periodic 5-minute PC performance check and optimization for Jarvis"

Write-Output "Successfully registered scheduled task 'JarvisPerfMonitor' to run every 5 minutes."

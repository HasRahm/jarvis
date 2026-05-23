# Run this ONCE to make Jarvis start automatically when you log into Windows.
# After this, double-clicking start_jarvis.ps1 is never needed again.

$taskName   = "JarvisAutoStart"
$scriptPath = "$PSScriptRoot\start_jarvis.ps1"
$pwsh       = (Get-Command pwsh -ErrorAction SilentlyContinue)?.Source ?? "powershell"

# Remove old task if it exists
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action  = New-ScheduledTaskAction -Execute $pwsh -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force

Write-Host ""
Write-Host "Jarvis will now start automatically every time you log in." -ForegroundColor Green
Write-Host "To remove: Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false" -ForegroundColor DarkGray

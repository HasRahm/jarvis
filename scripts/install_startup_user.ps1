# install_startup_user.ps1
# Creates a hidden startup VBScript in the User's Startup folder to run start_jarvis.ps1 on login.
# Does not require admin rights.

$PROJECT = Split-Path $PSScriptRoot -Parent
$scriptPath = Join-Path $PSScriptRoot "start_jarvis.ps1"
$startupFolder = [System.IO.Path]::Combine($env:APPDATA, "Microsoft\Windows\Start Menu\Programs\Startup")
$vbsPath = Join-Path $startupFolder "jarvis_startup.vbs"

$vbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`"", 0, false
"@

$vbsContent | Set-Content -Path $vbsPath -Encoding Ascii
Write-Output "Successfully installed startup script in: $vbsPath"

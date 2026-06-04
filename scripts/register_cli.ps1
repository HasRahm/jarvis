# scripts/register_cli.ps1
# Register Jarvis OS globally in the user's PowerShell Profile

$ErrorActionPreference = "Stop"

function Show-Banner {
    Write-Host ""
    Write-Host "  JARVIS OS - GLOBAL COMMAND REGISTRATION" -ForegroundColor Yellow
    Write-Host "  ---------------------------------------------" -ForegroundColor DarkGray
}

$PSScriptRoot = $PSScriptRoot
if ($null -eq $PSScriptRoot) {
    $PSScriptRoot = Split-Path $MyInvocation.MyCommand.Path -Parent
}
$PROJECT = Split-Path $PSScriptRoot -Parent
$scriptPath = Join-Path $PROJECT "scripts\start_local.ps1"
$hermesScriptPath = Join-Path $PROJECT "scripts\hermes_cli.ps1"

Show-Banner

Write-Host "  Locating your PowerShell Profile..." -ForegroundColor Cyan
$profilePath = $PROFILE

if (-not $profilePath) {
    Write-Error "Could not resolve your PowerShell PROFILE path."
    exit 1
}

# Create profile directory and file if they do not exist
$profileDir = Split-Path $profilePath
if (-not (Test-Path $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    Write-Host "  Created profile directory: $profileDir" -ForegroundColor DarkGray
}

if (-not (Test-Path $profilePath)) {
    New-Item -ItemType File -Path $profilePath -Force | Out-Null
    Write-Host "  Created profile file: $profilePath" -ForegroundColor DarkGray
}

$functionCode = @"

# --- JARVIS AI OS GLOBAL COMMAND ---
function jarvis {
    powershell -ExecutionPolicy Bypass -File "$scriptPath" `$args
}
# -----------------------------------
"@

$hermesFunctionCode = @"

# --- HERMES AI OS GLOBAL COMMAND ---
function hermes {
    powershell -ExecutionPolicy Bypass -File "$hermesScriptPath" `$args
}
# -----------------------------------
"@

# Read profile contents
$profileContent = Get-Content $profilePath -Raw
if ($null -eq $profileContent) { $profileContent = "" }

# Register jarvis
if ($profileContent -like "*JARVIS AI OS GLOBAL*") {
    Write-Host "  Jarvis is already registered in your PowerShell profile." -ForegroundColor Yellow
} else {
    Add-Content -Path $profilePath -Value $functionCode
    Write-Host "  [SUCCESS] Successfully added global 'jarvis' command to your profile!" -ForegroundColor Green
}

# Reload profile content
$profileContent = Get-Content $profilePath -Raw
if ($null -eq $profileContent) { $profileContent = "" }

# Register hermes
if ($profileContent -like "*HERMES AI OS GLOBAL*") {
    Write-Host "  Hermes is already registered in your PowerShell profile." -ForegroundColor Yellow
} else {
    Add-Content -Path $profilePath -Value $hermesFunctionCode
    Write-Host "  [SUCCESS] Successfully added global 'hermes' command to your profile!" -ForegroundColor Green
}

Write-Host ""
Write-Host "  ================================================================" -ForegroundColor Yellow
Write-Host "  ACTION REQUIRED: Load the new profile" -ForegroundColor White
Write-Host "  Please open a new PowerShell window, or reload your profile run:" -ForegroundColor White
Write-Host "    . `$PROFILE" -ForegroundColor Cyan
Write-Host "  ----------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  You can now boot up Jarvis globally from any directory by typing:" -ForegroundColor White
Write-Host "    jarvis" -ForegroundColor Cyan
Write-Host "  And Hermes globally by typing:" -ForegroundColor White
Write-Host "    hermes" -ForegroundColor Cyan
Write-Host "  ================================================================" -ForegroundColor Yellow
Write-Host ""

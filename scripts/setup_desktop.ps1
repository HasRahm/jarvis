# setup_desktop.ps1
# Automates setting up the Electron project environment and copying frontend assets.

param(
    [switch]$Start,
    [switch]$Build
)

$PROJECT = Split-Path $PSScriptRoot -Parent
$desktopDir = Join-Path $PROJECT "desktop"
$phoneSrc = Join-Path $PROJECT "phone"
$phoneDest = Join-Path $desktopDir "phone"

Write-Host ""
Write-Host "  JARVIS DESKTOP COMPILER SETUP" -ForegroundColor Yellow
Write-Host "  ---------------------------------------------" -ForegroundColor DarkGray

# 1. Ensure directories exist and copy assets
Write-Host "[1/3] Copying frontend assets to build workspace..." -ForegroundColor Cyan

if (Test-Path $phoneDest) {
    Remove-Item $phoneDest -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $phoneDest -Force | Out-Null

Copy-Item -Path "$phoneSrc\*" -Destination $phoneDest -Recurse -Force
Write-Host "    Assets copied successfully." -ForegroundColor Green

# 2. Run npm install
Write-Host "[2/3] Installing Electron dependencies..." -ForegroundColor Cyan
Set-Location $desktopDir

# Run npm install
& npm install

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install npm packages."
    exit 1
}
Write-Host "    npm packages installed successfully." -ForegroundColor Green

# 3. Handle action commands
Write-Host "[3/3] Execution actions..." -ForegroundColor Cyan
if ($Start) {
    Write-Host "    Starting Electron app..." -ForegroundColor Yellow
    & npm run start
} elseif ($Build) {
    Write-Host "    Compiling Windows .exe installer..." -ForegroundColor Yellow
    & npm run build
    Write-Host "    Build complete. Installer located at desktop\dist\" -ForegroundColor Green
} else {
    Write-Host "    Workspace ready." -ForegroundColor Green
    Write-Host "    To run app:  cd desktop; npm run start" -ForegroundColor DarkGray
    Write-Host "    To build app: cd desktop; npm run build" -ForegroundColor DarkGray
}
Write-Host ""

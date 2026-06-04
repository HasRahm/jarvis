# scripts/hermes_cli.ps1
$ErrorActionPreference = "Stop"

$PSScriptRoot = $PSScriptRoot
if ($null -eq $PSScriptRoot) {
    $PSScriptRoot = Split-Path $MyInvocation.MyCommand.Path -Parent
}
$PROJECT = Split-Path $PSScriptRoot -Parent

# Store current location and change to project root
$oldLocation = Get-Location
Set-Location -Path $PROJECT

try {
    # Activate virtual environment
    if (Test-Path ".venv\Scripts\Activate.ps1") {
        . ".venv\Scripts\Activate.ps1"
    }

    # Execute hermes CLI runner with original arguments
    .venv\Scripts\python.exe core/hermes/hermes_cli_runner.py $args
} finally {
    # Restore original working directory
    Set-Location -Path $oldLocation
}

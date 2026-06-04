# cron_dream.ps1
# Runs the GBrain dream process to consolidate memory

$GBRAIN_PATH = "$env:USERPROFILE\.bun\bin\gbrain.exe"
if (-Not (Test-Path $GBRAIN_PATH)) {
    # Check if there is a wrapper without .exe
    $GBRAIN_PATH = "$env:USERPROFILE\.bun\bin\gbrain"
    if (-Not (Test-Path $GBRAIN_PATH)) {
        Write-Error "GBrain binary not found at $GBRAIN_PATH"
        exit 1
    }
}

Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Running GBrain night consolidation (dream)..."
& $GBRAIN_PATH dream
Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] GBrain dream completed."

# 10d: Nightly adaptive learning summary
Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Running adaptive learning analysis..."
$VENV_PY = Resolve-Path (Join-Path $PSScriptRoot ".." ".venv" "Scripts" "python.exe") -ErrorAction SilentlyContinue
$PY_CMD = if ($VENV_PY) { $VENV_PY } else { "python" }
try {
    & $PY_CMD (Join-Path $PSScriptRoot "dream_analyze.py")
    Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Adaptive analysis complete."
} catch {
    Write-Warning "[DREAM] dream_analyze.py failed: $_"
}

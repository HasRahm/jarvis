# run_perf_monitor.ps1
# Wrapper script to execute scripts/perf_optimizer.py in the python environment

$PROJECT = Split-Path $PSScriptRoot -Parent
$VENV_PY = Join-Path $PROJECT ".venv\Scripts\python.exe"
$PY = if (Test-Path $VENV_PY) { $VENV_PY } else { "python" }

# Set PYTHONPATH to project root
$env:PYTHONPATH = $PROJECT

& $PY (Join-Path $PSScriptRoot "perf_optimizer.py")

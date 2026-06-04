# Jarvis Disk Cleanup - 4-Stage Intelligent Cleanup
# Usage: pwsh -ExecutionPolicy Bypass -File scripts\cleanup.ps1 [scan|safe|judge|delete <path>]
#   scan   - Stage 1: show disk usage by category (read-only)
#   safe   - Stage 2: dry-run safe cleanup, then ask to confirm actual delete
#   judge  - Stage 3: show items needing judgment with AI suggestions
#   delete - Stage 4: delete a specific path approved from judge output
#   (no arg) - run scan, then ask what to do next

param(
    [Parameter(Position=0)][string]$Command = "menu",
    [Parameter(Position=1)][string]$TargetPath = ""
)

$PROJECT = Split-Path $PSScriptRoot -Parent
$env:PYTHONPATH = $PROJECT
$PY = "py"

# Try to use project venv if available
$venvPy = Join-Path $PROJECT ".venv\Scripts\python.exe"
if (Test-Path $venvPy) { $PY = $venvPy }

function Invoke-Python($Code) {
    & $PY -c $Code
}

function Show-Banner {
    Write-Host ""
    Write-Host "  JARVIS DISK CLEANUP" -ForegroundColor Yellow
    Write-Host "  ---------------------------------------------" -ForegroundColor DarkGray
}

# -- Stage 1: Scan ----------------------------------------------------------
function Invoke-Scan {
    Write-Host ""
    Write-Host "  [1/4] SCANNING DISK USAGE..." -ForegroundColor Cyan
    $json = Invoke-Python 'import json; from tools.disk_cleanup import scan; print(json.dumps(scan()))'
    $data = $json | ConvertFrom-Json
    Write-Host ""
    Write-Host "  Category                     Size" -ForegroundColor White
    Write-Host "  ---------------------------  ----------" -ForegroundColor DarkGray
    Write-Host ('  Windows Temp files           {0,8:F1} MB' -f $data.temp_mb)
    Write-Host ('  Browser / INet cache         {0,8:F1} MB' -f $data.cache_mb)
    Write-Host ('  Windows Update downloads     {0,8:F1} MB' -f $data.win_update_mb)
    Write-Host ('  Jarvis log backups           {0,8:F1} MB' -f $data.jarvis_logs_mb)
    Write-Host "  ---------------------------  ----------" -ForegroundColor DarkGray
    Write-Host ('  SAFE TO AUTO-CLEAN           {0,8:F1} MB' -f $data.total_safe_mb) -ForegroundColor Green
    Write-Host ""
    Write-Host ('  User Downloads folder        {0,8:F1} MB' -f $data.user_downloads_mb) -ForegroundColor DarkCyan
    Write-Host ""
    return $data
}

# -- Stage 2: Safe clean -----------------------------------------------------
function Invoke-SafeClean {
    Write-Host ""
    Write-Host "  [2/4] SAFE CLEAN - DRY RUN..." -ForegroundColor Cyan
    $json = Invoke-Python 'import json; from tools.disk_cleanup import safe_clean; print(json.dumps(safe_clean(dry_run=True)))'
    $dry = $json | ConvertFrom-Json
    Write-Host ""
    Write-Host ('  Would delete: {0} items, free {1:F1} MB' -f $dry.files_deleted, $dry.mb_freed) -ForegroundColor Yellow
    foreach ($t in $dry.targets) {
        Write-Host ('    {0,-55} {1,6:F1} MB' -f ($t.path -replace [regex]::Escape($env:USERPROFILE), '~'), $t.mb) -ForegroundColor DarkGray
    }
    Write-Host ""

    if ($dry.files_deleted -eq 0) {
        Write-Host "  Nothing to clean." -ForegroundColor Green
        return
    }

    $confirm = Read-Host "  Proceed with actual deletion? (yes/no)"
    if ($confirm -eq "yes") {
        Write-Host "  Cleaning..." -ForegroundColor Cyan
        $json2 = Invoke-Python 'import json; from tools.disk_cleanup import safe_clean; print(json.dumps(safe_clean(dry_run=False)))'
        $result = $json2 | ConvertFrom-Json
        Write-Host ('  Done. Freed {0:F1} MB across {1} items.' -f $result.mb_freed, $result.files_deleted) -ForegroundColor Green
    } else {
        Write-Host "  Cancelled." -ForegroundColor DarkGray
    }
}

# -- Stage 3: Judgment scan --------------------------------------------------
function Invoke-JudgeScan {
    Write-Host ""
    Write-Host "  [3/4] JUDGMENT SCAN - asking AI for suggestions..." -ForegroundColor Cyan
    Write-Host "  (This may take a moment while Jarvis consults Gemma)" -ForegroundColor DarkGray
    Write-Host ""
    $json = Invoke-Python 'import json; from tools.disk_cleanup import judgment_scan; print(json.dumps(judgment_scan()))'
    $items = $json | ConvertFrom-Json
    if ($items.Count -eq 0) {
        Write-Host "  No judgment-needed items found. Your disk is tidy!" -ForegroundColor Green
        return @()
    }

    Write-Host ('  Found {0} items needing review:' -f $items.Count) -ForegroundColor Yellow
    Write-Host ""
    $i = 0
    foreach ($item in $items) {
        $i++
        $short = $item.path -replace [regex]::Escape($env:USERPROFILE), '~'
        Write-Host ('  [{0}] {1}' -f $i, $short) -ForegroundColor White
        Write-Host ('       Type: {0}  |  Size: {1} MB  |  Age: {2} days' -f $item.type, $item.size_mb, $item.age_days) -ForegroundColor DarkGray
        Write-Host ('       Reason: {0}' -f $item.reason) -ForegroundColor DarkGray
        Write-Host ('       AI: {0}' -f $item.ai_suggestion) -ForegroundColor DarkCyan
        Write-Host ""
    }
    Write-Host "  To delete an item, run:" -ForegroundColor DarkGray
    Write-Host "    .\scripts\cleanup.ps1 delete `"<path>`"" -ForegroundColor DarkGray
    Write-Host ""
    return $items
}

# -- Stage 4: Delete an approved item ---------------------------------------
function Invoke-DeleteItem($Path) {
    if (-not $Path) {
        Write-Host "  Usage: .\scripts\cleanup.ps1 delete `"<path>`"" -ForegroundColor Red
        return
    }
    Write-Host ""
    Write-Host ('  Deleting: {0}' -f $Path) -ForegroundColor Yellow
    $env:CLEANUP_PATH = $Path
    $json = Invoke-Python 'import json, os; from tools.disk_cleanup import delete_judgment_item; path = os.environ.get("CLEANUP_PATH", ""); print(json.dumps(delete_judgment_item(path)))'
    $result = $json | ConvertFrom-Json
    if ($result.deleted) {
        Write-Host ('  Deleted. Freed {0:F1} MB.' -f $result.mb_freed) -ForegroundColor Green
    } else {
        Write-Host ('  Could not delete: {0}' -f $result.error) -ForegroundColor Red
    }
}

# -- Main -------------------------------------------------------------------
Show-Banner

switch ($Command.ToLower()) {
    "scan"   { Invoke-Scan }
    "safe"   { Invoke-SafeClean }
    "judge"  { Invoke-JudgeScan }
    "delete" { Invoke-DeleteItem $TargetPath }
    default  {
        # Interactive menu
        Invoke-Scan | Out-Null
        Write-Host "  What would you like to do?" -ForegroundColor White
        Write-Host "  [1] Safe auto-clean (temp / cache / log backups)" -ForegroundColor Green
        Write-Host "  [2] Judgment scan (large files, old downloads, stale envs)" -ForegroundColor DarkCyan
        Write-Host "  [3] Both" -ForegroundColor Yellow
        Write-Host "  [q] Quit" -ForegroundColor DarkGray
        Write-Host ""
        $choice = Read-Host "  Enter choice"
        switch ($choice) {
            "1" { Invoke-SafeClean }
            "2" { Invoke-JudgeScan }
            "3" { Invoke-SafeClean; Invoke-JudgeScan }
            default { Write-Host "  Goodbye." -ForegroundColor DarkGray }
        }
    }
}
Write-Host ""

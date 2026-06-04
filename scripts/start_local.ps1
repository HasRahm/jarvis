# scripts/start_local.ps1
$ErrorActionPreference = "Stop"

# Change to project root
Set-Location -Path "$PSScriptRoot\.."

# Activate virtual environment
if (Test-Path ".venv\Scripts\Activate.ps1") {
    . ".venv\Scripts\Activate.ps1"
}

# Load .env variables (ignores inline comments)
if (Test-Path ".env") {
    Get-Content ".env" | Where-Object { $_ -match "^[^#]" -and $_ -match "=" } | ForEach-Object {
        $name, $value = $_.Split('=', 2)
        if ($name -and $value) {
            $n = $name.Trim()
            $v = $value.Split('#')[0].Trim()
            Set-Item -Path "Env:$n" -Value $v -ErrorAction SilentlyContinue
        }
    }
}

# Check for cloudflared
$cloudflaredBin = "cloudflared.exe"
if (-not (Get-Command cloudflared.exe -ErrorAction SilentlyContinue)) {
    if (Test-Path "C:\Program Files (x86)\cloudflared\cloudflared.exe") {
        $cloudflaredBin = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
    } elseif (Test-Path "C:\Program Files\cloudflared\cloudflared.exe") {
        $cloudflaredBin = "C:\Program Files\cloudflared\cloudflared.exe"
    } else {
        Write-Host "Installing cloudflared via winget..."
        winget install Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements
        Write-Host "=================================================================="
        Write-Host "ACTION REQUIRED: Authenticate cloudflared"
        Write-Host "Please run: & `"C:\Program Files (x86)\cloudflared\cloudflared.exe`" login"
        Write-Host "=================================================================="
        exit 1
    }
}

Write-Host "Starting Jarvis OS Services..."

# Graceful shutdown helper — SIGTERM first, force-kill after 8s
function Stop-Gracefully {
    param([System.Diagnostics.Process]$proc, [string]$name = "process")
    if ($null -eq $proc -or $proc.HasExited) { return }
    Write-Host "  Stopping $name (pid $($proc.Id))..."
    try { $proc.CloseMainWindow() | Out-Null } catch {}
    if (-not $proc.WaitForExit(8000)) {
        Write-Warning "  $name did not exit gracefully — force killing."
        try { $proc.Kill() } catch {}
    }
}

# Cleanup old logs (best-effort)
"hermes.log","hermes_err.log","tunnel.log","tunnel_err.log","watcher.log","watcher_err.log" | ForEach-Object {
    try { "" | Set-Content $_ -ErrorAction SilentlyContinue } catch {}
}

# 1. Start Hermes Server (with restart-on-failure up to 3 attempts)
$hermesProc = $null
$hermesStarted = $false
for ($attempt = 1; $attempt -le 3; $attempt++) {
    Write-Host "Starting Hermes WebSocket server on port 9000 (attempt $attempt/3)..."
    $hermesProc = Start-Process -PassThru -NoNewWindow -FilePath "uvicorn" `
        -ArgumentList "core.hermes.server:app","--host","0.0.0.0","--port","9000" `
        -RedirectStandardOutput "hermes.log" -RedirectStandardError "hermes_err.log"

    # Health-check wait — poll /health every 2s for up to 30s
    $ready = $false
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep 2
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:9000/health" -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
            if ($r.StatusCode -eq 200) { $ready = $true; break }
        } catch {}
    }

    if ($ready) {
        Write-Host "[OK] Hermes is ready on port 9000."
        $hermesStarted = $true
        break
    } else {
        Write-Warning "[WARN] Hermes did not become healthy (attempt $attempt). Retrying..."
        Stop-Gracefully $hermesProc "hermes"
        Start-Sleep 2
    }
}

if (-not $hermesStarted) {
    Write-Error "[ERROR] Hermes failed to start after 3 attempts. Check hermes_err.log."
    exit 1
}

# 2. Start Cloudflare Tunnel
Write-Host "Starting Cloudflare Tunnel to expose port 9000..."
$tunnelProc = Start-Process -PassThru -NoNewWindow -FilePath $cloudflaredBin `
    -ArgumentList "tunnel","--url","http://localhost:9000" `
    -RedirectStandardOutput "tunnel.log" -RedirectStandardError "tunnel_err.log"

Start-Sleep 3
Write-Host "[INFO] Tunnel URL will appear in tunnel_err.log. Run: Get-Content tunnel_err.log | Select-String trycloudflare"

# 3. Start Sync Watcher
Write-Host "Starting Sync Watcher heartbeat..."
$watcherProc = Start-Process -PassThru -NoNewWindow -FilePath "python" `
    -ArgumentList "core/sync/watcher.py" `
    -RedirectStandardOutput "watcher.log" -RedirectStandardError "watcher_err.log"

# 3.5 Start Messaging Bot Bridge
Write-Host "Starting Secure Messaging Bot Bridge..."
$bridgeProc = Start-Process -PassThru -NoNewWindow -FilePath "python" `
    -ArgumentList "core/hermes/bridge.py" `
    -RedirectStandardOutput "bridge.log" -RedirectStandardError "bridge_err.log"

Write-Host "Services started. Logs: hermes.log, tunnel.log, watcher.log, bridge.log"
Write-Host "Starting Jarvis OS Core Loop (Press Ctrl+C to stop all services)..."
Write-Host "-----------------------------------"

try {
    # 4. Start Core Loop (foreground)
    python core/gemma4_loop.py
} finally {
    Write-Host "`nShutting down Jarvis OS services gracefully..."
    Stop-Gracefully $hermesProc  "hermes"
    Stop-Gracefully $tunnelProc  "cloudflared"
    Stop-Gracefully $watcherProc "watcher"
    Stop-Gracefully $bridgeProc  "bridge"
    Write-Host "All services stopped."
}

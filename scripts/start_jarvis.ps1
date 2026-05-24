# ─────────────────────────────────────────────────────────────────────────────
# Jarvis Startup Script
# Starts Hermes + Cloudflare Tunnel, publishes the live URL to GitHub Gist
# so your phone auto-discovers it with no manual config.
#
# Gist: https://gist.github.com/HasRahm/e99532bb52fd6b67e77f759d9921d5d8
# ─────────────────────────────────────────────────────────────────────────────

$GIST_ID       = "e99532bb52fd6b67e77f759d9921d5d8"
$PROJECT       = "C:\Users\hasin\jarvis"
# GH_TOKEN is set as a persistent Windows user environment variable (never in source).
# If missing, Gist updates are skipped — tunnel still works, phone just keeps old URL.
$PYTHON        = "C:\Users\hasin\AppData\Local\Programs\Python\Python313\Scripts\uvicorn.exe"
$CLOUDFLARED   = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$HERMES_PORT   = 9000
# Published to Gist so phone/HUD auto-connect with zero manual config.
$HERMES_SECRET = if ($env:HERMES_SECRET) { $env:HERMES_SECRET } else { "jarvis_hermes_2026" }

Set-Location $PROJECT

# ── 1. Kill anything already on port 9000 ────────────────────────────────────
$old = Get-NetTCPConnection -LocalPort $HERMES_PORT -ErrorAction SilentlyContinue
if ($old) {
    Stop-Process -Id ($old | Select-Object -First 1).OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep 1
}

# ── 2. Start Hermes in a hidden background window ────────────────────────────
Write-Host "[1/4] Starting Hermes on port $HERMES_PORT..." -ForegroundColor Cyan
$hermes = Start-Process $PYTHON `
    -ArgumentList "core.hermes.server:app --host 0.0.0.0 --port $HERMES_PORT" `
    -WorkingDirectory $PROJECT `
    -WindowStyle Hidden -PassThru

# Wait for Hermes to be ready (poll /health)
$ready = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep 2
    try {
        $r = Invoke-WebRequest "http://localhost:$HERMES_PORT/health" -UseBasicParsing -TimeoutSec 1
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
}
if (-not $ready) { Write-Error "Hermes failed to start."; exit 1 }
Write-Host "    Hermes is ready." -ForegroundColor Green

# ── 3. Start Cloudflare Tunnel and capture the public URL ────────────────────
Write-Host "[2/4] Starting Cloudflare Tunnel..." -ForegroundColor Cyan

# cloudflared writes the URL to stderr — capture it via a temp file
$cfLog  = [System.IO.Path]::GetTempFileName()
$cfProc = Start-Process $CLOUDFLARED `
    -ArgumentList "tunnel --url http://localhost:$HERMES_PORT" `
    -RedirectStandardError $cfLog `
    -WindowStyle Hidden -PassThru

# Poll the log until we see the trycloudflare.com URL (up to 30s)
$tunnelUrl = ""
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep 1
    if (Test-Path $cfLog) {
        $content = Get-Content $cfLog -Raw -ErrorAction SilentlyContinue
        if ($content -match 'https://[a-z0-9\-]+\.trycloudflare\.com') {
            $tunnelUrl = $matches[0]
            break
        }
    }
}
Remove-Item $cfLog -Force -ErrorAction SilentlyContinue

if (-not $tunnelUrl) {
    Write-Warning "Could not detect tunnel URL. Your phone will need manual setup."
} else {
    Write-Host "    Tunnel live: $tunnelUrl" -ForegroundColor Green
}

# ── 4. Publish URL to GitHub Gist so phone auto-discovers it ─────────────────
Write-Host "[3/4] Publishing URL to discovery Gist..." -ForegroundColor Cyan
if ($tunnelUrl) {
    $payload = @{
        url     = $tunnelUrl
        token   = $HERMES_SECRET
        updated = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
        status  = "online"
    } | ConvertTo-Json -Compress

    # Write to temp file and update gist
    $tmp = [System.IO.Path]::GetTempFileName() + ".json"
    $payload | Set-Content $tmp -Encoding UTF8
    Rename-Item $tmp (Join-Path (Split-Path $tmp) "jarvis-url.json")
    $tmp = Join-Path (Split-Path $tmp) "jarvis-url.json"

    try {
        & gh gist edit $GIST_ID $tmp 2>&1 | Out-Null
        Write-Host "    Gist updated — phone will auto-connect." -ForegroundColor Green
    } catch {
        Write-Warning "Gist update failed: $_"
    }
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
}

# ── 5. Done ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[4/4] Jarvis is live." -ForegroundColor Green
if ($tunnelUrl) {
    Write-Host "    Public URL : $tunnelUrl" -ForegroundColor Yellow
}
Write-Host "    Local URL  : http://localhost:$HERMES_PORT" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C to stop everything." -ForegroundColor DarkGray

# Keep script alive — kill children on exit
try {
    Wait-Process -Id $hermes.Id
} finally {
    Write-Host "`nShutting down..." -ForegroundColor DarkGray
    Stop-Process -Id $hermes.Id  -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $cfProc.Id  -Force -ErrorAction SilentlyContinue

    # Mark offline in Gist
    $offlinePayload = '{"url":"","token":"","updated":"' + (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ") + '","status":"offline"}'
    $tmp = Join-Path $env:TEMP "jarvis-url.json"
    $offlinePayload | Set-Content $tmp -Encoding UTF8
    gh gist edit $GIST_ID $tmp 2>&1 | Out-Null
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    Write-Host "Jarvis stopped. Gist marked offline." -ForegroundColor DarkGray
}

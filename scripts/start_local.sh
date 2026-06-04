#!/usr/bin/env bash
set -e

# Change to the project root
cd "$(dirname "$0")/.."

# Activate venv
if [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
else
    source .venv/bin/activate
fi

# Load env variables
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Locate cloudflared or install it
CLOUDFLARED_BIN="cloudflared"
if command -v cloudflared >/dev/null 2>&1; then
    CLOUDFLARED_BIN="cloudflared"
elif [ -f "C:/Program Files (x86)/cloudflared/cloudflared.exe" ]; then
    CLOUDFLARED_BIN="C:/Program Files (x86)/cloudflared/cloudflared.exe"
elif [ -f "C:/Program Files/cloudflared/cloudflared.exe" ]; then
    CLOUDFLARED_BIN="C:/Program Files/cloudflared/cloudflared.exe"
elif [ -f "/mnt/c/Program Files (x86)/cloudflared/cloudflared.exe" ]; then
    CLOUDFLARED_BIN="/mnt/c/Program Files (x86)/cloudflared/cloudflared.exe"
elif [ -f "/mnt/c/Program Files/cloudflared/cloudflared.exe" ]; then
    CLOUDFLARED_BIN="/mnt/c/Program Files/cloudflared/cloudflared.exe"
else
    echo "Installing cloudflared via winget..."
    powershell.exe -Command "winget install Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements"
    
    echo "=================================================================="
    echo "ACTION REQUIRED: Authenticate cloudflared"
    echo "Please run: '& \"C:\Program Files (x86)\cloudflared\cloudflared.exe\" login'"
    echo "Then run: '& \"C:\Program Files (x86)\cloudflared\cloudflared.exe\" tunnel create jarvis'"
    echo "Finally, map the tunnel: '& \"C:\Program Files (x86)\cloudflared\cloudflared.exe\" tunnel route dns jarvis your-domain.com'"
    echo "And add the URL to .env as CLOUDFLARE_TUNNEL_URL"
    echo "=================================================================="
    exit 1
fi

echo "Starting Jarvis OS Services..."

# 1. Start Hermes Server (Background)
echo "Starting Hermes WebSocket server on port 8000..."
uvicorn core.hermes.server:app --host 0.0.0.0 --port 8000 --reload > hermes.log 2>&1 &
HERMES_PID=$!

# 2. Start Cloudflare Tunnel (Background)
echo "Starting Cloudflare Tunnel to expose port 8000..."
# If user set up a named tunnel properly, they usually run 'cloudflared tunnel run jarvis'
# But for Quick Tunnel (no domain required), this command works automatically:
"$CLOUDFLARED_BIN" tunnel --url http://localhost:8000 > tunnel.log 2>&1 &
TUNNEL_PID=$!

# 3. Start Sync Watcher (Background)
echo "Starting Sync Watcher heartbeat..."
python core/sync/watcher.py > watcher.log 2>&1 &
WATCHER_PID=$!

# Ensure we cleanup all background jobs when we exit the shell
trap "echo 'Shutting down services...'; kill $HERMES_PID $TUNNEL_PID $WATCHER_PID 2>/dev/null" EXIT

echo "Services started in background. Logs: hermes.log, tunnel.log, watcher.log"
echo "Starting Jarvis OS Core Loop..."
echo "-----------------------------------"
# 4. Start Core Loop (Foreground)
python core/gemma4_loop.py

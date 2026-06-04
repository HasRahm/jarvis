#!/usr/bin/env bash
# deploy_linux.sh — Idempotent Jarvis production deployment for Ubuntu/Debian VPS
# Usage: sudo bash scripts/deploy_linux.sh
# Run from the jarvis project root.
set -euo pipefail

INSTALL_DIR="/opt/jarvis"
SERVICE_USER="jarvis"
LOG_DIR="$INSTALL_DIR/logs"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "[1/7] Creating system user '$SERVICE_USER' (if not exists)..."
id "$SERVICE_USER" &>/dev/null || useradd --system --shell /usr/sbin/nologin --home "$INSTALL_DIR" "$SERVICE_USER"

echo "[2/7] Syncing project files to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
      --exclude='workspaces/' --exclude='.git/' \
      "$PROJECT_ROOT/" "$INSTALL_DIR/"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

echo "[3/7] Installing Python dependencies..."
if [ ! -d "$INSTALL_DIR/.venv" ]; then
    python3 -m venv "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/.venv"

echo "[4/7] Creating log directory..."
mkdir -p "$LOG_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"

echo "[5/7] Installing systemd service units..."
cp "$SCRIPT_DIR/jarvis.service"         /etc/systemd/system/jarvis.service
cp "$SCRIPT_DIR/jarvis-watcher.service" /etc/systemd/system/jarvis-watcher.service
systemctl daemon-reload

echo "[6/7] Enabling and starting services..."
systemctl enable jarvis.service jarvis-watcher.service
systemctl restart jarvis.service
systemctl restart jarvis-watcher.service

echo "[7/7] Verifying health endpoint..."
sleep 3
if curl -sf http://localhost:9000/health | grep -q '"ok"'; then
    echo "[OK] Jarvis Hermes is healthy on port 9000."
else
    echo "[WARN] Health check failed — check logs at $LOG_DIR/hermes.log"
    journalctl -u jarvis.service --no-pager -n 30
    exit 1
fi

echo ""
echo "=== Jarvis deployed successfully ==="
echo "  Service:  systemctl status jarvis.service"
echo "  Logs:     tail -f $LOG_DIR/hermes.log"
echo "  Restart:  systemctl restart jarvis.service"
echo ""
echo "Next: set up a named Cloudflare tunnel for a stable domain:"
echo "  cloudflared tunnel login"
echo "  cloudflared tunnel create jarvis"
echo "  cloudflared tunnel route dns jarvis your-subdomain.your-domain.com"
echo "  cloudflared tunnel run jarvis"

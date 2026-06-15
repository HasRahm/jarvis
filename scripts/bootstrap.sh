#!/usr/bin/env bash
# bootstrap.sh — One-time setup for Jarvis on Windows (Git Bash) or Linux/macOS.
# Usage: bash scripts/bootstrap.sh
set -e

echo "Bootstrapping Jarvis..."

# ---------------------------------------------------------------------------
# 1. Install Bun (used to run GBrain)
# ---------------------------------------------------------------------------
echo "[1/5] Installing Bun..."
if command -v bun &> /dev/null; then
    echo "  Bun already installed: $(bun --version)"
else
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || -n "$WINDIR" ]]; then
        powershell.exe -Command "Set-ExecutionPolicy RemoteSigned -Scope CurrentUser ; irm bun.sh/install.ps1 | iex"
    else
        curl -fsSL https://bun.sh/install | bash
    fi
    export PATH="$HOME/.bun/bin:$PATH"
    if ! command -v bun &> /dev/null; then
        echo "ERROR: Bun installation failed. Install manually: https://bun.sh"
        exit 1
    fi
    echo "  Bun installed: $(bun --version)"
fi

# ---------------------------------------------------------------------------
# 2. Clone and install GBrain (must live OUTSIDE the Jarvis repo)
# ---------------------------------------------------------------------------
echo "[2/5] Setting up GBrain..."
GBRAIN_DIR="${JARVIS_GBRAIN_DIR:-$HOME/tools/gbrain}"
if [ ! -d "$GBRAIN_DIR" ]; then
    echo "  Cloning GBrain to $GBRAIN_DIR..."
    mkdir -p "$(dirname "$GBRAIN_DIR")"
    git clone https://github.com/garrytan/gbrain "$GBRAIN_DIR"
fi
cd "$GBRAIN_DIR"
bun install
bun link
cd - > /dev/null
echo "  GBrain ready at $GBRAIN_DIR"

# ---------------------------------------------------------------------------
# 3. Create Python virtual environment
# ---------------------------------------------------------------------------
echo "[3/5] Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

if [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate   # Windows Git Bash
else
    source .venv/bin/activate       # Linux / macOS
fi

# ---------------------------------------------------------------------------
# 4. Install Python dependencies
# ---------------------------------------------------------------------------
echo "[4/5] Installing Python dependencies..."
pip install --upgrade pip --quiet
pip install --quiet -r requirements.txt
pip install --quiet pytesseract mss playwright

# ---------------------------------------------------------------------------
# 5. Install Playwright Chromium browser & verify Tesseract
# ---------------------------------------------------------------------------
echo "[5/5] Installing Playwright Chromium and verifying Tesseract..."
playwright install chromium
python -c "import pytesseract; print('Tesseract Version:', pytesseract.get_tesseract_version())"

echo ""
echo "=== Bootstrap complete ==="
echo "Next steps:"
echo "  1. Copy .env.example to .env and fill in your API keys"
echo "  2. Launch Chrome/Edge with Remote Debugging enabled (for Phase 20 CDP web content reading):"
echo "     Windows: start chrome --remote-debugging-port=9222"
echo "     macOS:   /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222"
echo "     Linux:   google-chrome --remote-debugging-port=9222"
echo "  3. Run: powershell -ExecutionPolicy Bypass -File scripts/start_local.ps1"
echo "     (Windows) or: uvicorn core.hermes.server:app --port 9000"
echo "  4. Open https://<tunnel-url>/phone on your phone"


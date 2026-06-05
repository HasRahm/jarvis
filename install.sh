#!/usr/bin/env bash
# jarvis.sh — One-Command Install for Jarvis AI OS
# Usage: curl -sSL https://raw.githubusercontent.com/HasRahm/jarvis/main/install.sh | bash

set -e

echo "==========================================================="
echo "  Jarvis AI OS - One-Command Installer"
echo "==========================================================="
echo ""

# 1. Determine Installation Directory
INSTALL_DIR="${JARVIS_DIR:-$HOME/jarvis}"
if [ -d "$INSTALL_DIR" ]; then
    echo "Directory $INSTALL_DIR already exists."
    echo "Please remove it or set JARVIS_DIR to a different path."
    exit 1
fi

# 2. Check Dependencies
echo "Checking prerequisites..."
for req in git curl python3; do
    if ! command -v $req &> /dev/null; then
        echo "ERROR: $req is required but not installed."
        exit 1
    fi
done

# 3. Install Ollama if missing
if ! command -v ollama &> /dev/null; then
    echo "Installing Ollama..."
    if [[ "$OSTYPE" == "darwin"* || "$OSTYPE" == "linux-gnu"* ]]; then
        curl -fsSL https://ollama.com/install.sh | sh
    else
        echo "Please install Ollama manually for your OS: https://ollama.com/download"
        echo "Then re-run this script."
        exit 1
    fi
fi

# 4. Clone Repository
echo "Cloning Jarvis repository to $INSTALL_DIR..."
git clone https://github.com/HasRahm/jarvis.git "$INSTALL_DIR"
cd "$INSTALL_DIR"

# 5. Run Bootstrap (Bun, GBrain, Python venv, Playwright)
echo "Running bootstrap script..."
bash scripts/bootstrap.sh

# 6. Pull Local Model
echo "Pulling local model (gemma4:31b-cloud) via Ollama..."
# Ensure Ollama server is running in background if not already
if ! curl -s http://localhost:11434/api/tags > /dev/null; then
    echo "Starting Ollama server in background..."
    ollama serve > /dev/null 2>&1 &
    sleep 5
fi
ollama pull gemma4:31b-cloud || echo "WARNING: Failed to pull gemma4:31b-cloud. You may need to run 'ollama pull gemma4:31b-cloud' manually."

# 7. Configure Environment
echo "Configuring environment variables..."
cp .env.example .env
# Generate a secure Hermes secret
if command -v openssl &> /dev/null; then
    SECRET=$(openssl rand -hex 16)
else
    SECRET=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32 || echo "generate_your_own_secret")
fi

if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/HERMES_SECRET=.*/HERMES_SECRET=$SECRET/" .env
else
    sed -i "s/HERMES_SECRET=.*/HERMES_SECRET=$SECRET/" .env
fi

echo ""
echo "==========================================================="
echo "  Jarvis Installed Successfully!"
echo "==========================================================="
echo "Location: $INSTALL_DIR"
echo "Hermes Secret: $SECRET"
echo ""
echo "Next Steps:"
echo "1. cd $INSTALL_DIR"
echo "2. Edit .env to add your API keys (ANTHROPIC_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY)"
echo "3. Run Jarvis:"
echo "     bash scripts/start_local.sh"
echo "4. Connect your phone:"
echo "     Open the cloudflared URL printed in the terminal on your phone."
echo "     Enter your Hermes Secret to connect."
echo "==========================================================="

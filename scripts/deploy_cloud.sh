#!/usr/bin/env bash
# scripts/deploy_cloud.sh
# Automates the deployment of the OpenClaw and Hermes Agent templates to Render and Railway.

set -e

# Change to the root directory
cd "$(dirname "$0")/.."

# Load environment variables
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

echo "Deploying Phase 3 Cloud Components..."

# 1. Render Deployment (OpenClaw via AlphaClaw template)
echo "Deploying AlphaClaw to Render..."
if command -v render >/dev/null 2>&1; then
    render blueprint apply --url https://github.com/chrysb/alphaclaw
else
    echo "Warning: Render CLI not found. Please install it."
    echo "Fallback: Manually deploy https://github.com/chrysb/alphaclaw on Render."
fi

# 2. Railway Deployment (Hermes Agent)
echo "Deploying Hermes Agent to Railway..."
if command -v railway >/dev/null 2>&1; then
    # Railway CLI doesn't natively deploy a template URL directly without a local repo, 
    # so we clone it into a temp dir and run railway up
    TEMP_DIR=$(mktemp -d)
    git clone https://github.com/praveen-ks-2001/hermes-agent-template "$TEMP_DIR"
    cd "$TEMP_DIR"
    
    # Pass necessary env vars to Railway if they exist in local .env
    if [ -n "$CLOUDFLARE_TUNNEL_URL" ]; then
        railway variables set LOCAL_ENDPOINT="$CLOUDFLARE_TUNNEL_URL"
    fi
    if [ -n "$HERMES_SECRET" ]; then
        railway variables set HERMES_SECRET="$HERMES_SECRET"
    fi

    railway up -d
    cd - > /dev/null
    rm -rf "$TEMP_DIR"
else
    echo "Warning: Railway CLI not found. Please install via 'npm i -g @railway/cli'."
    echo "Fallback: Manually deploy https://github.com/praveen-ks-2001/hermes-agent-template on Railway."
fi

echo "Cloud deployments initiated!"
echo "IMPORTANT: Update OPENCLAW_URL in .env once Render provisions the domain."

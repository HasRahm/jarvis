import sys
from core.trace import trace as _jtrace
import os
import time
import requests
import logging
from dotenv import load_dotenv

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(project_root, ".env"))

from core.logging_config import configure_logging
configure_logging("watcher")
logger = logging.getLogger("Watcher")

OPENCLAW_URL = os.getenv("OPENCLAW_URL")
LOCAL_HEALTH_URL = "http://localhost:9000/health"
HERMES_SECRET = os.getenv("HERMES_SECRET", "default_secret")

def is_local_online():
    try:
        resp = requests.get(LOCAL_HEALTH_URL, timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        _jtrace(f"[TRACE] core.sync.watcher.is_local_online: except RequestException")
        return False

def ping_cloud():
    _jtrace(f"[TRACE] core.sync.watcher.ping_cloud: enter")
    if not OPENCLAW_URL:
        logger.warning("OPENCLAW_URL not set in .env. Skipping cloud ping.")
        return
        
    try:
        # Ping the cloud deployment to register local fallback priority
        headers = {"Authorization": f"Bearer {HERMES_SECRET}"}
        payload = {
            "status": "online", 
            "tunnel_url": os.getenv("CLOUDFLARE_TUNNEL_URL", "")
        }
        resp = requests.post(f"{OPENCLAW_URL.rstrip('/')}/api/heartbeat", json=payload, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            logger.info("Successfully pinged OpenClaw. Cloud fallback is now asleep.")
        else:
            logger.warning(f"Failed to ping OpenClaw: {resp.status_code} {resp.text}")
    except requests.RequestException as e:
        _jtrace(f"[TRACE] core.sync.watcher.ping_cloud: except {str(e)[:80]}")
        logger.error(f"Error pinging cloud: {e}")

if __name__ == "__main__":
    logger.info("Starting Jarvis Sync Watcher...")
    while True:
        if is_local_online():
            ping_cloud()
        else:
            logger.warning("Local Hermes server is offline. Heartbeat skipped.")
        
        # Ping every 60 seconds
        time.sleep(60)

import sys
from core.trace import trace as _jtrace
import os
import subprocess
import logging
import shutil
from dotenv import load_dotenv

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(project_root, ".env"))

from core.logging_config import configure_logging
configure_logging("migrate")
logger = logging.getLogger("Migrate")

def sync_files():
    """Sync static files/assets from a remote mapped drive to local using robocopy"""
    _jtrace(f"[TRACE] core.sync.migrate.sync_files: enter")
    remote_path = os.getenv("REMOTE_SYNC_PATH")
    local_path = os.path.join(project_root, "data")
    
    if not remote_path:
        logger.info("REMOTE_SYNC_PATH not defined in .env, skipping file sync.")
        return
        
    if not os.path.exists(local_path):
        os.makedirs(local_path)
        
    logger.info(f"Syncing files from {remote_path} to {local_path} via robocopy...")
    try:
        # robocopy returns < 8 for successful copies (1=copied, 2=extra files, 3=both, etc)
        result = subprocess.run(["robocopy", remote_path, local_path, "/MIR", "/Z", "/W:5"], capture_output=True, text=True)
        if result.returncode < 8:
            logger.info("File sync complete.")
        else:
            logger.error(f"Robocopy failed with code {result.returncode}: {result.stdout}")
    except Exception as e:
        _jtrace(f"[TRACE] core.sync.migrate.sync_files: except {str(e)[:80]}")
        logger.error(f"Failed to run robocopy: {e}")

def sync_gbrain():
    """Sync GBrain memory using its native migrate command to prevent PGLite corruption"""
    _jtrace(f"[TRACE] core.sync.migrate.sync_gbrain: enter")
    GBRAIN = shutil.which("gbrain")
    if not GBRAIN:
        if os.name == "nt":
            _possible = os.path.expanduser(r"~\.bun\bin\gbrain.cmd")
            if os.path.exists(_possible):
                GBRAIN = _possible
        else:
            _possible = os.path.expanduser(r"~/.bun/bin/gbrain")
            if os.path.exists(_possible):
                GBRAIN = _possible
                
    if not GBRAIN:
        logger.error("GBrain executable not found. Cannot migrate memory.")
        return
        
    logger.info("Migrating GBrain database to local PGLite...")
    try:
        # `gbrain migrate --to pglite` handles safe database syncing without raw file corruption
        result = subprocess.run([GBRAIN, "migrate", "--to", "pglite"], capture_output=True, text=True, cwd=project_root)
        if result.returncode == 0:
            logger.info("GBrain migration complete.")
        else:
            logger.error(f"GBrain migration failed: {result.stderr or result.stdout}")
    except Exception as e:
        _jtrace(f"[TRACE] core.sync.migrate.sync_gbrain: except {str(e)[:80]}")
        logger.error(f"Error running gbrain migrate: {e}")

if __name__ == "__main__":
    logger.info("Starting Jarvis Sync & Migration...")
    sync_files()
    sync_gbrain()
    logger.info("Sync sequence finished.")

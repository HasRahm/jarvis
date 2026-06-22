import sys
import subprocess
import os

# Dynamically resolve GBrain executable path to avoid hardcoded user profile paths
_GBRAIN_PATH = None
if os.name == "nt":
    _possible_path = os.path.expanduser(r"~\.bun\bin\gbrain.cmd")
    if os.path.isfile(_possible_path):
        _GBRAIN_PATH = _possible_path

if not _GBRAIN_PATH:
    import shutil
    _GBRAIN_PATH = shutil.which("gbrain")

GBRAIN_AVAILABLE = _GBRAIN_PATH is not None and (os.path.isfile(_GBRAIN_PATH) or not os.path.isabs(_GBRAIN_PATH))

def brain_get(slug: str) -> str:
    """Retrieve a page's raw content from memory by exact slug (Phase 25).

    Reads directly from Supabase with a short timeout. Returns "" if absent
    or the store is unavailable. Never raises.
    """
    try:
        from brain.supabase_store import mem_get
        return mem_get(slug) or ""
    except Exception:
        print(f"[TRACE] brain.get.brain_get: except Exception", file=sys.stderr, flush=True)
        return ""

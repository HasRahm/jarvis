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

def brain_write(slug: str, content: str) -> str:
    """Store a note or result in memory for future recall (Phase 25).

    Fire-and-forget: the write is queued to Supabase on a background thread
    and this returns immediately. The agent never waits. Ordering-critical
    internal callers should use brain.supabase_store.mem_upsert (synchronous)
    instead.
    """
    print(f"[TRACE] brain.write.brain_write: enter", file=sys.stderr, flush=True)
    try:
        from brain.supabase_store import enqueue_upsert
        enqueue_upsert(slug, content)
    except Exception as e:
        print(f"[TRACE] brain.write.brain_write: except {str(e)[:80]}", file=sys.stderr, flush=True)
        return f"Error queuing write for slug '{slug}': {e}"
    return f"Queued write to memory under slug '{slug}'."

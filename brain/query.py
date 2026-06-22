import sys
from core.trace import trace as _jtrace
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

# Phase 25: gbrain (Bun) is now an OPTIONAL, best-effort enrichment behind a
# short timeout — never the blocking primary path.
GBRAIN_QUERY_ENABLED = os.environ.get("JARVIS_GBRAIN_QUERY", "1") == "1"
GBRAIN_QUERY_TIMEOUT = 8.0
_NO_MEM = "No relevant memories found."


def _gbrain_enrich(query: str) -> str:
    """Best-effort semantic enrichment via the gbrain (Bun) CLI.

    Runs in a worker thread with a short hard timeout; ANY slowness or crash
    is swallowed and returns "" — the design allows this path to be
    "completely lost" without affecting the agent.
    """
    _jtrace(f"[TRACE] brain.query._gbrain_enrich: enter")
    import concurrent.futures

    def _call():
        _jtrace(f"[TRACE] brain.query._gbrain_enrich._call: enter")
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [_GBRAIN_PATH, "query", query]
        if os.name == "nt" and _GBRAIN_PATH.endswith(".cmd"):
            cmd = ["cmd.exe", "/c"] + cmd
        import tempfile
        with tempfile.TemporaryFile(mode="w+t") as out_f, tempfile.TemporaryFile(mode="w+t") as err_f:
            result = subprocess.run(
                cmd, stdout=out_f, stderr=err_f, stdin=subprocess.DEVNULL,
                cwd=project_root, timeout=GBRAIN_QUERY_TIMEOUT,
            )
            out_f.seek(0)
            data = out_f.read()
        if result.returncode != 0:
            return ""
        data = (data or "").strip()
        return data if data and "No relevant memories" not in data else ""

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_call).result(timeout=GBRAIN_QUERY_TIMEOUT + 2)
    except Exception:
        _jtrace(f"[TRACE] brain.query._gbrain_enrich: except Exception")
        return ""


def brain_query(query: str) -> str:
    """Search memory for relevant context before answering (Phase 25).

    Supabase first (fast, reliable — covers Jarvis's own writes like contracts
    and checkpoints), then OPTIONALLY enriches with gbrain semantic search
    (best-effort, short timeout). Returns the "No relevant memories found."
    sentinel when nothing is found, and never emits the literal word 'error'
    on the happy/empty path (callers gate on those strings).
    """
    # 1. Supabase text search — the reliable primary path.
    _jtrace(f"[TRACE] brain.query.brain_query: enter")
    supa_text = ""
    try:
        from brain.supabase_store import mem_search
        rows = mem_search(query)
        if rows:
            blocks = []
            for r in rows:
                slug = r.get("slug", "")
                content = (r.get("content") or "").strip()
                blocks.append(f"### {slug}\n{content}" if slug else content)
            supa_text = "\n\n".join(b for b in blocks if b)
    except Exception:
        _jtrace(f"[TRACE] brain.query.brain_query: except Exception")
        supa_text = ""

    # 2. Optional gbrain enrichment — best-effort, allowed to be lost.
    gbrain_text = ""
    if (GBRAIN_QUERY_ENABLED and GBRAIN_AVAILABLE
            and os.environ.get("JARVIS_CI") != "true"):
        gbrain_text = _gbrain_enrich(query)

    parts = [t for t in (supa_text, gbrain_text) if t]
    if not parts:
        return _NO_MEM
    return "\n\n".join(parts)

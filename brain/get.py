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
    """Retrieve a page's raw content from GBrain by slug"""
    if not GBRAIN_AVAILABLE:
        return ""
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [_GBRAIN_PATH, "get", slug]
        if os.name == "nt" and _GBRAIN_PATH.endswith(".cmd"):
            cmd = ["cmd.exe", "/c"] + cmd
        
        import tempfile
        with tempfile.TemporaryFile(mode='w+t') as out_f, tempfile.TemporaryFile(mode='w+t') as err_f:
            result = subprocess.run(
                cmd,
                stdout=out_f,
                stderr=err_f,
                stdin=subprocess.DEVNULL,
                cwd=project_root,
                timeout=10
            )
            out_f.seek(0)
            err_f.seek(0)
            stdout_data = out_f.read()
            stderr_data = err_f.read()
            
        if result.returncode != 0:
            if "Page not found" in stderr_data or "page_not_found" in stderr_data:
                return ""
            raise RuntimeError(f"GBrain get error: {stderr_data}")
        return stdout_data.strip()
    except subprocess.TimeoutExpired:
        return ""
    except Exception:
        return ""

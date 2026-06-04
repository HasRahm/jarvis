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

def brain_query(query: str) -> str:
    """Search GBrain memory for relevant context before answering"""
    if not GBRAIN_AVAILABLE:
        return "No relevant memories found. (GBrain not installed)"
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [_GBRAIN_PATH, "query", query]
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
            return f"GBrain query error: {stderr_data}"
        return stdout_data.strip() if stdout_data else "No relevant memories found."
    except subprocess.TimeoutExpired:
        return "No relevant memories found. (GBrain timed out)"
    except Exception as e:
        return f"Error executing GBrain query: {str(e)}"

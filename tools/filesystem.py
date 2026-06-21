import os

# ---------------------------------------------------------------------------
# Optional workspace jail (review finding #3)
# ---------------------------------------------------------------------------
# By default Jarvis is a single-user desktop "control your whole PC" agent, so file access is
# unrestricted. For SaaS / shared / untrusted deployments, set JARVIS_WORKSPACE_JAIL to an absolute
# root path: all reads and writes are then confined to that subtree, and path-traversal escapes
# (e.g. ../../etc/passwd) are refused. Unset → unrestricted (current behaviour, no surprise).


def _jail_root() -> str | None:
    root = os.environ.get("JARVIS_WORKSPACE_JAIL", "").strip()
    return os.path.realpath(root) if root else None


def _check_path_allowed(path: str) -> tuple[bool, str]:
    """When a jail is configured, confirm `path` resolves inside it (blocks .. traversal)."""
    root = _jail_root()
    if not root:
        return True, ""
    resolved = os.path.realpath(os.path.abspath(path))
    # commonpath raises on different drives (Windows) — treat that as outside the jail.
    try:
        inside = os.path.commonpath([resolved, root]) == root
    except ValueError:
        inside = False
    if inside:
        return True, ""
    return False, (f"Refused: '{path}' is outside the workspace jail ({root}). "
                   "Writes/reads are confined to the jail in this deployment.")


def read_file(path: str) -> str:
    """Read the contents of a file at the given path"""
    ok, reason = _check_path_allowed(path)
    if not ok:
        return f"Error reading file {path}: {reason}"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file {path}: {str(e)}"

def write_file(path: str, content: str) -> str:
    """Write content to a file, creating it if it does not exist"""
    ok, reason = _check_path_allowed(path)
    if not ok:
        return f"Error writing to file {path}: {reason}"
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing to file {path}: {str(e)}"

def list_dir(path: str) -> str:
    """List files and directories at a path"""
    ok, reason = _check_path_allowed(path)
    if not ok:
        return f"Error listing directory {path}: {reason}"
    try:
        items = os.listdir(path)
        result = []
        for item in items:
            full_path = os.path.join(path, item)
            is_dir = os.path.isdir(full_path)
            result.append(f"{'[DIR]' if is_dir else '[FILE]'} {item}")
        return "\n".join(result)
    except Exception as e:
        return f"Error listing directory {path}: {str(e)}"

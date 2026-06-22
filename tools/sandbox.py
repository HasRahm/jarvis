"""
tools/sandbox.py — E2B cloud sandbox lifecycle management.

Provides a thin wrapper around the e2b-code-interpreter SDK.
Returns None everywhere when JARVIS_SANDBOX_MODE != "e2b" or JARVIS_CI=true,
so all existing callers that don't use E2B are completely unaffected.

Usage:
    sandbox = create_sandbox(task_id)     # None in local/docker/CI modes
    result  = run_in_sandbox(sandbox, cmd)
    destroy_sandbox(sandbox, task_id)

JARVIS_SANDBOX_MODE values:
    local   — run commands on the host machine (default)
    docker  — run inside the docker-compose sandbox container
    e2b     — run in an ephemeral E2B cloud Linux sandbox
"""
import sys
from core.trace import trace as _jtrace

import os
import logging

logger = logging.getLogger(__name__)

_SANDBOX_MODE = os.environ.get("JARVIS_SANDBOX_MODE", "local")


def create_sandbox(task_id: str) -> object | None:
    """
    Create a fresh E2B sandbox for the given task.

    Returns the sandbox object on success, or None when:
    - JARVIS_SANDBOX_MODE != "e2b"
    - JARVIS_CI=true (test mode — no external calls)
    - e2b_code_interpreter package not installed
    - E2B API call fails (fallback to local gracefully)
    """
    _jtrace(f"[TRACE] tools.sandbox.create_sandbox: enter")
    if _SANDBOX_MODE != "e2b" or os.environ.get("JARVIS_CI") == "true":
        return None

    try:
        from e2b_code_interpreter import Sandbox  # type: ignore
        sbx = Sandbox()
        logger.info(f"[sandbox] E2B sandbox created for task {task_id}: {sbx.sandbox_id}")
        return sbx
    except ImportError:
        _jtrace(f"[TRACE] tools.sandbox.create_sandbox: except ImportError")
        logger.warning("[sandbox] e2b_code_interpreter not installed. Falling back to local execution.")
        return None
    except Exception as e:
        _jtrace(f"[TRACE] tools.sandbox.create_sandbox: except {str(e)[:80]}")
        logger.warning(f"[sandbox] E2B create failed for task {task_id}: {e}. Falling back to local.")
        return None


def destroy_sandbox(sandbox: object | None, task_id: str) -> None:
    """
    Cleanly tear down an E2B sandbox.

    Safe to call with sandbox=None (no-op).
    """
    _jtrace(f"[TRACE] tools.sandbox.destroy_sandbox: enter")
    if sandbox is None:
        return
    try:
        sandbox.kill()
        logger.info(f"[sandbox] E2B sandbox destroyed for task {task_id}")
    except Exception as e:
        _jtrace(f"[TRACE] tools.sandbox.destroy_sandbox: except {str(e)[:80]}")
        logger.warning(f"[sandbox] E2B destroy failed for task {task_id}: {e}")


def run_in_sandbox(sandbox: object | None, command: str, cwd: str = "/home/user") -> str:
    """
    Execute a shell command inside an E2B sandbox.

    Returns combined stdout + stderr on success, or an error string if the
    call fails. Returns empty string when sandbox is None (caller should
    fall through to local execution).
    """
    _jtrace(f"[TRACE] tools.sandbox.run_in_sandbox: enter")
    if sandbox is None:
        return ""
    try:
        result = sandbox.commands.run(command, cwd=cwd)
        return (result.stdout or "") + (result.stderr or "")
    except Exception as e:
        _jtrace(f"[TRACE] tools.sandbox.run_in_sandbox: except {str(e)[:80]}")
        logger.warning(f"[sandbox] E2B command failed: {e}")
        return f"E2B error: {e}"


def write_files_to_sandbox(sandbox: object | None, files: dict, base: str = "/home/user/workspace") -> bool:
    """
    Write a {relative_path: content} mapping into an E2B sandbox under *base*.

    Used by the self-correction spine to push an agent's generated files into the
    sandbox before executing them. Returns True on success, False on any failure
    (including sandbox=None, so the caller can fall back to local checks).
    """
    _jtrace(f"[TRACE] tools.sandbox.write_files_to_sandbox: enter")
    if sandbox is None or not files:
        return False
    try:
        for rel_path, content in files.items():
            dest = f"{base.rstrip('/')}/{rel_path.lstrip('/')}"
            sandbox.files.write(dest, content if isinstance(content, str) else str(content))
        return True
    except Exception as e:
        _jtrace(f"[TRACE] tools.sandbox.write_files_to_sandbox: except {str(e)[:80]}")
        logger.warning(f"[sandbox] E2B file write failed: {e}")
        return False

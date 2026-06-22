"""
core/system/mxc_adapter.py — Microsoft Execution Containers (MXC) sandbox integration.

Provides a wrapper around the Windows 11 MXC CLI / OpenClaw runtime for local agent execution.
Returns None everywhere when JARVIS_SANDBOX_MODE != "mxc", falling back to docker/local.

Usage:
    sandbox = create_sandbox(task_id)
    result  = run_in_sandbox(sandbox, cmd)
    destroy_sandbox(sandbox, task_id)
"""
import sys

import os
import shutil
import subprocess
import logging
import uuid
import json

logger = logging.getLogger(__name__)

_SANDBOX_MODE = os.environ.get("JARVIS_SANDBOX_MODE", "local")


class MXCSandbox:
    def __init__(self, task_id: str, container_id: str):
        self.task_id = task_id
        self.container_id = container_id

    def kill(self):
        try:
            # Command to terminate the MXC container
            subprocess.run(["mxc", "rm", "-f", self.container_id], check=True, capture_output=True, text=True)
            logger.info(f"[mxc_adapter] Terminated MXC container {self.container_id}")
        except subprocess.CalledProcessError as e:
            print(f"[TRACE] core.system.mxc_adapter.MXCSandbox.kill: except {str(e)[:80]}", file=sys.stderr, flush=True)
            logger.error(f"[mxc_adapter] Failed to terminate MXC container: {e.stderr}")
            raise e

    def run(self, command: str, cwd: str = "/workspace") -> dict:
        """Run a command inside the MXC container. Returns a dict mimicking the E2B result object."""
        try:
            # mxc exec syntax
            mxc_cmd = ["mxc", "exec", "--workdir", cwd, self.container_id, "cmd.exe", "/c", command]
            result = subprocess.run(mxc_cmd, capture_output=True, text=True, check=False)
            
            # Mocking the E2B result format for drop-in compatibility
            class ResultDict:
                def __init__(self, stdout, stderr):
                    self.stdout = stdout
                    self.stderr = stderr
            return ResultDict(result.stdout, result.stderr)
        except Exception as e:
            print(f"[TRACE] core.system.mxc_adapter.MXCSandbox.run: except {str(e)[:80]}", file=sys.stderr, flush=True)
            logger.error(f"[mxc_adapter] MXC exec failed: {e}")
            raise e


def create_sandbox(task_id: str) -> object | None:
    """
    Create a fresh MXC container for the given task.
    """
    print(f"[TRACE] core.system.mxc_adapter.create_sandbox: enter", file=sys.stderr, flush=True)
    if _SANDBOX_MODE != "mxc":
        return None

    try:
        # Check if MXC is available
        if shutil.which("mxc") is None:
            logger.warning("[mxc_adapter] 'mxc' CLI not found on PATH. Falling back to local/docker execution.")
            return None

        # Generate a unique container ID based on task
        container_id = f"jarvis-mxc-{task_id[:8]}-{uuid.uuid4().hex[:6]}"
        
        # Build 2026 MXC Container start command with strict policy
        logger.info(f"[mxc_adapter] Creating MXC container {container_id} for task {task_id}...")
        cmd = [
            "mxc", "run", 
            "--name", container_id,
            "--policy", "isolated-strict",
            "--mount", f"type=bind,source={os.getcwd()},target=/workspace",
            "--detach",
            "mcr.microsoft.com/windows/nanoserver:ltsc2026"
        ]
        
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info(f"[mxc_adapter] MXC container {container_id} created successfully.")
        return MXCSandbox(task_id, container_id)
        
    except subprocess.CalledProcessError as e:
        print(f"[TRACE] core.system.mxc_adapter.create_sandbox: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"[mxc_adapter] MXC create failed for task {task_id}: {e.stderr}. Falling back.")
        return None
    except Exception as e:
        print(f"[TRACE] core.system.mxc_adapter.create_sandbox: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"[mxc_adapter] MXC create exception: {e}. Falling back.")
        return None


def destroy_sandbox(sandbox: object | None, task_id: str) -> None:
    """
    Cleanly tear down an MXC container.
    """
    print(f"[TRACE] core.system.mxc_adapter.destroy_sandbox: enter", file=sys.stderr, flush=True)
    if sandbox is None:
        return
    try:
        if hasattr(sandbox, 'kill'):
            sandbox.kill()
        logger.info(f"[mxc_adapter] MXC container destroyed for task {task_id}")
    except Exception as e:
        print(f"[TRACE] core.system.mxc_adapter.destroy_sandbox: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"[mxc_adapter] MXC destroy failed for task {task_id}: {e}")


def run_in_sandbox(sandbox: object | None, command: str, cwd: str = "/workspace") -> str:
    """
    Execute a shell command inside an MXC container.
    """
    print(f"[TRACE] core.system.mxc_adapter.run_in_sandbox: enter", file=sys.stderr, flush=True)
    if sandbox is None:
        return ""
    try:
        if hasattr(sandbox, 'run'):
            result = sandbox.run(command, cwd=cwd)
            return (result.stdout or "") + (result.stderr or "")
        return ""
    except Exception as e:
        print(f"[TRACE] core.system.mxc_adapter.run_in_sandbox: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"[mxc_adapter] MXC command failed: {e}")
        return f"MXC error: {e}"

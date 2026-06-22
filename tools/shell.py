import sys
from core.trace import trace as _jtrace
import subprocess
import os

_SANDBOX_MODE = os.environ.get("JARVIS_SANDBOX_MODE", "local")


def _jailed_local_exec_blocked() -> bool:
    """SaaS / untrusted deployments can forbid raw local shell entirely (review finding #3).

    When JARVIS_WORKSPACE_JAIL is set AND the sandbox mode is the unconfined 'local', refuse
    host shell execution — such deployments must run commands inside the e2b/docker sandbox
    instead. Self-hosted desktop (no jail) is unaffected: arbitrary local execution is the
    intended capability.
    """
    return bool(os.environ.get("JARVIS_WORKSPACE_JAIL", "").strip()) and _SANDBOX_MODE == "local"


def run_command(command: str, cwd: str = None, sandbox=None) -> str:
    """Run a shell command and return stdout and stderr.

    sandbox: optional E2B sandbox object (Phase 13).  When provided and
             JARVIS_SANDBOX_MODE=e2b, the command is executed inside the
             cloud sandbox instead of locally.  Existing callers that omit
             sandbox= are completely unaffected.
    """
    # Fail closed for jailed deployments that haven't wired a real sandbox.
    _jtrace(f"[TRACE] tools.shell.run_command: enter")
    if _jailed_local_exec_blocked() and not (sandbox and _SANDBOX_MODE == "e2b"):
        return ("ERROR: raw local shell execution is disabled in this deployment "
                "(JARVIS_WORKSPACE_JAIL is set). Configure JARVIS_SANDBOX_MODE=e2b or =docker "
                "to run commands inside a sandbox.")
    try:
        # Phase 13: E2B cloud sandbox execution path
        if _SANDBOX_MODE == "e2b" and sandbox is not None:
            from tools.sandbox import run_in_sandbox
            return run_in_sandbox(sandbox, command, cwd or "/home/user")

        # Redirect to docker if sandbox is requested and we are NOT already inside the container
        if _SANDBOX_MODE == "docker" and not os.path.exists('/.dockerenv'):
            # Translate host path to container path
            if cwd:
                cwd = cwd.replace('\\', '/')
                _root_wsl = os.environ.get("JARVIS_WSL_PROJECT_ROOT", "")
                _root_win = os.environ.get("JARVIS_WIN_PROJECT_ROOT", "")
                if _root_wsl and cwd.startswith(_root_wsl):
                    container_cwd = cwd.replace(_root_wsl, '/workspace', 1)
                elif _root_win and cwd.startswith(_root_win):
                    container_cwd = cwd.replace(_root_win, '/workspace', 1)
                else:
                    container_cwd = cwd
            else:
                container_cwd = "/workspace"
            
            # Execute inside the running docker compose sandbox container
            docker_cmd = [
                "docker", "compose", "exec", "-T",
                "-w", container_cwd,
                "sandbox", "sh", "-c", command
            ]
            
            from core.system.safety_monitor import SafetyMonitor
            result = SafetyMonitor.run_monitored(
                docker_cmd,
                shell=False
            )
        else:
            from core.system.safety_monitor import SafetyMonitor
            result = SafetyMonitor.run_monitored(
                command,
                shell=True,
                cwd=cwd
            )
        
        output = ""
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"
            
        output += f"Exit Code: {result.returncode}"
        
        return output.strip() if output else "Command executed successfully with no output."
    except Exception as e:
        _jtrace(f"[TRACE] tools.shell.run_command: except {str(e)[:80]}")
        return f"Error executing command: {str(e)}"


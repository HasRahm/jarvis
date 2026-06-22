import os
import re
import subprocess
import sys
from core.trace import trace as _jtrace
import psutil
from typing import Callable, List, Optional, Tuple

class HarnessRuntimeError(Exception):
    """Exception raised when a critical environment error requires human escalation."""
    def __init__(self, message: str, category: str):
        super().__init__(message)
        self.category = category


class SafetyMonitor:
    # Error classification regexes
    PATTERNS_AUTO_RESOLVE = {
        "port_conflict": r"(?:Address already in use|port (?:\d+ )?already in use|EADDRINUSE|address bound)",
        "cache_corruption": r"(?:npm ERR! cache clean|pip check.*failed|SHA.*integrity checksum failed|failed to verify integrity)",
        "playwright_crash": r"(?:browser.*context.*closed|Playwright.*crash|chromium.*target closed|BrowserType\.launch)",
    }

    PATTERNS_ESCALATE = {
        "git_auth": r"(?:git.*Authentication failed|fatal: Could not read from remote repository|Permission denied \(publickey\))",
        "db_lock": r"(?:database.*locked|lock.*held.*external.*process|deadlock detected|relation.*lock)",
        "docker_down": r"(?:Cannot connect to the Docker daemon|docker daemon is not running)",
        "permission_denied": r"(?:Permission denied|EACCES|Operation not permitted)",
    }

    @classmethod
    def scan_stream(cls, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Scans a stream text segment against error regexes, returning (category, type)."""
        # Check ESCALATE first to prioritize human attention
        _jtrace(f"[TRACE] core.system.safety_monitor.SafetyMonitor.scan_stream: enter")
        for cat, pat in cls.PATTERNS_ESCALATE.items():
            if re.search(pat, text, re.IGNORECASE):
                # Custom safety check for permission denied outside /workspace/
                if cat == "permission_denied":
                    # Check if the text references a path outside /workspace/
                    workspace_match = re.search(r"(/[\w.-]+)+", text)
                    if workspace_match:
                        path = workspace_match.group(0)
                        if not path.startswith("/workspace") and not path.startswith("/tmp"):
                            return "escalate", cat
                    continue
                return "escalate", cat

        for cat, pat in cls.PATTERNS_AUTO_RESOLVE.items():
            if re.search(pat, text, re.IGNORECASE):
                return "auto_resolve", cat

        return None, None

    @classmethod
    def run_monitored(
        cls, 
        cmd: List[str] or str, 
        cwd: Optional[str] = None, 
        env: Optional[dict] = None,
        shell: bool = False,
        timeout: float = 60.0
    ) -> subprocess.CompletedProcess:
        """
        Executes a terminal command with dynamic real-time stream scanning.
        Automatically resolves known port, cache, and browser issues, and escalates database/git blockages.
        """
        _jtrace(f"[TRACE] core.system.safety_monitor.SafetyMonitor.run_monitored: enter")
        cmd_str = cmd if isinstance(cmd, str) else ' '.join(cmd)
        print(f"[SAFETY MONITOR] Launching command: {cmd_str}")
        
        # Merge environments
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        # Launch command with stdout/stderr combined or piped
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=run_env,
            shell=shell,
            text=True
        )

        import queue
        from threading import Thread
        import time

        stdout_accum = []
        stderr_accum = []

        stdout_queue = queue.Queue()
        stderr_queue = queue.Queue()

        def reader_thread(stream, q):
            try:
                for line in iter(stream.readline, ''):
                    q.put(line)
            except Exception:
                _jtrace(f"[TRACE] core.system.safety_monitor.SafetyMonitor.run_monitored.reader_thread: except Exception")
                pass
            finally:
                try:
                    stream.close()
                except Exception:
                    _jtrace(f"[TRACE] core.system.safety_monitor.SafetyMonitor.run_monitored.reader_thread: except Exception")
                    pass

        def _attach_readers(proc):
            """Start fresh reader threads bound to a (possibly retried) process."""
            _jtrace(f"[TRACE] core.system.safety_monitor.SafetyMonitor.run_monitored._attach_readers: enter")
            t_out = Thread(target=reader_thread, args=(proc.stdout, stdout_queue), daemon=True)
            t_err = Thread(target=reader_thread, args=(proc.stderr, stderr_queue), daemon=True)
            t_out.start()
            t_err.start()
            return t_out, t_err

        _attach_readers(process)

        start = time.monotonic()
        timed_out = False

        # Poll outputs in real time
        try:
            while process.poll() is None or not stdout_queue.empty() or not stderr_queue.empty():
                # Enforce the wall-clock timeout — a silently-hung process must not run forever.
                if timeout and (time.monotonic() - start) > timeout:
                    timed_out = True
                    break

                has_data = False

                # Drain stdout
                while True:
                    try:
                        line = stdout_queue.get_nowait()
                        stdout_accum.append(line)
                        has_data = True

                        sys.stdout.write(f"    [cmd stdout] {line}")
                        sys.stdout.flush()

                        action, error_type = cls.scan_stream(line)
                        if action:
                            retry = cls._handle_action(action, error_type, line, process, cmd, cwd, env, shell)
                            if retry is not None:
                                # Swap the retried process back into the loop and re-attach
                                # readers, so its output is monitored and its result returned —
                                # instead of being abandoned in the background.
                                process = retry
                                _attach_readers(process)
                                start = time.monotonic()   # reset the clock for the retry
                    except queue.Empty:
                        break

                # Drain stderr
                while True:
                    try:
                        line = stderr_queue.get_nowait()
                        stderr_accum.append(line)
                        has_data = True

                        sys.stderr.write(f"    [cmd stderr] {line}")
                        sys.stderr.flush()

                        action, error_type = cls.scan_stream(line)
                        if action:
                            retry = cls._handle_action(action, error_type, line, process, cmd, cwd, env, shell)
                            if retry is not None:
                                process = retry
                                _attach_readers(process)
                                start = time.monotonic()
                    except queue.Empty:
                        break

                if not has_data:
                    time.sleep(0.01)

        except Exception as e:
            _jtrace(f"[TRACE] core.system.safety_monitor.SafetyMonitor.run_monitored: except {str(e)[:80]}")
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                _jtrace(f"[TRACE] core.system.safety_monitor.SafetyMonitor.run_monitored: except TimeoutExpired")
                process.kill()
            raise e

        if timed_out:
            # Kill the hung process and surface a clear timeout instead of hanging forever.
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                _jtrace(f"[TRACE] core.system.safety_monitor.SafetyMonitor.run_monitored: except TimeoutExpired")
                process.kill()
            raise subprocess.TimeoutExpired(cmd, timeout,
                                            output="".join(stdout_accum),
                                            stderr="".join(stderr_accum))

        ret = process.poll()
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=ret,
            stdout="".join(stdout_accum),
            stderr="".join(stderr_accum)
        )

    @classmethod
    def _handle_action(
        cls, 
        action: str, 
        error_type: str, 
        trigger_text: str, 
        process: subprocess.Popen,
        cmd: List[str] or str,
        cwd: Optional[str],
        env: Optional[dict],
        shell: bool
    ):
        """Processes a matched action tier by either resolving locally or raising Escalation.

        Returns the new retry `subprocess.Popen` when the command was re-launched (so the caller's
        monitoring loop can adopt it), or `None` when there is no retry. Escalations raise.
        """
        _jtrace(f"[TRACE] core.system.safety_monitor.SafetyMonitor._handle_action: enter")
        print(f"\n[SAFETY GUARD] Detected matched pattern {error_type} in stream! Action tier: {action.upper()}")

        # Gracefully terminate the blocked process first
        process.terminate()
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            _jtrace(f"[TRACE] core.system.safety_monitor.SafetyMonitor._handle_action: except TimeoutExpired")
            process.kill()

        if action == "escalate":
            message = f"Critical external error detected: '{trigger_text.strip()}'. Requires manual human escalation."
            raise HarnessRuntimeError(message, error_type)

        elif action == "auto_resolve":
            cmd_str = cmd if isinstance(cmd, str) else ' '.join(cmd)
            if error_type == "port_conflict":
                # Attempt to extract port number
                port_match = re.search(r":(\d+)|port (\d+)", trigger_text)
                if port_match:
                    port = int(port_match.group(1) or port_match.group(2))
                    cls._resolve_port_conflict(port)
                    # Re-run the command once after resolving
                    print(f"[SAFETY GUARD] Port {port} freed. Retrying command...")
                    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env, shell=shell, text=True)
                else:
                    raise HarnessRuntimeError("Port conflict detected, but could not parse port number.", error_type)

            elif error_type == "cache_corruption":
                print("[SAFETY GUARD] Clearing package manager caches...")
                if "npm" in cmd_str:
                    subprocess.run(["npm", "cache", "clean", "--force"], capture_output=True)
                else:
                    subprocess.run(["pip", "cache", "purge"], capture_output=True)
                # Re-run the command once
                print("[SAFETY GUARD] Cache cleared. Retrying command...")
                return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env, shell=shell, text=True)

            elif error_type == "playwright_crash":
                print("[SAFETY GUARD] Restarting Playwright browser instance...")
                # Playwright resolves dynamically by restarting context/browser. We re-run command.
                return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env, shell=shell, text=True)

        return None

    @classmethod
    def _resolve_port_conflict(cls, port: int):
        """Identifies PIDs bound to the port. Automatically terminates if it's a known Jarvis-owned process."""
        _jtrace(f"[TRACE] core.system.safety_monitor.SafetyMonitor._resolve_port_conflict: enter")
        print(f"[SAFETY GUARD] Auditing port {port} tcp connections...")
        resolved = False
        
        for conn in psutil.net_connections():
            if conn.laddr.port == port and conn.status == 'LISTEN':
                pid = conn.pid
                if pid:
                    try:
                        p = psutil.Process(pid)
                        name = p.name().lower()
                        cmdline = " ".join(p.cmdline()).lower()
                        
                        # Known Jarvis-owned process names/paths
                        is_jarvis_owned = any(
                            keyword in name or keyword in cmdline
                            for keyword in ["uvicorn", "python", "node", "npm", "ollama"]
                        )
                        
                        if is_jarvis_owned:
                            print(f"[SAFETY GUARD] Terminating known Jarvis process (PID: {pid}, Command: {p.name()}) holding port {port}...")
                            p.terminate()
                            p.wait(timeout=2.0)
                            resolved = True
                        else:
                            print(f"[SAFETY GUARD WARNING] Port {port} held by non-Jarvis process (PID: {pid}, Command: {p.name()}). Will not kill.")
                    except Exception as e:
                        _jtrace(f"[TRACE] core.system.safety_monitor.SafetyMonitor._resolve_port_conflict: except {str(e)[:80]}")
                        print(f"[SAFETY GUARD WARNING] Could not inspect process {pid}: {e}")
        
        if not resolved:
            raise HarnessRuntimeError(f"Could not automatically resolve port conflict on port {port}. Port held by external process.", "port_conflict")

import os
import shutil
import sys
import threading
import time
from typing import Dict, List, Optional

class EnvironmentHandshake:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(EnvironmentHandshake, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._cached_scan: Optional[Dict] = None
        self._cached_prompt: Optional[str] = None
        self._lock = threading.RLock()
        
        # System directories to watch (Linux/WSL)
        self._watch_dirs = ["/usr/bin", "/usr/local/bin"]
        self._docker_socket = "/var/run/docker.sock"
        
        # Cache validation tokens
        self._cached_path_env = ""
        self._cached_docker_socket_exists = False
        self._cached_mtimes: Dict[str, float] = {}
        
        # Perform initial scan to populate cache
        self.scan()

    def invalidate(self):
        with self._lock:
            print("[HANDSHAKE] Invalidation triggered. Clearing cached capability scan.")
            self._cached_scan = None
            self._cached_prompt = None

    def _is_cache_valid(self) -> bool:
        """Checks if any tracked system state has changed since the last scan."""
        # 1. Check PATH environment variable
        current_path = os.environ.get("PATH", "")
        if current_path != self._cached_path_env:
            return False

        # 2. Check Docker socket existence
        current_docker_exists = os.path.exists(self._docker_socket)
        if current_docker_exists != self._cached_docker_socket_exists:
            return False

        # 3. Check mtimes of binary directories
        for d in self._watch_dirs:
            if os.path.isdir(d):
                try:
                    mtime = os.path.getmtime(d)
                except OSError:
                    mtime = 0.0
                if self._cached_mtimes.get(d, 0.0) != mtime:
                    return False
            else:
                if d in self._cached_mtimes:
                    return False

        return True

    def scan(self) -> Dict:
        """
        Scans local system capabilities, returning a dictionary of verified binaries,
        OS information, and container sandboxing states.
        Uses efficient on-demand cache validation to avoid polling overhead.
        """
        with self._lock:
            if self._cached_scan is not None and self._is_cache_valid():
                return self._cached_scan

            t0 = time.perf_counter()
            
            # Update cache validation tokens
            self._cached_path_env = os.environ.get("PATH", "")
            self._cached_docker_socket_exists = os.path.exists(self._docker_socket)
            self._cached_mtimes = {}
            for d in self._watch_dirs:
                if os.path.isdir(d):
                    try:
                        self._cached_mtimes[d] = os.path.getmtime(d)
                    except OSError:
                        self._cached_mtimes[d] = 0.0

            capabilities = {
                "os": {
                    "platform": sys.platform,
                    "is_wsl": self._check_wsl(),
                    "sandboxed": os.environ.get("JARVIS_SANDBOXED", "false").lower() == "true",
                },
                "binaries": {},
                "services": {
                    "docker_running": self._check_docker(),
                }
            }

            # Standard development binaries to search
            target_binaries = [
                "git", "docker", "docker-compose", "npm", "node", 
                "python", "python3", "pip", "pip3", "poetry", 
                "make", "gcc", "g++", "curl", "wget", "sqlite3", "psql"
            ]

            # Optimize shutil.which path search by filtering out slow mounted paths (e.g. /mnt/c)
            path_env = os.environ.get("PATH", "")
            search_paths = None
            if sys.platform.startswith("linux"):
                # Filter out any directory starting with /mnt/ to avoid crossing the host OS mount boundary
                filtered_dirs = [
                    d for d in path_env.split(os.path.pathsep)
                    if d and not d.startswith("/mnt/")
                ]
                search_paths = os.path.pathsep.join(filtered_dirs)

            for binary in target_binaries:
                path = shutil.which(binary, path=search_paths)
                capabilities["binaries"][binary] = {
                    "installed": path is not None,
                    "path": path
                }

            self._cached_scan = capabilities
            self._cached_prompt = None  # Force prompt regeneration
            duration = (time.perf_counter() - t0) * 1000.0
            print(f"[HANDSHAKE] Environmental scan completed in {duration:.2f}ms.")
            return self._cached_scan

    def _check_wsl(self) -> bool:
        if sys.platform.startswith("linux"):
            try:
                with open("/proc/version", "r") as f:
                    if "microsoft" in f.read().lower():
                        return True
            except IOError:
                pass
        return False

    def _check_docker(self) -> bool:
        if os.path.exists(self._docker_socket):
            return os.access(self._docker_socket, os.W_OK)
        return shutil.which("docker") is not None

    def get_system_prompt_addition(self) -> str:
        """
        Generates a highly descriptive, compact Markdown table of the host's actual
        system capabilities to inject into system prompts.
        """
        with self._lock:
            # First ensure cache is valid (scan() will re-validate and update if needed)
            self.scan()
            
            if self._cached_prompt is not None:
                return self._cached_prompt

            scan_data = self._cached_scan
            os_info = scan_data["os"]
            binaries = scan_data["binaries"]
            services = scan_data["services"]

            lines = [
                "",
                "## Local System Capabilities Handshake (WSL2/Linux Environment)",
                "This table represents the mathematically verified capabilities of your current local host environment.",
                "DO NOT attempt to suggest, generate, or execute tools/commands for components marked as 'Not Installed'.",
                "",
                f"| Environment Feature | Value / Status |",
                f"|---|---|",
                f"| Host Platform | `{os_info['platform']}` |",
                f"| Running Inside WSL2 | `{os_info['is_wsl']}` |",
                f"| Execution Sandboxed | `{os_info['sandboxed']}` |",
                f"| Docker Socket Online | `{services['docker_running']}` |",
            ]

            # Append binary presence matrix
            installed = []
            not_installed = []
            for name, meta in binaries.items():
                if meta["installed"]:
                    installed.append(name)
                else:
                    not_installed.append(name)

            lines.append(f"| Verified Installed Binaries | {', '.join([f'`{b}`' for b in installed])} |")
            if not_installed:
                lines.append(f"| Unsupported / Not Installed | {', '.join([f'`{b}`' for b in not_installed])} |")

            lines.append("")
            self._cached_prompt = "\n".join(lines)
            return self._cached_prompt

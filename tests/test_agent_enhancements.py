import os
import sys
import re
import pytest

# Ensure the root project directory is in the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.system.system_handshake import EnvironmentHandshake
from core.system.safety_monitor import SafetyMonitor, HarnessRuntimeError


# =====================================================================
# TIER A: Pure Unit Tests (Zero external processes, zero mocks, zero cost)
# =====================================================================

def test_tier_a_handshake_singleton_and_scanning():
    """Verify EnvironmentHandshake acts as a singleton and performs offline status scanning."""
    hs1 = EnvironmentHandshake()
    hs2 = EnvironmentHandshake()
    assert hs1 is hs2

    scan = hs1.scan()
    assert "os" in scan
    assert "binaries" in scan
    assert "services" in scan
    assert isinstance(scan["os"]["is_wsl"], bool)

    prompt = hs1.get_system_prompt_addition()
    assert "Local System Capabilities Handshake" in prompt
    assert "Verified Installed Binaries" in prompt


@pytest.mark.parametrize(
    "input_text, expected_action, expected_category",
    [
        # Port conflict
        ("Address already in use on port :9000", "auto_resolve", "port_conflict"),
        ("port 8080 already in use", "auto_resolve", "port_conflict"),
        ("EADDRINUSE: address bound", "auto_resolve", "port_conflict"),
        
        # Cache corruption
        ("npm ERR! cache clean --force", "auto_resolve", "cache_corruption"),
        ("pip check validation failed", "auto_resolve", "cache_corruption"),
        ("SHA integrity checksum failed for package", "auto_resolve", "cache_corruption"),
        
        # Playwright crash
        ("browser context was closed unexpectedly", "auto_resolve", "playwright_crash"),
        ("Playwright browser crash detected", "auto_resolve", "playwright_crash"),
        
        # Git authentication (Escalate)
        ("fatal: Could not read from remote repository", "escalate", "git_auth"),
        ("git@github.com: Permission denied (publickey).", "escalate", "git_auth"),
        
        # Database lock (Escalate)
        ("database is locked", "escalate", "db_lock"),
        ("lock held by external process", "escalate", "db_lock"),
        
        # Docker down (Escalate)
        ("Cannot connect to the Docker daemon at unix:///var/run/docker.sock", "escalate", "docker_down"),
        ("docker daemon is not running", "escalate", "docker_down"),
        
        # Permission denied (Escalate only if outside /workspace or /tmp)
        ("Permission denied: /root/secrets", "escalate", "permission_denied"),
        ("EACCES: permission denied to /etc/shadow", "escalate", "permission_denied"),
        ("Permission denied: /workspace/my_project/src.py", None, None),
        ("Permission denied: /tmp/scratch.json", None, None),
    ]
)
def test_tier_a_safety_monitor_scan_stream_patterns(input_text, expected_action, expected_category):
    """Verify that SafetyMonitor.scan_stream correctly classifies log streams without launching processes."""
    action, category = SafetyMonitor.scan_stream(input_text)
    assert action == expected_action
    assert category == expected_category


# =====================================================================
# TIER B: Live Subprocess Tests (Real local execution, no mock descriptors)
# =====================================================================

def test_tier_b_live_safety_monitor_escalation():
    """Verify SafetyMonitor escalates critical errors using a short-lived real python script."""
    # Use python executable compatible with current environment
    python_exe = sys.executable
    
    # Simulating a failing command that prints a git authentication failure to stderr
    script = "import sys; print('fatal: Could not read from remote repository', file=sys.stderr); sys.exit(1)"
    cmd = [python_exe, "-c", script]

    with pytest.raises(HarnessRuntimeError) as exc_info:
        SafetyMonitor.run_monitored(cmd, timeout=5.0)

    assert exc_info.value.category == "git_auth"
    assert "manual human escalation" in str(exc_info.value)

import os
import sys

# Add root folder to path so it can import tools
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools.shell as s

# Enable sandbox mode for testing
os.environ["JARVIS_SANDBOX_MODE"] = "docker"

if __name__ == "__main__":
    print("--- Sandboxed Shell Execution Test ---")
    print("Redirection Target: docker compose exec sandbox")
    print(s.run_command("uname -a && cat /etc/os-release | grep PRETTY_NAME"))


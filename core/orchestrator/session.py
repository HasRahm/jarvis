import sys
from core.trace import trace as _jtrace
import os
import json
import time
import subprocess
from brain.write import brain_write
from brain.query import brain_query
from brain.get import brain_get
from brain.supabase_store import mem_upsert

class SessionManager:
    def checkpoint(self, session_id: str, state: dict):
        """Write checkpoint before every action."""
        _jtrace(f"[TRACE] core.orchestrator.session.SessionManager.checkpoint: enter")
        data = {
            "session_id": session_id,
            "state": state,
            "timestamp": time.time(),
            "dag_position": state.get("current_index", 0),
            "status": "incomplete" if state.get("status") != "completed" else "completed"
        }
        # Synchronous: checkpoints are recovery-critical — a dropped write
        # defeats the purpose, so commit before returning.
        mem_upsert(f"sessions/{session_id}/checkpoint", json.dumps(data, indent=2))
        
    def mark_completed(self, session_id: str, state: dict):
        """Mark session as completed."""
        _jtrace(f"[TRACE] core.orchestrator.session.SessionManager.mark_completed: enter")
        data = {
            "session_id": session_id,
            "state": state,
            "timestamp": time.time(),
            "dag_position": state.get("current_index", 0),
            "status": "completed"
        }
        # Synchronous: checkpoints are recovery-critical — a dropped write
        # defeats the purpose, so commit before returning.
        mem_upsert(f"sessions/{session_id}/checkpoint", json.dumps(data, indent=2))

    def recover(self) -> dict | None:
        """On startup, check for incomplete sessions."""
        _jtrace(f"[TRACE] core.orchestrator.session.SessionManager.recover: enter")
        try:
            from brain.write import _GBRAIN_PATH
            if _GBRAIN_PATH:
                cmd = [_GBRAIN_PATH, "list", "--limit", "100", "--sort", "updated_desc"]
                if os.name == "nt" and _GBRAIN_PATH.endswith(".cmd"):
                    cmd = ["cmd.exe", "/c"] + cmd
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")
                    for line in lines:
                        parts = line.split()
                        if not parts:
                            continue
                        slug = parts[0]
                        if slug.startswith("sessions/") and slug.endswith("/checkpoint"):
                            content = brain_get(slug)
                            if content:
                                try:
                                    data = json.loads(content)
                                    if data.get("status") == "incomplete":
                                        return data
                                except Exception:
                                    _jtrace(f"[TRACE] core.orchestrator.session.SessionManager.recover: except Exception")
                                    continue
        except Exception:
            _jtrace(f"[TRACE] core.orchestrator.session.SessionManager.recover: except Exception")
            pass
        return None

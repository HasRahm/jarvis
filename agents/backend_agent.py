"""
Backend Agent — specializes in API routes, database schemas, and server logic.

Uses claude-sonnet-4-6 via the Anthropic SDK.
Falls back to gemini-3.1-pro-preview if Anthropic is rate-limited.
"""

import os
import json
import logging
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert backend engineer and database architect.
You write clean, production-ready Python (FastAPI) and SQL.

When given a task:
1. Analyze what database schema changes are needed
2. Write the SQL migration
3. Write the API endpoint code
4. Return your work as a JSON object with this exact structure:

{
  "files": {
    "path/to/file.py": "file contents...",
    "path/to/migration.sql": "SQL contents..."
  },
  "summary": "Brief description of what was built",
  "contract": {
    "tables": [{"name": "...", "columns": [...]}],
    "endpoints": [{"method": "POST", "path": "/api/...", "body": {...}, "response": {...}}]
  }
}

The "contract" field is critical — other agents read it from AGENTS.md to understand
what you built. Be precise about column names, types, and endpoint signatures.

IMPORTANT: Return ONLY the JSON object. No markdown, no explanation, no code fences."""


class BackendAgent(BaseAgent):
    """Backend agent for API routes, schemas, and database work."""

    def __init__(self, user_id: str | None = None):
        super().__init__(role="backend", user_id=user_id)

    def run(self, task: str) -> dict:
        """Execute a backend/database task."""
        self.update_status("WORKING", "Analyzing task")
        self.append_log(f"Started: {task}")

        try:
            # Read AGENTS.md to see if other agents have provided context
            agents_md = self.read_agents_md()

            full_prompt = f"""Task: {task}

Current AGENTS.md state (for context from other agents):
{agents_md}

Generate the backend code and database schema for this task.
Return ONLY a JSON object as specified in your system prompt."""

            self.update_status("WORKING", "Generating code")
            response = self._call_model(SYSTEM_PROMPT, full_prompt)

            # Parse the response — strip any accidental markdown fencing
            clean = response.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1]  # remove first line
                if clean.endswith("```"):
                    clean = clean[:-3]
                clean = clean.strip()

            result = json.loads(clean)

            # Write generated files to workspace
            files_written = []
            for filepath, content in result.get("files", {}).items():
                self.write_workspace_file(filepath, content)
                files_written.append(filepath)

            # Write the contract to AGENTS.md so other agents can read it
            contract = result.get("contract", {})
            if contract:
                contract_str = json.dumps(contract, indent=2)
                self.append_log(f"Contract published:\n```json\n{contract_str}\n```")

                # 10c: Persist contract to GBrain for cross-session recall
                if os.environ.get("JARVIS_CI") != "true":
                    try:
                        import re as _re
                        _md = self.read_agents_md()
                        _m = _re.search(r'\| Task ID \| ([^|]+) \|', _md)
                        _slug_suffix = _m.group(1).strip()[-20:] if _m else "unknown"
                        from brain.write import brain_write
                        brain_write(f"contract/{_slug_suffix}", contract_str)
                        logger.info(f"[backend] Contract stored to GBrain: contract/{_slug_suffix}")
                    except Exception as _be:
                        logger.warning(f"[backend] GBrain contract write failed: {_be}")

            self.update_status("DONE", f"Created {len(files_written)} files")
            self.append_log(f"Completed: {result.get('summary', 'Task done')}")

            return {
                "status": "success",
                "output": result.get("summary", "Backend task completed"),
                "files": files_written,
                "contract": contract,
            }

        except json.JSONDecodeError as e:
            self.update_status("ERROR", "Invalid JSON response")
            self.append_log(f"ERROR: Model returned invalid JSON: {e}")
            return {"status": "error", "output": f"JSON parse error: {e}", "files": []}

        except Exception as e:
            self.update_status("ERROR", str(e)[:50])
            self.append_log(f"ERROR: {e}")
            return {"status": "error", "output": str(e), "files": []}

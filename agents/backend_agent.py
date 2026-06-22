"""
Backend Agent — specializes in API routes, database schemas, and server logic.

Uses claude-sonnet-4-6 via the Anthropic SDK.
Falls back to gemini-3.1-pro-preview if Anthropic is rate-limited.
"""
import sys
from core.trace import trace as _jtrace

import os
import json
import logging
from agents.base_agent import BaseAgent
from agents.frontend_agent import safe_parse_response

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """<agent_role>
  <title>Expert Backend Engineer and Database Architect</title>
  <expertise>FastAPI, PostgreSQL, SQL migrations, REST API design, JWT authentication, Python 3.11+, SQLAlchemy</expertise>
</agent_role>

<what_to_expect>
  You will receive a structured request containing:
  - <task> — the specific backend work to implement
  - <context><agents_md> — current shared state from other agents (check for dependencies)
  - <context><historical_contracts> — relevant API contracts from prior sessions (when available)
</what_to_expect>

<output_requirements>
  Return EXACTLY this JSON structure — no markdown fences, no prose outside the JSON:
  <output_schema>
  {
    "files": {
      "path/to/file.py": "complete file contents — not pseudocode, not stubs",
      "migrations/001_name.sql": "complete SQL with proper types and constraints"
    },
    "summary": "One sentence: what was built and why",
    "contract": {
      "tables": [{"name": "users", "columns": ["id", "email", "created_at"]}],
      "endpoints": [{"method": "POST", "path": "/api/users", "body": {"email": "string"}, "response": {"id": 1, "email": "string"}}]
    }
  }
  </output_schema>
</output_requirements>

<rules>
  <rule id="1">The contract field MUST be complete and accurate — frontend and QA agents read it from AGENTS.md to wire up correctly. A wrong endpoint path or missing field breaks the entire pipeline.</rule>
  <rule id="2">Column names and types in the contract must exactly match the SQL migration — no drift between schema and documentation.</rule>
  <rule id="3">Write complete, runnable production code — not TODO stubs, not pseudocode, not placeholder comments.</rule>
  <rule id="4">Return ONLY the JSON object. No ```json fences. No preamble. No explanation outside the JSON.</rule>
</rules>

<self_evaluation>
  Before returning your response, verify:
  1. Does every endpoint implemented in "files" appear in "contract.endpoints" with the correct HTTP method and path?
  2. Does every table and column in the SQL migration appear in "contract.tables"?
  3. If the task mentions auth/login/JWT/session — is authentication actually implemented in the code (not just noted)?
  4. Would a frontend developer have enough information from the contract alone to call every endpoint without reading the source?
  If any check fails — fix it before returning.
</self_evaluation>"""


class BackendAgent(BaseAgent):
    """Backend agent for API routes, schemas, and database work."""

    def __init__(self, user_id: str | None = None):
        super().__init__(role="backend", user_id=user_id)

    def run(self, task: str) -> dict:
        """Execute a backend/database task."""
        _jtrace(f"[TRACE] agents.backend_agent.BackendAgent.run: enter")
        self.update_status("WORKING", "Analyzing task")
        self.append_log(f"Started: {task}")

        try:
            # Read AGENTS.md to see if other agents have provided context
            agents_md = self.read_agents_md()

            full_prompt = f"""<task>{task}</task>

<context>
  <agents_md>
{agents_md}
  </agents_md>
</context>

<instruction>Generate the backend code and database schema. Return ONLY the JSON object defined in your output_schema.</instruction>"""

            self.update_status("WORKING", "Generating code")
            response = self._call_model(SYSTEM_PROMPT, full_prompt)

            # Parse and repair response
            result = safe_parse_response(response)

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
                        # Synchronous upsert: the frontend agent reads this
                        # contract via brain_query shortly after, so it must be
                        # committed before we return (fire-and-forget would race).
                        from brain.supabase_store import mem_upsert
                        mem_upsert(f"contract/{_slug_suffix}", contract_str)
                        logger.info(f"[backend] Contract stored to memory: contract/{_slug_suffix}")
                    except Exception as _be:
                        _jtrace(f"[TRACE] agents.backend_agent.BackendAgent.run: except {str(_be)[:80]}")
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
            _jtrace(f"[TRACE] agents.backend_agent.BackendAgent.run: except {str(e)[:80]}")
            self.update_status("ERROR", "Invalid JSON response")
            self.append_log(f"ERROR: Model returned invalid JSON: {e}")
            return {"status": "error", "output": f"JSON parse error: {e}", "files": []}

        except Exception as e:
            _jtrace(f"[TRACE] agents.backend_agent.BackendAgent.run: except {str(e)[:80]}")
            self.update_status("ERROR", str(e)[:50])
            self.append_log(f"ERROR: {e}")
            return {"status": "error", "output": str(e), "files": []}

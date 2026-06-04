"""
Frontend Agent — specializes in UI, HTML, CSS, JavaScript, and React components.

Uses gemini-3.1-pro-preview via the Google GenAI SDK.
Includes extra retry logic for Gemini's known harness instability
(tendency to break out of tool loops and print raw tool outputs).
"""

import os
import json
import logging
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert frontend developer specializing in modern web UI.
You write clean, production-ready HTML, CSS, and JavaScript.
You use best practices: semantic HTML, responsive design, accessible markup.

When given a task:
1. Check the AGENTS.md context for any API contracts from the backend agent
2. Build the UI that integrates with those endpoints
3. Return your work as a JSON object with this exact structure:

{
  "files": {
    "index.html": "file contents...",
    "styles.css": "CSS contents...",
    "app.js": "JavaScript contents..."
  },
  "summary": "Brief description of what was built"
}

If the AGENTS.md contains a backend contract with endpoint details,
wire your frontend to call those endpoints correctly.

IMPORTANT: Return ONLY the JSON object. No markdown, no explanation, no code fences."""


class FrontendAgent(BaseAgent):
    """Frontend agent for UI generation."""

    def __init__(self, user_id: str | None = None):
        # Extra retries for Gemini's harness instability
        super().__init__(role="frontend", max_retries=4, user_id=user_id)

    def run(self, task: str) -> dict:
        """Execute a frontend/UI task."""
        self.update_status("WORKING", "Analyzing task")
        self.append_log(f"Started: {task}")

        try:
            agents_md = self.read_agents_md()

            # 10c: Query GBrain for historical API contracts from prior sessions
            _gbrain_ctx = ""
            if os.environ.get("JARVIS_CI") != "true":
                try:
                    from brain.query import brain_query
                    _qr = brain_query(f"API contract endpoints for: {task[:80]}")
                    if _qr and "No relevant memories" not in _qr and "error" not in _qr.lower():
                        _gbrain_ctx = f"\nHistorical GBrain API contracts:\n{_qr}\n"
                        logger.info("[frontend] Injected GBrain historical contract context.")
                except Exception as _qe:
                    logger.warning(f"[frontend] GBrain query failed: {_qe}")

            full_prompt = f"""Task: {task}
{_gbrain_ctx}
Current AGENTS.md state (check for backend contracts/endpoints):
{agents_md}

Generate the frontend code for this task.
Return ONLY a JSON object as specified in your system prompt."""

            self.update_status("WORKING", "Generating UI code")
            response = self._call_model(SYSTEM_PROMPT, full_prompt)

            # Parse response — handle Gemini's tendency to wrap in markdown
            clean = response.strip()
            if clean.startswith("```"):
                # Remove ```json or ``` prefix
                first_newline = clean.index("\n")
                clean = clean[first_newline + 1:]
                if clean.endswith("```"):
                    clean = clean[:-3]
                clean = clean.strip()

            result = json.loads(clean)

            files_written = []
            for filepath, content in result.get("files", {}).items():
                self.write_workspace_file(filepath, content)
                files_written.append(filepath)

            self.update_status("DONE", f"Created {len(files_written)} files")
            self.append_log(f"Completed: {result.get('summary', 'UI done')}")

            return {
                "status": "success",
                "output": result.get("summary", "Frontend task completed"),
                "files": files_written,
            }

        except json.JSONDecodeError as e:
            self.update_status("ERROR", "Invalid JSON response")
            self.append_log(f"ERROR: Model returned invalid JSON: {e}")
            return {"status": "error", "output": f"JSON parse error: {e}", "files": []}

        except Exception as e:
            self.update_status("ERROR", str(e)[:50])
            self.append_log(f"ERROR: {e}")
            return {"status": "error", "output": str(e), "files": []}

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
import re
import asyncio

logger = logging.getLogger(__name__)

class JSONRepairError(Exception):
    pass

def safe_parse_response(raw: str) -> dict:
    """
    Repair and parse malformed/truncated JSON output.
    """
    # 1. Clean markdown fences
    clean = raw.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        if lines[0].startswith("```"):
            clean = "\n".join(lines[1:])
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
        
    # Try parsing directly
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # Try to find a JSON block in the clean text
    match = re.search(r'\{.*\}|\[.*\]', clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
            
    # Best effort repair for truncated JSON by backtracking
    # We backtrack character by character from the end of the clean string.
    # At each step, we check if we can successfully close and parse it.
    max_backtrack = min(len(clean), 2000)
    for backtrack_len in range(max_backtrack):
        candidate = clean if backtrack_len == 0 else clean[:-backtrack_len]
        
        # Strip trailing commas, colons, spaces, partial keys/words
        candidate = candidate.rstrip(" \t\n\r,:{[")
        
        # Scan state to find open strings and open brackets
        in_string = False
        escape = False
        stack = []
        for char in candidate:
            if escape:
                escape = False
                continue
            if char == '\\':
                if in_string:
                    escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char == '{':
                    stack.append('}')
                elif char == '[':
                    stack.append(']')
                elif char in ('}', ']'):
                    if stack and stack[-1] == char:
                        stack.pop()
                        
        # Attempt to close the structure
        repaired = candidate
        if in_string:
            repaired += '"'
        for close_char in reversed(stack):
            repaired += close_char
            
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            continue
            
    # Raise the JSONRepairError if everything fails
    raise JSONRepairError(
        f"Could not parse response after repair attempts.\n"
        f"Raw response (first 500 chars): {raw[:500]}"
    )

async def call_gemini(prompt: str) -> str:
    """Helper to satisfy call_with_retry by invoking Google Gemini API via llm_adapter."""
    from core.system.llm_adapter import call_llm
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: call_llm([{"role": "user", "content": prompt}], "gemini-3.1-pro-preview")
    )
    return response.get("content", "") if isinstance(response, dict) else str(response)

async def call_with_retry(prompt: str, max_retries: int = 3) -> dict:
    import os
    from agents.base_agent import PROJECT_ROOT
    from datetime import datetime
    for attempt in range(max_retries):
        try:
            raw = await call_gemini(prompt)
            return safe_parse_response(raw)
        except JSONRepairError as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt  # 1s, 2s, 4s
            
            # Log to task.log
            msg = f"JSON repair attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {wait}s..."
            logger.warning(msg)
            for log_dir in [os.path.join(PROJECT_ROOT, "workspaces", "frontend"), PROJECT_ROOT]:
                try:
                    os.makedirs(log_dir, exist_ok=True)
                    with open(os.path.join(log_dir, "task.log"), "a", encoding="utf-8") as f:
                        f.write(f"[{datetime.now().isoformat()}] [frontend] {msg}\n")
                except Exception:
                    pass
            await asyncio.sleep(wait)

SYSTEM_PROMPT = """<agent_role>
  <title>Expert Frontend Developer</title>
  <expertise>HTML5, CSS3, JavaScript ES2024, React, responsive design, accessibility (WCAG 2.1), REST API integration</expertise>
</agent_role>

<what_to_expect>
  You will receive a structured request containing:
  - <task> — the specific UI to build
  - <context><agents_md> — current shared state including backend contracts and endpoint signatures
  - <context><historical_contracts> — API contracts from prior sessions (when available)
</what_to_expect>

<output_requirements>
  Return EXACTLY this JSON structure — no markdown fences, no prose outside the JSON:
  <output_schema>
  {
    "files": {
      "index.html": "complete HTML with proper DOCTYPE, head, and body",
      "styles.css": "complete CSS — responsive and accessible",
      "app.js": "complete JavaScript — wired to backend endpoints from the contract"
    },
    "summary": "One sentence: what UI was built and how it connects to the backend"
  }
  </output_schema>
</output_requirements>

<rules>
  <rule id="1">Check agents_md for the backend contract FIRST — use the exact endpoint paths, methods, and payload shapes defined there. Do not invent endpoint signatures.</rule>
  <rule id="2">Write complete, functional code — not stubs or TODO placeholders.</rule>
  <rule id="3">Keep generated code concise — include at most 2-3 sample items in any mock dataset to prevent token truncation.</rule>
  <rule id="4">Return ONLY the JSON object. No ```json fences. No preamble. No explanation outside the JSON.</rule>
</rules>

<self_evaluation>
  Before returning your response, verify:
  1. Are all API calls in the JavaScript using the exact paths and HTTP methods from the backend contract?
  2. Is every form field wired to the correct endpoint body field name?
  3. Does the UI handle both success and error responses from the API?
  4. Is the HTML valid, semantic, and complete (with DOCTYPE, head, body)?
  If any check fails — fix it before returning.
</self_evaluation>"""


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

            full_prompt = f"""<task>{task}</task>

<context>
  <agents_md>
{agents_md}
  </agents_md>{f"""
  <historical_contracts>
{_gbrain_ctx.strip()}
  </historical_contracts>""" if _gbrain_ctx else ""}
</context>

<instruction>Generate the frontend UI code. Return ONLY the JSON object defined in your output_schema.</instruction>"""

            self.update_status("WORKING", "Generating UI code")
            
            result = None
            last_err = None
            max_attempts = 3
            
            for attempt in range(max_attempts):
                try:
                    response = self._call_model(SYSTEM_PROMPT, full_prompt)
                    result = safe_parse_response(response)
                    break
                except JSONRepairError as e:
                    last_err = e
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    msg = f"JSON repair/parse attempt {attempt + 1}/{max_attempts} failed: {e}. Retrying in {wait}s..."
                    logger.warning(msg)
                    
                    # Log repair attempt to task.log in both agent workspace and project root
                    from agents.base_agent import PROJECT_ROOT
                    from datetime import datetime
                    
                    # Save full raw response for debugging
                    try:
                        scratch_dir = os.path.join(PROJECT_ROOT, "scratch")
                        os.makedirs(scratch_dir, exist_ok=True)
                        with open(os.path.join(scratch_dir, f"failed_response_{attempt+1}.txt"), "w", encoding="utf-8") as f:
                            f.write(response)
                    except Exception as save_err:
                        logger.warning(f"Failed to save raw response: {save_err}")
                    
                    for log_dir in [self.workspace, PROJECT_ROOT]:
                        try:
                            os.makedirs(log_dir, exist_ok=True)
                            with open(os.path.join(log_dir, "task.log"), "a", encoding="utf-8") as f:
                                f.write(f"[{datetime.now().isoformat()}] [frontend] {msg}\n")
                        except Exception as log_err:
                            logger.warning(f"Failed to write to task.log in {log_dir}: {log_err}")
                    
                    if attempt < max_attempts - 1:
                        import time
                        time.sleep(wait)
            
            if result is None:
                raise last_err

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

        except Exception as e:
            self.update_status("ERROR", str(e)[:50])
            self.append_log(f"ERROR: {e}")
            return {"status": "error", "output": str(e), "files": []}

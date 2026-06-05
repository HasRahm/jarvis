"""
Base Agent — abstract base class for all specialized agents.

Each agent:
- Has its own workspace directory (process-based isolation)
- Reads/writes AGENTS.md as the only coordination mechanism
- Uses model_router for model selection (never hard-codes model strings)
- Has built-in retry logic for API instability
"""

import os
import re
import sys
import json
import time
import logging
from abc import ABC, abstractmethod
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.model_router import get_model, get_provider, get_api_key, get_fallbacks
from core.orchestrator.distributed_sync import agents_md_lock

logger = logging.getLogger(__name__)

# Project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_MD_PATH = os.path.join(PROJECT_ROOT, "AGENTS.md")

PRICING_LAST_UPDATED = "2026-06-05"
PRICING = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-8": {"input": 15.00, "output": 75.00},
    "gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00},
    "gpt-5.4": {"input": 2.50, "output": 15.00},
    "gemini-3.5-flash": {"input": 0.075, "output": 0.30},
    "gemma4:31b": {"input": 0.00, "output": 0.00},
    "gemma4:31b-cloud": {"input": 0.00, "output": 0.00},
}

def check_pricing_freshness():
    """Warning if token operational pricing has gone stale (> 90 days since update)."""
    try:
        updated_date = datetime.strptime(PRICING_LAST_UPDATED, "%Y-%m-%d")
        delta = datetime.now() - updated_date
        if delta.days > 90:
            print(
                f"[WARNING] Operational pricing rules are STALE ({delta.days} days since last update). "
                f"Please update model costs inside base_agent.py."
            )
            logger.warning(f"Pricing data is {delta.days} days stale. Fresh review required.")
    except Exception as e:
        logger.warning(f"Pricing freshness audit failed: {e}")

# Check pricing freshness on import
check_pricing_freshness()

def record_api_telemetry(role: str, model: str, latency: float, input_tokens: int, output_tokens: int, status: str):
    """Atomically record model telemetry data point under lock."""
    telemetry_path = os.path.join(PROJECT_ROOT, "workspaces", "telemetry.json")
    
    # Calculate estimated cost (USD per 1 Million tokens)
    price_info = PRICING.get(model, {"input": 0.0, "output": 0.0})
    cost_est = (input_tokens * price_info["input"] + output_tokens * price_info["output"]) / 1_000_000.0
    
    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "role": role,
        "model": model,
        "latency_sec": round(latency, 3),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_est, 6),
        "status": status,
        "cost_type": "estimated, verify against provider dashboard"
    }
    
    os.makedirs(os.path.dirname(telemetry_path), exist_ok=True)
    with agents_md_lock(telemetry_path + ".lock"):
        records = []
        if os.path.exists(telemetry_path):
            try:
                with open(telemetry_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        records = json.loads(content)
            except Exception as e:
                logger.warning(f"Failed to read telemetry file: {e}")
                
        records.append(record)
        
        try:
            with open(telemetry_path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write telemetry data: {e}")


class BaseAgent(ABC):
    """Abstract base class for all Jarvis IDE agents."""

    def __init__(self, role: str, max_retries: int = 3, user_id: str | None = None):
        self.role = role
        self.user_id = user_id
        self.model = get_model(role)

        # 10b: Adaptive model override — learned best model takes precedence
        # over env/default when enough telemetry samples exist.
        if os.environ.get("JARVIS_CI") != "true":
            try:
                from agents.adaptive_router import get_adaptive_model
                _adaptive = get_adaptive_model(role)
                if _adaptive and _adaptive != self.model:
                    logger.info(f"[{role}] Adaptive router: {self.model} -> {_adaptive}")
                    self.model = _adaptive
            except Exception as _ae:
                logger.warning(f"[{role}] Adaptive router unavailable: {_ae}")

        # provider and api_key must resolve AFTER the potential adaptive override
        self.provider = get_provider(self.model)
        self.api_key = get_api_key(self.provider)
        self.max_retries = max_retries

        # Phase 13: workspace and AGENTS.md are scoped to user_id in SaaS mode.
        # Self-hosted (user_id=None): <root>/workspaces/<role>/
        # SaaS         (user_id set): <root>/workspaces/<user_id>/<role>/
        from core.auth import get_workspace_path, get_agents_md_path
        self.workspace = get_workspace_path(role, user_id)
        self._agents_md_path = get_agents_md_path(user_id)

        # Client is lazily initialized on first _raw_call — no eager SDK imports
        self.client = None

    def _get_mock_response(self, user_prompt: str) -> str:
        """Return a deterministic mock response based on role for offline testing."""
        if self.role == "backend":
            return json.dumps({
                "files": {
                    "migrations/001_create_users_table.sql": "CREATE TABLE users (id SERIAL PRIMARY KEY, email VARCHAR(255) NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);",
                    "app/routers/users.py": "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/api/users')\ndef create_user(user: dict):\n    return {'id': 1, 'email': user['email'], 'created_at': '2026-05-18'}\n"
                },
                "summary": "Created users table migration and POST /api/users endpoint",
                "contract": {
                    "tables": [{"name": "users", "columns": ["id", "email", "created_at"]}],
                    "endpoints": [{"method": "POST", "path": "/api/users", "body": {"email": "string"}, "response": {"id": 1, "email": "string", "created_at": "string"}}]
                }
            })
        elif self.role == "frontend":
            return json.dumps({
                "files": {
                    "index.html": "<!DOCTYPE html><html><head><title>Users UI</title></head><body><h1>Create User</h1><form id='userForm'><input type='email' id='email'/><button type='submit'>Create</button></form><script src='app.js'></script></body></html>",
                    "styles.css": "body { font-family: sans-serif; background: #fafafa; }",
                    "app.js": "document.getElementById('userForm').addEventListener('submit', async (e) => {\n  e.preventDefault();\n  const email = document.getElementById('email').value;\n  const res = await fetch('/api/users', { method: 'POST', body: JSON.stringify({ email }) });\n  const data = await res.json();\n  alert('Created: ' + data.email);\n});"
                },
                "summary": "Built responsive users creation UI wired to /api/users endpoint"
            })
        elif self.role == "qa":
            return json.dumps({
                "review": {
                    "passed": True,
                    "issues": []
                },
                "tests": {
                    "tests/test_users.py": "def test_create_user():\n    assert True\n"
                },
                "summary": "All backend migrations, endpoints, and frontend components verified successfully. Assertions match contracts perfectly."
            })
        elif self.role == "verifier" or self.role == "orchestrator":
            return json.dumps({
                "verified": True,
                "removed_issues": [],
                "notes": "Verified offline during CI"
            })
        elif self.role == "iac":
            return json.dumps({
                "files": {
                    "terraform/main.tf": "# Mock Terraform main file\nresource \"local_file\" \"db_init\" {\n  filename = \"db_setup.sql\"\n  content  = \"SELECT 1;\"\n}",
                    "terraform/variables.tf": "# Mock variables\nvariable \"db_name\" {\n  type = string\n  default = \"mock_db\"\n}"
                },
                "plan": {
                    "to_add": 1,
                    "to_change": 0,
                    "to_destroy": 0,
                    "summary": "Plan: 1 to add, 0 to change, 0 to destroy."
                },
                "notes": "Mocked offline Terraform infrastructure plan."
            })
        else:
            return "{}"

    def _call_model(self, system_prompt: str, user_prompt: str) -> str:
        """Send a prompt to the model with retry logic and fallback chain."""
        # Dynamic Skills Injection!
        if self.role != "orchestrator":
            try:
                from core.system.skills import SkillsEngine
                task_match = re.match(r"^Task:\s*(.*?)(?:\n|$)", user_prompt, re.IGNORECASE)
                task_text = task_match.group(1).strip() if task_match else user_prompt.strip()
                
                engine = SkillsEngine()
                addition = engine.get_skills_prompt_addition(task_text)
                if addition:
                    system_prompt += addition
                    logger.info(f"[{self.role}] Dynamically loaded matching skills into system prompt context.")
            except Exception as se:
                logger.warning(f"[{self.role}] Dynamic skills injection failed: {se}")

        if os.environ.get("JARVIS_CI") == "true":
            logger.info(f"[{self.role}] JARVIS_CI=true. Returning mock response.")
            return self._get_mock_response(user_prompt)

        models_to_try = [self.model] + get_fallbacks(self.role)

        for model_str in models_to_try:
            provider = get_provider(model_str)
            for attempt in range(self.max_retries):
                try:
                    return self._raw_call(provider, model_str, system_prompt, user_prompt)
                except Exception as e:
                    wait = 2 ** attempt
                    logger.warning(
                        f"[{self.role}] {model_str} attempt {attempt+1}/{self.max_retries} "
                        f"failed: {e}. Retrying in {wait}s..."
                    )
                    time.sleep(wait)

            logger.error(f"[{self.role}] {model_str} exhausted all retries. Trying fallback...")

        raise RuntimeError(f"[{self.role}] All models exhausted. No response obtained.")

    def _raw_call(self, provider: str, model: str, system_prompt: str, user_prompt: str) -> str:
        """Make a single API call to the specified provider/model."""
        start_time = time.time()
        input_tokens = len(system_prompt + user_prompt) // 4
        output_tokens = 0
        status = "success"
        response_text = ""

        try:
            if os.environ.get("JARVIS_CI") == "true":
                logger.info(f"[CI MODE] Intercepted raw call for {model}. Returning mock response.")
                if "verifier" in system_prompt or "verified" in system_prompt or "fact-checker" in system_prompt:
                    response_text = json.dumps({
                        "verified": True,
                        "removed_issues": [],
                        "notes": "Verified offline during CI"
                    })
                elif "Infrastructure-as-Code" in system_prompt or "Terraform" in system_prompt:
                    response_text = json.dumps({
                        "files": {
                            "terraform/main.tf": "# Mock Terraform main file\nresource \"local_file\" \"db_init\" {\n  filename = \"db_setup.sql\"\n  content  = \"SELECT 1;\"\n}",
                            "terraform/variables.tf": "# Mock variables\nvariable \"db_name\" {\n  type = string\n  default = \"mock_db\"\n}"
                        },
                        "plan": {
                            "to_add": 1,
                            "to_change": 0,
                            "to_destroy": 0,
                            "summary": "Plan: 1 to add, 0 to change, 0 to destroy."
                        },
                        "notes": "Mocked offline Terraform infrastructure plan."
                    })
                else:
                    response_text = "{}"
                
                output_tokens = len(response_text) // 4
                latency = time.time() - start_time
                record_api_telemetry(self.role, model, latency, input_tokens, output_tokens, status)
                return response_text

            if provider == "google":
                import google.generativeai as genai
                api_key = get_api_key("google")
                genai.configure(api_key=api_key)
                client = genai.GenerativeModel(
                    model,
                    system_instruction=system_prompt
                )
                response = client.generate_content(user_prompt)
                response_text = response.text
                
                try:
                    input_tokens = getattr(response.usage_metadata, "prompt_token_count", input_tokens)
                    output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0)
                except Exception:
                    output_tokens = len(response_text) // 4

            elif provider == "anthropic":
                import anthropic
                client = anthropic.Anthropic(api_key=get_api_key("anthropic"))
                response = client.messages.create(
                    model=model,
                    max_tokens=8192,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}]
                )
                response_text = response.content[0].text
                
                try:
                    input_tokens = getattr(response.usage, "input_tokens", input_tokens)
                    output_tokens = getattr(response.usage, "output_tokens", 0)
                except Exception:
                    output_tokens = len(response_text) // 4

            elif provider == "openai":
                import openai
                client = openai.OpenAI(api_key=get_api_key("openai"))
                params = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                }
                if "gpt-5" in model or "o1" in model or "o3" in model:
                    params["max_completion_tokens"] = 8192
                else:
                    params["max_tokens"] = 8192

                response = client.chat.completions.create(**params)
                response_text = response.choices[0].message.content
                
                try:
                    input_tokens = getattr(response.usage, "prompt_tokens", input_tokens)
                    output_tokens = getattr(response.usage, "completion_tokens", 0)
                except Exception:
                    output_tokens = len(response_text) // 4

            elif provider == "ollama":
                import ollama
                response = ollama.chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                response_text = response["message"]["content"]
                output_tokens = len(response_text) // 4

            else:
                raise ValueError(f"Unknown provider: {provider}")

            latency = time.time() - start_time
            record_api_telemetry(self.role, model, latency, input_tokens, output_tokens, status)
            # 10b: Record success for adaptive learning
            if os.environ.get("JARVIS_CI") != "true":
                try:
                    from agents.adaptive_router import record_model_outcome
                    record_model_outcome(self.role, model, True)
                except Exception as _ae:
                    logger.warning(f"[{self.role}] Adaptive record failed: {_ae}")
            return response_text

        except Exception as e:
            status = "error"
            latency = time.time() - start_time
            record_api_telemetry(self.role, model, latency, input_tokens, 0, status)
            # 10b: Record failure for adaptive learning
            if os.environ.get("JARVIS_CI") != "true":
                try:
                    from agents.adaptive_router import record_model_outcome
                    record_model_outcome(self.role, model, False)
                except Exception as _ae:
                    logger.warning(f"[{self.role}] Adaptive record failed: {_ae}")
            raise

    # ---- AGENTS.md Protocol ----

    @property
    def _md_path(self) -> str:
        """Resolve the effective AGENTS.md path.

        Normally set in __init__ via get_agents_md_path(user_id).  Falls back
        to the module-level AGENTS_MD_PATH constant so that test subclasses
        that bypass __init__ and patch base_mod.AGENTS_MD_PATH continue to work.
        """
        return getattr(self, "_agents_md_path", AGENTS_MD_PATH)

    def read_agents_md(self) -> str:
        """Read the full contents of AGENTS.md (user-scoped in SaaS mode)."""
        with open(self._md_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_agents_md(self, content: str):
        """Overwrite AGENTS.md with new content (user-scoped in SaaS mode)."""
        with open(self._md_path, "w", encoding="utf-8") as f:
            f.write(content)

    def update_status(self, status: str, step: str = "—"):
        """Update this agent's row in the Agent Assignments table."""
        with agents_md_lock(self._md_path + ".lock"):
            content = self.read_agents_md()

            # Match the row for this agent's role
            pattern = rf"(\| {self.role}\s+\|[^|]+\|)\s+\w+\s+(\|)\s+[^|]+(\|)"
            replacement = rf"\1 {status} \2 {step} \3"
            updated = re.sub(pattern, replacement, content)

            if updated == content:
                # Fallback: simple line-based replacement
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if line.startswith(f"| {self.role}"):
                        parts = [p.strip() for p in line.split("|")]
                        # parts: ['', 'agent', 'model', 'status', 'step', '']
                        if len(parts) >= 5:
                            parts[3] = f" {status} "
                            parts[4] = f" {step} "
                            lines[i] = "|".join(parts)
                        break
                updated = "\n".join(lines)

            self.write_agents_md(updated)

    def update_task(self, task_id: str, description: str, status: str = "IN_PROGRESS"):
        """Update the Current Task section of AGENTS.md."""
        with agents_md_lock(self._md_path + ".lock"):
            content = self.read_agents_md()
            content = re.sub(r"(\| Task ID \|)[^|]+\|", rf"\1 {task_id} |", content)
            content = re.sub(r"(\| Description \|)[^|]+\|", rf"\1 {description} |", content)
            content = re.sub(r"(\| Status \|)[^|]+\|", rf"\1 {status} |", content)
            content = re.sub(r"(\| Requested By \|)[^|]+\|", rf"\1 orchestrator |", content)
            self.write_agents_md(content)

    def append_log(self, message: str):
        """Append a timestamped entry to the Task Log section."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"- [{timestamp}] {self.role}: {message}\n"
        with agents_md_lock(self._md_path + ".lock"):
            content = self.read_agents_md()
            content += entry
            self.write_agents_md(content)

    # ---- Workspace file operations ----

    def write_workspace_file(self, relative_path: str, content: str):
        """Write a file inside this agent's workspace directory."""
        full_path = os.path.join(self.workspace, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"[{self.role}] Wrote {relative_path}")

    def read_workspace_file(self, relative_path: str) -> str:
        """Read a file from this agent's workspace directory."""
        full_path = os.path.join(self.workspace, relative_path)
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()

    # ---- Abstract interface ----

    @abstractmethod
    def run(self, task: str) -> dict:
        """
        Execute a task. Returns a dict with:
          - status: "success" | "error"
          - output: str (description of what was done)
          - files: list[str] (relative paths of files created/modified)
        """
        pass

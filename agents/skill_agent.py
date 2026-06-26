"""
SkillAgent (Phase 37) — turns ANY skill (a SKILL.md persona) into a first-class agent with the
full pipeline: a scoped workspace, skill-aware model routing, standardized file output, and the
Phase 36 self-correction loop. This is how the 345+ skills from the vendored claude-skills repo
become callable coding/engineering agents instead of one-shot prompt injections.

A skill's SKILL.md body becomes the system persona. We wrap it with a standard OUTPUT contract so
file-producing skills (scaffolders, builders) emit `files` we can write + verify, while analysis
skills (reviewers, auditors) return `notes` and the verification spine simply no-ops (no files).
"""
import sys
from core.trace import trace as _jtrace

import os
import re
import json
import logging

from agents.base_agent import BaseAgent
from agents.frontend_agent import safe_parse_response

logger = logging.getLogger(__name__)

# Output contract appended to every skill persona so SkillAgent output is uniform and verifiable.
_OUTPUT_CONTRACT = """

---
<output_contract>
You are operating as an autonomous agent. After applying your expertise to the task, return EXACTLY
this JSON object — no markdown fences, no prose outside the JSON:
{
  "files": { "path/to/file.ext": "COMPLETE file contents (omit this key entirely if your task produces no files)" },
  "summary": "one sentence describing what you did",
  "notes": "any findings, review comments, or guidance (use this for analysis/review tasks)"
}
Rules:
- Decide your mode FIRST: if the task BUILDS something, produce complete, runnable files in "files"
  (never stubs, TODOs, or pseudocode); if it is analysis or review, omit "files" and put your
  findings in "notes".
- Stay in your skill's lane — apply the expertise the persona above gives you, and don't pad with
  work outside the task.
- Return ONLY the JSON object.
</output_contract>"""


class SkillAgent(BaseAgent):
    """Run a named skill as a full agent."""

    def __init__(self, skill_name: str, user_id: str | None = None):
        self.skill_name = skill_name
        # Workspace/role must be filesystem-safe (no ':' on Windows).
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", skill_name)[:60]
        super().__init__(role=f"skill_{safe}", user_id=user_id)

        # Skill-specific model routing overrides the generic role default.
        try:
            from agents.model_router import get_skill_model, get_provider, get_api_key
            self.model = get_skill_model(skill_name)
            self.provider = get_provider(self.model)
            self.api_key = get_api_key(self.provider)
        except Exception as e:
            _jtrace(f"[TRACE] agents.skill_agent.SkillAgent.__init__: except {str(e)[:80]}")
            logger.warning(f"[skill:{skill_name}] model routing fell back to default: {e}")

        # Load the skill persona (SKILL.md body) — resolves anywhere under skills/, incl. external/.
        try:
            from core.system.skills import SkillsEngine
            self._skill_body = SkillsEngine().get_skill_content(skill_name)
        except Exception as e:
            _jtrace(f"[TRACE] agents.skill_agent.SkillAgent.__init__: except {str(e)[:80]}")
            logger.warning(f"[skill:{skill_name}] could not load skill body: {e}")
            self._skill_body = f"You are the '{skill_name}' specialist agent."

    def run(self, task: str) -> dict:
        """Execute the task using the skill persona; write any produced files; return result dict."""
        _jtrace(f"[TRACE] agents.skill_agent.SkillAgent.run: enter")
        self.update_status("WORKING", f"Running skill {self.skill_name}")
        self.append_log(f"Started skill '{self.skill_name}': {task}")

        try:
            agents_md = self.read_agents_md()
            system_prompt = self._skill_body + _OUTPUT_CONTRACT
            full_prompt = (
                f"<task>{task}</task>\n\n"
                f"<context>\n  <agents_md>\n{agents_md}\n  </agents_md>\n</context>\n\n"
                f"<instruction>Apply your expertise and return ONLY the JSON object from your "
                f"output_contract.</instruction>"
            )

            response = self._call_model(system_prompt, full_prompt)
            result = safe_parse_response(response)
            if not isinstance(result, dict):
                result = {"summary": str(result)[:200], "notes": str(result)}

            files_written = []
            for filepath, content in (result.get("files") or {}).items():
                self.write_workspace_file(filepath, content)
                files_written.append(filepath)

            summary = result.get("summary") or result.get("notes", "")[:120] or f"{self.skill_name} completed"
            self.update_status("DONE", f"Created {len(files_written)} file(s)")
            self.append_log(f"Completed skill '{self.skill_name}': {summary}")

            return {
                "status": "success",
                "output": summary,
                "files": files_written,
                "notes": result.get("notes", ""),
                "skill": self.skill_name,
            }

        except Exception as e:
            _jtrace(f"[TRACE] agents.skill_agent.SkillAgent.run: except {str(e)[:80]}")
            self.update_status("ERROR", str(e)[:50])
            self.append_log(f"ERROR in skill '{self.skill_name}': {e}")
            return {"status": "error", "output": str(e), "files": [], "skill": self.skill_name}

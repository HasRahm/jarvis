"""
IaC Agent — specializes in system configuration, directory provisioning, and local Terraform infrastructure generation.

Dynamically loaded model from MODEL_ROUTER.
"""
import sys
from core.trace import trace as _jtrace

import json
import logging
import re
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """<agent_role>
  <title>Expert Infrastructure-as-Code Engineer</title>
  <expertise>Terraform HCL, Docker, local system provisioning, database schema deployment, container networking</expertise>
</agent_role>

<what_to_expect>
  You will receive a structured request containing:
  - <task> — the infrastructure work to provision or configure
  - <context><agents_md> — current shared state including code contracts and system dependencies
</what_to_expect>

<output_requirements>
  Return EXACTLY this JSON structure — no markdown fences, no prose outside the JSON:
  <output_schema>
  {
    "files": {
      "terraform/main.tf": "complete Terraform HCL configuration",
      "terraform/variables.tf": "complete variables declarations"
    },
    "plan": {
      "to_add": 2,
      "to_change": 0,
      "to_destroy": 0,
      "summary": "Specific description of what will be provisioned and why"
    },
    "notes": "Engineering design decisions and operational notes"
  }
  </output_schema>
</output_requirements>

<rules>
  <rule id="1">Operations are strictly scoped to the workspace directory — do not reference paths outside the project.</rule>
  <rule id="2">Write correct, standard Terraform HCL — not pseudocode or placeholder resource blocks.</rule>
  <rule id="3">The plan.summary must be specific about exactly what resources are being created, changed, or destroyed.</rule>
  <rule id="4">Return ONLY the JSON object. No ```json fences. No preamble. No text outside the JSON.</rule>
</rules>

<self_evaluation>
  Before returning your response, verify:
  1. Do all resource names and types in main.tf use valid Terraform provider syntax?
  2. Does the plan.summary accurately describe what the Terraform configuration will do?
  3. Are all variable references in main.tf declared in variables.tf?
  If any check fails — fix it before returning.
</self_evaluation>"""


class IacAgent(BaseAgent):
    """Infrastructure-as-Code (IaC) agent for system orchestration."""

    def __init__(self):
        super().__init__(role="iac")

    def run(self, task: str) -> dict:
        """Execute an IaC infrastructure provisioning task."""
        _jtrace(f"[TRACE] agents.iac_agent.IacAgent.run: enter")
        self.update_status("WORKING", "Provisioning system infrastructure")
        self.append_log(f"Started IaC Task: {task}")

        try:
            agents_md = self.read_agents_md()

            full_prompt = f"""<task>{task}</task>

<context>
  <agents_md>
{agents_md}
  </agents_md>
</context>

<instruction>Generate the Terraform infrastructure files and plan. Return ONLY the JSON object defined in your output_schema.</instruction>"""

            self.update_status("WORKING", "Generating Terraform config")
            response = self._call_model(SYSTEM_PROMPT, full_prompt)

            clean = response.strip()
            # Robust extraction of content inside markdown code fences
            match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", clean, re.DOTALL)
            if match:
                clean = match.group(1).strip()

            result = json.loads(clean)

            # Write the generated terraform files into the agent's workspace
            created_files = []
            files_dict = result.get("files", {})
            for rel_path, contents in files_dict.items():
                self.write_workspace_file(rel_path, contents)
                created_files.append(rel_path)

            self.append_log(f"IaC finished. Created {len(created_files)} files: {', '.join(created_files)}")
            self.update_status("IDLE", "Finished infrastructure plan")

            return {
                "status": "success",
                "output": result.get("plan", {}).get("summary", "Infrastructure provisioned successfully."),
                "files": created_files,
                "plan": result.get("plan", {}),
                "notes": result.get("notes", "")
            }

        except Exception as e:
            _jtrace(f"[TRACE] agents.iac_agent.IacAgent.run: except {str(e)[:80]}")
            logger.exception("[iac] Provisioning run failed")
            self.append_log(f"IaC failed: {str(e)}")
            self.update_status("IDLE", f"Failed: {str(e)}")
            return {"status": "failed", "output": str(e), "files": []}

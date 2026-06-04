"""
IaC Agent — specializes in system configuration, directory provisioning, and local Terraform infrastructure generation.

Dynamically loaded model from MODEL_ROUTER.
"""

import json
import logging
import re
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Infrastructure-as-Code (IaC) engineer.
You design, generate, plan, and apply Terraform configurations for local development and testing environments.
Your operations are strictly scoped to the workspace directory.

Your primary capabilities include:
1. Generating correct, standard Terraform configurations (main.tf, variables.tf, etc.) to declare local resources.
2. Generating plans (terraform plan) and verifying changes.
3. Applying plans (terraform apply) to configure local system directory mounts, database schemas, and container-level network routing rules.

When given a task:
1. Examine the current system setup and local database dependencies from the context.
2. Write appropriate, secure, and clean Terraform code.
3. Return your output as a JSON object with this exact structure:

{
  "files": {
    "terraform/main.tf": "main.tf contents...",
    "terraform/variables.tf": "variables.tf contents..."
  },
  "plan": {
    "to_add": 3,
    "to_change": 0,
    "to_destroy": 0,
    "summary": "Detailed plan summary..."
  },
  "notes": "Any engineering design notes."
}

Return ONLY the JSON object. No markdown explanations outside the JSON structure, no other text."""


class IacAgent(BaseAgent):
    """Infrastructure-as-Code (IaC) agent for system orchestration."""

    def __init__(self):
        super().__init__(role="iac")

    def run(self, task: str) -> dict:
        """Execute an IaC infrastructure provisioning task."""
        self.update_status("WORKING", "Provisioning system infrastructure")
        self.append_log(f"Started IaC Task: {task}")

        try:
            agents_md = self.read_agents_md()

            full_prompt = f"""Task: {task}

Current AGENTS.md state (includes code contracts and file lists):
{agents_md}

Generate the required Terraform infrastructure files and plan mapping.
Return ONLY a JSON object as specified in your system prompt."""

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
            logger.exception("[iac] Provisioning run failed")
            self.append_log(f"IaC failed: {str(e)}")
            self.update_status("IDLE", f"Failed: {str(e)}")
            return {"status": "failed", "output": str(e), "files": []}

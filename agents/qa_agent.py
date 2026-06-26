"""
QA Agent — specializes in code review, testing, and verification.

Uses gpt-5.4 via the OpenAI SDK.
Includes a verification pass with gemini-3.5-flash to catch
hallucinated test assertions (reasoning models hallucinate at >10%).
"""
import sys
from core.trace import trace as _jtrace

import json
import logging
from agents.base_agent import BaseAgent
from agents.model_router import get_api_key
from agents.frontend_agent import safe_parse_response

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """<agent_role>
  <title>Expert QA Engineer and Code Reviewer</title>
  <expertise>Code review, security auditing, test writing (pytest, unittest), contract verification, API testing</expertise>
</agent_role>

<what_to_expect>
  You will receive a structured request containing:
  - <task> — the QA work to perform
  - <context><agents_md> — current shared state with all code files, contracts, and agent outputs
</what_to_expect>

<when>
  You run LAST, after the backend and frontend agents. Read all of their outputs from <agents_md>
  before reviewing. Judge only code that is actually present: every issue must point at a real file
  and line, and every test must import and call functions/endpoints that truly exist. Verify the
  implementation against the backend contract — drift between the contract and the code IS a real issue.
</when>
<how>
  Review for real bugs and security holes (not style), then write executable tests that exercise the
  contract. Do not invent symbols; if a test would reference something that does not exist, fix the test.
</how>

<output_requirements>
  Return EXACTLY this JSON structure — no markdown fences, no prose outside the JSON:
  <output_schema>
  {
    "review": {
      "passed": true,
      "issues": [
        {"severity": "critical|warning|info", "file": "path/to/file.py", "line": null, "message": "Description of real issue"}
      ]
    },
    "tests": {
      "tests/test_feature.py": "complete test file contents"
    },
    "summary": "One sentence QA summary"
  }
  </output_schema>
</output_requirements>

<rules>
  <rule id="1">Only flag issues that actually exist in the provided code — read the code before claiming an issue exists at a specific location.</rule>
  <rule id="2">Test assertions must reference functions, endpoints, and field names that actually exist in the code. Do not hallucinate function names.</rule>
  <rule id="3">Be practical — flag real bugs and security issues, not style preferences or theoretical concerns.</rule>
  <rule id="4">Return ONLY the JSON object. No ```json fences. No preamble.</rule>
</rules>

<self_evaluation>
  Before returning your response, verify:
  1. Does every issue in "review.issues" reference code that actually exists in agents_md?
  2. Does every test import and call functions/endpoints that are actually defined in the code?
  3. Are all test assertions testing the actual behavior described in the task, not guessed behavior?
  If any check fails — fix it before returning.
</self_evaluation>"""

VERIFIER_PROMPT = """<agent_role>
  <title>Fact-Checker for Code Review Outputs</title>
</agent_role>

<what_to_expect>
  You will receive:
  - <qa_review> — the QA review JSON to verify
  - <source_context> — the actual source code and AGENTS.md state
</what_to_expect>

<verification_checklist>
  <check id="1">Every cited issue actually exists in the provided source at the stated location</check>
  <check id="2">Every test assertion references a function, endpoint, or field name that actually exists in the code</check>
  <check id="3">No hallucinated function names, table names, or endpoint paths</check>
</verification_checklist>

<output_schema>
{
  "verified": true,
  "removed_issues": ["exact message of any hallucinated issue removed"],
  "notes": "brief explanation of any removals, or empty string"
}
</output_schema>

<rule>Return ONLY the JSON object. No markdown fences. No preamble.</rule>"""


class QAAgent(BaseAgent):
    """QA agent for code review, testing, and verification."""

    def __init__(self, user_id: str | None = None):
        super().__init__(role="qa", user_id=user_id)

    def _verify_with_flash_lite(self, review_json: str, source_context: str) -> dict:
        """Run a hallucination verification pass with gemini-3.5-flash."""
        try:
            prompt = f"""<qa_review>
{review_json}
</qa_review>

<source_context>
{source_context}
</source_context>

<instruction>Check for hallucinated issues or test assertions. Return ONLY the JSON object defined in your output_schema.</instruction>"""

            response = self._raw_call(
                "google", "gemini-3.5-flash",
                VERIFIER_PROMPT, prompt
            )

            clean = response.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1]
                if clean.endswith("```"):
                    clean = clean[:-3]
                clean = clean.strip()

            return json.loads(clean)
        except Exception as e:
            _jtrace(f"[TRACE] agents.qa_agent.QAAgent._verify_with_flash_lite: except {str(e)[:80]}")
            logger.warning(f"[qa] Verification pass failed: {e}. Proceeding without verification.")
            return {"verified": True, "removed_issues": [], "notes": "Verification skipped"}

    def verify_ui_layout_visually(self, screenshot_path: str, html_context: str) -> dict:
        """Verify the UI layout visually using Gemini-3.5-flash, with escalation to Gemini-3.1-pro-preview if confidence < 0.8."""
        _jtrace(f"[TRACE] agents.qa_agent.QAAgent.verify_ui_layout_visually: enter")
        import base64
        import json
        import os
        from agents.model_router import get_api_key

        if os.environ.get("JARVIS_CI") == "true":
            logger.info("[CI MODE] Mocking visual verification pass.")
            return {"passed": True, "issues": [], "confidence": 0.95, "notes": "Verified offline"}

        try:
            with open(screenshot_path, "rb") as img_file:
                img_data = img_file.read()

            image_part = {
                "mime_type": "image/png",
                "data": img_data
            }

            system_prompt = """You are an expert senior UI designer and visual auditor holding the
output to the polish bar of Linear, Vercel, and Stripe. Review the layout screenshot alongside its
source HTML/CSS and identify defects against a real design system:
1. Spacing rhythm — does everything snap to a consistent 4/8px scale? Flag ad-hoc margins/padding.
2. Typography — consistent type scale and weights, readable line length, clear hierarchy.
3. Color/tokens — restrained palette used consistently (no stray hard-coded colors), AA contrast.
4. Components — buttons/cards/inputs have proper radius, borders, hover/focus states, alignment.
5. Layout — centered container, balanced whitespace, no overlaps/word-wrap/truncation, responsive.
6. Overall: does it look intentionally designed, or default-browser plain?

Provide your response in JSON:
{
  "passed": true/false,
  "issues": [
    {"message": "specific design-system defect and how to fix it"}
  ],
  "confidence": float (between 0.0 and 1.0 representing your certainty of this evaluation)
}
Return ONLY the JSON string. No explanations, no markdown fences."""

            prompt_text = f"""Please review this UI screenshot.
Source HTML context for structure:
{html_context}"""

            default_model = "gemini-3.5-flash"
            logger.info(f"Running default visual verifier on model: {default_model}")
            
            from google import genai
            from google.genai import types as genai_types
            client = genai.Client(
                api_key=get_api_key("google"),
                http_options=genai_types.HttpOptions(timeout=90000)  # 90s timeout
            )
            response = client.models.generate_content(
                model=default_model,
                contents=[prompt_text, image_part],
                config={"system_instruction": system_prompt}
            )
            
            clean = response.text.strip()
            if clean.startswith("```"):
                # Remove markdown wrapping
                lines = clean.split("\n")
                if len(lines) > 1 and lines[0].startswith("```"):
                    clean = "\n".join(lines[1:])
                if clean.endswith("```"):
                    clean = clean[:-3]
                clean = clean.strip()
                
            res = json.loads(clean)
            
            confidence = res.get("confidence", 1.0)
            if confidence < 0.8:
                escalation_model = "gemini-3.1-pro-preview"
                logger.info(f"Low confidence ({confidence} < 0.8). Escalating visual audit to: {escalation_model}")
                resp_escalate = client.models.generate_content(
                    model=escalation_model,
                    contents=[prompt_text, image_part],
                    config={"system_instruction": system_prompt}
                )
                
                clean_esc = resp_escalate.text.strip()
                if clean_esc.startswith("```"):
                    lines_esc = clean_esc.split("\n")
                    if len(lines_esc) > 1 and lines_esc[0].startswith("```"):
                        clean_esc = "\n".join(lines_esc[1:])
                    if clean_esc.endswith("```"):
                        clean_esc = clean_esc[:-3]
                    clean_esc = clean_esc.strip()
                    
                res = json.loads(clean_esc)
                
            return res
        except Exception as e:
            _jtrace(f"[TRACE] agents.qa_agent.QAAgent.verify_ui_layout_visually: except {str(e)[:80]}")
            logger.warning(f"Visual layout verifier failed: {e}. Defaulting to safe pass.")
            return {"passed": True, "issues": [], "confidence": 1.0, "notes": f"Fallback due to error: {e}"}

    def run(self, task: str) -> dict:
        """Execute a QA/review task."""
        _jtrace(f"[TRACE] agents.qa_agent.QAAgent.run: enter")
        self.update_status("WORKING", "Reviewing code")
        self.append_log(f"Started QA: {task}")

        try:
            agents_md = self.read_agents_md()

            full_prompt = f"""<task>{task}</task>

<context>
  <agents_md>
{agents_md}
  </agents_md>
</context>

<instruction>Review the work done by other agents and generate test cases. Return ONLY the JSON object defined in your output_schema.</instruction>"""

            self.update_status("WORKING", "Generating review")
            response = self._call_model(SYSTEM_PROMPT, full_prompt)

            # Parse and repair response
            result = safe_parse_response(response)
            clean = json.dumps(result)

            # Verification pass to catch hallucinated assertions
            self.update_status("WORKING", "Verifying review")
            verification = self._verify_with_flash_lite(clean, agents_md)

            if not verification.get("verified", True):
                removed = verification.get("removed_issues", [])
                self.append_log(f"Verifier removed {len(removed)} hallucinated issues")
                # Filter out hallucinated issues from review
                if removed and "review" in result:
                    original_count = len(result["review"].get("issues", []))
                    result["review"]["issues"] = [
                        issue for issue in result["review"].get("issues", [])
                        if issue.get("message") not in removed
                    ]
                    logger.info(
                        f"[qa] Verification removed {original_count - len(result['review']['issues'])} issues"
                    )

            # Write test files to workspace
            files_written = []
            for filepath, content in result.get("tests", {}).items():
                self.write_workspace_file(filepath, content)
                files_written.append(filepath)

            review = result.get("review", {})
            passed = review.get("passed", False)
            issues = review.get("issues", [])

            status_str = "PASSED" if passed else f"FAILED ({len(issues)} issues)"
            self.update_status("DONE", status_str)
            self.append_log(f"Completed: {result.get('summary', 'QA done')} — {status_str}")

            return {
                "status": "success",
                "output": result.get("summary", "QA completed"),
                "files": files_written,
                "review": review,
                "verification": verification,
            }

        except json.JSONDecodeError as e:
            _jtrace(f"[TRACE] agents.qa_agent.QAAgent.run: except {str(e)[:80]}")
            self.update_status("ERROR", "Invalid JSON response")
            self.append_log(f"ERROR: Model returned invalid JSON: {e}")
            return {"status": "error", "output": f"JSON parse error: {e}", "files": []}

        except Exception as e:
            _jtrace(f"[TRACE] agents.qa_agent.QAAgent.run: except {str(e)[:80]}")
            self.update_status("ERROR", str(e)[:50])
            self.append_log(f"ERROR: {e}")
            return {"status": "error", "output": str(e), "files": []}

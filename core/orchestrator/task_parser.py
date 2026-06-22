"""
Task Parser — uses gemma4:31b-cloud to decompose a natural language task
into structured subtasks with agent assignments and dependencies.
"""
import sys
from core.trace import trace as _jtrace

import json
import logging

logger = logging.getLogger(__name__)

DECOMPOSITION_PROMPT = """You are a task decomposition engine for a multi-agent IDE.

Given a user task, break it into subtasks and assign each to the correct agent:
- "backend": API routes, database schemas, migrations, server logic
- "frontend": HTML, CSS, JavaScript, React, UI components
- "qa": code review, test generation, verification

Return a JSON array of subtasks. Each subtask must have:
- "id": unique string like "sub_1", "sub_2"
- "agent": "backend" | "frontend" | "qa"
- "task": detailed description of what this agent should do
- "depends_on": array of subtask IDs this depends on (empty if none)

Rules:
1. Database/schema work ALWAYS comes before API routes
2. API routes ALWAYS come before frontend that calls them
3. QA ALWAYS comes last (depends on everything else)
4. Keep subtasks focused — one clear deliverable per subtask

Example output:
[
  {"id": "sub_1", "agent": "backend", "task": "Create users table with id, email, created_at columns", "depends_on": []},
  {"id": "sub_2", "agent": "backend", "task": "Create POST /api/users endpoint", "depends_on": ["sub_1"]},
  {"id": "sub_3", "agent": "qa", "task": "Review and test the users API", "depends_on": ["sub_2"]}
]

IMPORTANT: Return ONLY the JSON array. No markdown, no explanation."""


def parse_task(user_task: str, spec: dict | None = None) -> list[dict]:
    """
    Decompose a user task into structured subtasks using the configured orchestrator model.

    Args:
        user_task: Natural language description of what to build
        spec: Optional SPEC dict from the architect step (Phase 36C). When provided, the
              decomposition is grounded in the spec's data model, API contract, and file plan so
              subtasks align with one coherent blueprint.

    Returns:
        List of subtask dicts with id, agent, task, depends_on
    """
    _jtrace(f"[TRACE] core.orchestrator.task_parser.parse_task: enter")
    import os

    # Phase 41: when the architect produced an office brief with assignments, derive the subtask
    # DAG DETERMINISTICALLY from it — no second LLM call. One office meeting, one brief, executed.
    if spec and isinstance(spec.get("assignments"), list) and spec["assignments"]:
        derived = []
        for a in spec["assignments"]:
            agent = str(a.get("agent", "")).lower().strip()
            if agent not in ("backend", "frontend", "qa", "database", "research"):
                continue
            task_text = a.get("scope") or user_task
            if a.get("acceptance"):
                task_text = f"{task_text}\nAcceptance: {a['acceptance']}"
            derived.append({
                "id": a.get("id") or f"sub_{len(derived) + 1}",
                "agent": agent,
                "task": task_text,
                "depends_on": a.get("depends_on") or [],
            })
        if derived:
            logger.info(f"[task_parser] Derived {len(derived)} subtasks from architect assignments "
                        "(no decomposition LLM call).")
            return derived

    if os.environ.get("JARVIS_CI") == "true":
        logger.info("[CI MODE] Returning mock subtask decomposition for offline testing")
        return [
            {
                "id": "sub_1",
                "agent": "backend",
                "task": "Create users table with id, email, created_at columns in migrations/001_create_users_table.sql",
                "depends_on": []
            },
            {
                "id": "sub_2",
                "agent": "backend",
                "task": "Create POST /api/users endpoint in app/routers/users.py",
                "depends_on": ["sub_1"]
            },
            {
                "id": "sub_3",
                "agent": "qa",
                "task": "Review and verify the users API",
                "depends_on": ["sub_2"]
            }
        ]

    from agents.model_router import get_model, get_provider
    from agents.base_agent import BaseAgent
    from core.system.skills import SkillsEngine
    
    # Create a dummy agent just to reuse the _raw_call logic
    class OrchestratorAgent(BaseAgent):
        def __init__(self):
            # Bypass workspace creation
            self.role = "orchestrator"
            self.model = get_model("orchestrator")
            self.provider = get_provider(self.model)
            self.max_retries = 3

        def run(self, task):
            pass

    agent = OrchestratorAgent()

    logger.info(f"Decomposing task with {agent.model} via {agent.provider}...")

    # Inject agent workflow skills into the orchestrator's prompt
    engine = SkillsEngine()
    skill_names = ["agent-designer", "agent-workflow-designer"]
    prompt_addition = "\n\n--- DYNAMIC SKILLS & DOMAIN EXPERTISE ENABLED ---\n"
    prompt_addition += "You have been matched with the following specialized skills/guidelines for this orchestration task. "
    prompt_addition += "Follow these instructions meticulously to ensure success:\n\n"
    
    skills_injected = False
    for skill in engine.skills:
        if skill["name"] in skill_names:
            prompt_addition += f"### SKILL: {skill['name']}\n"
            prompt_addition += f"*Description: {skill['description']}*\n\n"
            prompt_addition += f"{skill['content']}\n\n"
            skills_injected = True
            
    if skills_injected:
        prompt_addition += "------------------------------------------------\n\n"
        final_prompt = DECOMPOSITION_PROMPT + prompt_addition
    else:
        final_prompt = DECOMPOSITION_PROMPT

    # Phase 36C: ground decomposition in the architect SPEC so subtasks align with the
    # canonical data model, API contract, and file plan instead of improvising.
    decomposition_input = user_task
    if spec:
        try:
            decomposition_input = (
                f"{user_task}\n\n--- IMPLEMENTATION SPEC (decompose to build exactly this) ---\n"
                f"{json.dumps(spec, indent=2)}\n"
                "Create subtasks that implement the data_model, api_contract, and files above. "
                "Backend subtasks build the contract; frontend subtasks consume it; QA verifies the "
                "acceptance_criteria."
            )
        except Exception:
            _jtrace(f"[TRACE] core.orchestrator.task_parser.parse_task: except Exception")
            decomposition_input = user_task

    raw = agent._call_model(final_prompt, decomposition_input)


    import re
    # Extract the JSON array or object block safely (resilient to conversational text or markdown fences)
    json_match = re.search(r"(\[.*\]|\{.*\})", raw, re.DOTALL)
    if json_match:
        raw = json_match.group(1).strip()
    else:
        # Fallback to standard stripping if no brackets found
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
        if match:
            raw = match.group(1).strip()

    subtasks = json.loads(raw)

    # Validate structure
    for st in subtasks:
        assert "id" in st, f"Subtask missing 'id': {st}"
        assert "agent" in st, f"Subtask missing 'agent': {st}"
        assert st["agent"] in ("backend", "frontend", "qa", "database", "research"), f"Invalid agent: {st['agent']}"
        assert "task" in st, f"Subtask missing 'task': {st}"
        assert "depends_on" in st, f"Subtask missing 'depends_on': {st}"

    logger.info(f"Decomposed into {len(subtasks)} subtasks")
    return subtasks

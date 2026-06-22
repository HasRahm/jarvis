"""
Planner — complexity-gated Chain-of-Thought planning before execution (Phase 28a).

Forces the orchestrator to think through a task (goal, needs, steps, failure modes,
verification) BEFORE acting — but only for non-trivial tasks. Trivial one-shot tasks
(a single shell command, a quick lookup) skip the planning round-trip entirely.

The returned plan string is injected into the system message as a <task_plan> block
so the model follows its own plan. Never raises.
"""
import sys

import os
import logging

logger = logging.getLogger(__name__)

PLANNING_PROMPT = """Before taking any action, think through this task carefully.

Task: {task}

Answer these five questions concisely:

1. GOAL — What does success look like exactly? What files, outputs, or state
   changes must exist when done?
2. NEEDS — What information, files, credentials, or system access is required?
   Mark each: HAVE IT / FIND IT / ASK USER.
3. STEPS — Break into the smallest discrete actions. Each step = one tool call.
4. FAILURE MODES — For each step, the most likely way it fails and how to detect it.
5. VERIFICATION — How you will confirm each step succeeded before the next.

Keep the whole plan under 250 words. Be specific and actionable."""

# Keywords / signals that indicate a task needs real planning.
_COMPLEX_KEYWORDS = (
    "open", "click", "type", "navigate", "browser", "desktop", "app", "window",
    "figma", "chrome", "excel", "spreadsheet", "build", "create", "implement",
    "scrape", "extract", "automate", "install", "configure", "search", "download",
    "screenshot", "fill", "form", "login", "email", "schedule", "deploy",
)


def is_complex(task: str) -> bool:
    """Cheap heuristic gate. True = needs a plan; False = trivial one-shot task."""
    print(f"[TRACE] core.orchestrator.planner.is_complex: enter", file=sys.stderr, flush=True)
    t = (task or "").strip().lower()
    if not t:
        return False
    # Multi-step chaining is a strong signal.
    if " and " in t or " then " in t or "," in t or ";" in t:
        return True
    # Longer requests tend to be multi-step.
    if len(t.split()) >= 14:
        return True
    # Any desktop/build/automation keyword.
    return any(kw in t for kw in _COMPLEX_KEYWORDS)


def plan_task(task: str) -> str:
    """Return a compact plan string for complex tasks, or "" to skip planning."""
    print(f"[TRACE] core.orchestrator.planner.plan_task: enter", file=sys.stderr, flush=True)
    task = (task or "").strip()
    if not task or not is_complex(task):
        return ""

    if os.environ.get("JARVIS_CI") == "true":
        return (
            "1. GOAL — complete the task.\n"
            "2. NEEDS — HAVE IT.\n"
            "3. STEPS — execute then verify.\n"
            "4. FAILURE MODES — tool error; detect via result.\n"
            "5. VERIFICATION — call verify_outcome after consequential actions."
        )

    try:
        from core.system.llm_adapter import call_llm
        from agents.model_router import get_model

        os.environ.setdefault("JARVIS_TEMPERATURE", "0.2")  # structured thinking
        result = call_llm(
            messages=[{"role": "user", "content": PLANNING_PROMPT.format(task=task)}],
            model=get_model("orchestrator"),
        )
        plan = (result.get("content") if isinstance(result, dict) else str(result)) or ""
        return plan.strip()
    except Exception as e:
        print(f"[TRACE] core.orchestrator.planner.plan_task: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"[planner] plan generation failed, proceeding without plan: {e}")
        return ""

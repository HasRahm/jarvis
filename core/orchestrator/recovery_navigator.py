"""
Recovery Navigator — get unstuck instead of giving up or faking success (Phase 28a).

When an action fails or the agent is blocked, this maps a recovery path:
  1. Diagnose the failure type from the failure description (keyword classifier).
  2. If it matches a known failure type, return the known escape routes (fast, free).
  3. Otherwise, ask the orchestrator model to reason out a step-by-step recovery plan,
     seeded with the goal, the failure, and the current window stack.

Returns an ordered, numbered recovery-steps string. Never raises.
"""
import sys

import os
import logging

logger = logging.getLogger(__name__)

KNOWN_ESCAPE_ROUTES = {
    "unexpected_dialog": [
        "press Escape",
        "click the Cancel button",
        "click the X button in the dialog title bar",
        "press Alt+F4 if the dialog has focus",
    ],
    "wrong_window_focused": [
        "call desktop_focus_window with the target window title",
        "check the window stack (get_3d_window_graph) for the target",
        "use Alt+Tab to cycle to the target window",
    ],
    "element_not_found": [
        "scroll up to find the element above the viewport",
        "scroll down to find the element below the viewport",
        "check if the element is inside a collapsed section or menu",
        "use Ctrl+F to search for the element's text",
        "fall back to visual_click with a clear description",
    ],
    "page_not_loaded": [
        "wait 2 seconds and re-check the screen (screen_imprint / visual_inspect)",
        "press F5 to refresh",
        "verify the page actually navigated (desktop_get_active_window)",
    ],
    "cursor_in_wrong_app": [
        "the spatial cortex likely fired a CONTEXT_SWITCH",
        "pause and re-focus the intended app with desktop_focus_window",
        "verify the active window before continuing",
    ],
}

RECOVERY_PROMPT = """I am stuck while doing a computer task. Help me recover.

Goal: {goal}
What I tried that failed: {what_failed}
Currently open windows: {windows}

Map a step-by-step recovery plan. Each step must be a single verifiable action.
Start from where I am now, NOT from the beginning. If recovery is impossible,
say WHY clearly. Keep it under 150 words, numbered."""


def _diagnose(what_failed: str) -> str:
    print(f"[TRACE] core.orchestrator.recovery_navigator._diagnose: enter", file=sys.stderr, flush=True)
    r = (what_failed or "").lower()
    if "dialog" in r or "popup" in r or "pop-up" in r:
        return "unexpected_dialog"
    if "wrong window" in r or "wrong app" in r or "focus" in r:
        return "wrong_window_focused"
    if "not found" in r or "can't find" in r or "cannot find" in r or "no match" in r:
        return "element_not_found"
    if "not loaded" in r or "loading" in r or "blank" in r or "no change" in r:
        return "page_not_loaded"
    if "context switch" in r or "context_switch" in r or "cortex" in r:
        return "cursor_in_wrong_app"
    return "unknown"


def get_unstuck(goal: str, what_failed: str) -> str:
    """Return an ordered recovery-steps string for the given stuck situation."""
    print(f"[TRACE] core.orchestrator.recovery_navigator.get_unstuck: enter", file=sys.stderr, flush=True)
    goal = (goal or "").strip()
    what_failed = (what_failed or "").strip()

    diagnosis = _diagnose(what_failed)
    routes = KNOWN_ESCAPE_ROUTES.get(diagnosis)
    if routes:
        header = f"Recovery plan (diagnosis: {diagnosis.replace('_', ' ')}):"
        steps = "\n".join(f"{i}. {s}" for i, s in enumerate(routes, 1))
        return f"{header}\n{steps}\n(Verify with verify_outcome after each step.)"

    # Unknown failure type — reason it out (skip LLM in CI).
    if os.environ.get("JARVIS_CI") == "true":
        return ("Recovery plan (diagnosis: unknown):\n"
                "1. re-read the current screen with visual_inspect\n"
                "2. confirm the active window with desktop_get_active_window\n"
                "3. retry the failed action, then call verify_outcome")

    try:
        from core.system.llm_adapter import call_llm
        from agents.model_router import get_model
        try:
            from tools.windows import get_window_stack
            windows = ", ".join(w.get("title", "") for w in get_window_stack()[:8]) or "unknown"
        except Exception:
            print(f"[TRACE] core.orchestrator.recovery_navigator.get_unstuck: except Exception", file=sys.stderr, flush=True)
            windows = "unknown"

        result = call_llm(
            messages=[{"role": "user", "content": RECOVERY_PROMPT.format(
                goal=goal or "(unspecified)", what_failed=what_failed or "(unspecified)",
                windows=windows)}],
            model=get_model("orchestrator"),
        )
        plan = (result.get("content") if isinstance(result, dict) else str(result)) or ""
        plan = plan.strip()
        return plan or ("Recovery plan (diagnosis: unknown):\n"
                        "1. re-read the screen with visual_inspect\n"
                        "2. retry the action, then call verify_outcome")
    except Exception as e:
        print(f"[TRACE] core.orchestrator.recovery_navigator.get_unstuck: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"[recovery] get_unstuck reasoning failed: {e}")
        return ("Recovery plan (diagnosis: unknown):\n"
                "1. re-read the screen with visual_inspect\n"
                "2. confirm the active window\n"
                "3. retry the failed action, then call verify_outcome")

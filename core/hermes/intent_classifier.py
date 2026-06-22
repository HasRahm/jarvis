import sys
import os
import re
import json
import logging

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a UI correction intent classifier. "
    "Given the user's speech and the last UI element they tapped, "
    "determine if they are requesting a visual correction or UI change. "
    "Output ONLY valid JSON. No explanation, no markdown fences."
)


def classify_correction_intent(text: str, visual_history: list) -> dict | None:
    """
    Classify whether user speech contains a UI correction request.

    Returns {"selector": str, "instruction": str} if correction detected, else None.
    Short-circuits to None under JARVIS_CI=true to keep CI offline.
    """
    print(f"[TRACE] core.hermes.intent_classifier.classify_correction_intent: enter", file=sys.stderr, flush=True)
    if os.environ.get("JARVIS_CI") == "true":
        return None

    last_tap = visual_history[-1] if visual_history else None
    last_selector = last_tap.get("selector", "body") if last_tap else "body"
    last_inner = last_tap.get("inner_text", "") if last_tap else ""

    user_prompt = (
        f'User said: "{text}"\n'
        f'Last tapped element: selector="{last_selector}", text="{last_inner}"\n\n'
        'If the user is requesting a UI change or correction output:\n'
        '{"is_correction": true, "instruction": "<what to fix>", "selector": "<target CSS selector>"}\n'
        'Otherwise output:\n'
        '{"is_correction": false, "instruction": "", "selector": ""}'
    )

    try:
        from core.system.llm_adapter import call_llm
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        response = call_llm(messages, model="gemma4:31b-cloud")
        raw = response.get("content", "") if isinstance(response, dict) else str(response)
    except Exception as e:
        print(f"[TRACE] core.hermes.intent_classifier.classify_correction_intent: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"Intent classifier call failed: {e}. Treating as non-correction.")
        return None

    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        parsed = json.loads(match.group())
        if parsed.get("is_correction"):
            return {
                "selector": parsed.get("selector") or last_selector,
                "instruction": parsed.get("instruction") or text,
            }
        return None
    except Exception as e:
        print(f"[TRACE] core.hermes.intent_classifier.classify_correction_intent: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"Failed to parse intent classification response: {e}")
        return None

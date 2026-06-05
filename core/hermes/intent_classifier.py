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
        import ollama
        client = ollama.Client(host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"), timeout=10.0)
        response = client.chat(
            model="gemma4:31b-cloud",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            options={"temperature": 0.0},
        )
        raw = response["message"]["content"]
    except Exception as e:
        logger.warning(f"Intent classifier local Ollama call failed: {e}. Trying OpenAI fallback...")
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            try:
                from openai import OpenAI
                fallback_model = os.environ.get("JARVIS_OPENAI_MODEL", "gpt-4o-mini")
                client = OpenAI(api_key=openai_key)
                response = client.chat.completions.create(
                    model=fallback_model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0
                )
                raw = response.choices[0].message.content
            except Exception as oe:
                logger.warning(f"Intent classifier OpenAI fallback failed: {oe}. Treating as non-correction.")
                return None
        else:
            logger.warning(f"Intent classifier failed and no OPENAI_API_KEY available. Treating as non-correction.")
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
        logger.warning(f"Failed to parse intent classification response: {e}")
        return None

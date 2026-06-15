"""
Clarifier — detects CRITICAL ambiguity in a task before execution (Phase 28a).

Policy (user-approved): /jarvis is a one-shot non-interactive subprocess and the
shared rules mandate autonomy, so:
  - MINOR ambiguity -> make a reasonable assumption and PROCEED (logged elsewhere).
  - CRITICAL ambiguity (wrong interpretation => data loss / irreversible action /
    wrong target) -> return questions so the caller can emit NEEDS_INPUT and stop.

Fails OPEN: any LLM/parse error -> proceed (autonomy preserved).
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

AMBIGUITY_PROMPT = """Analyze this task for ambiguity before executing it.

Task: {task}

For each ambiguous element, decide:
- Is this ambiguity CRITICAL (wrong interpretation = wrong result, data loss,
  irreversible action, or acting on the wrong target/file/account)?
- Is this ambiguity MINOR (you can make a reasonable assumption and proceed)?

For CRITICAL ambiguities ONLY, generate either:
A) A multiple choice question with 2-4 concrete options
B) A yes/no question
C) A fill-in question if options cannot be enumerated

Never ask about minor ambiguities. Never ask more than 3 questions total.
If zero critical ambiguities exist, respond with exactly: PROCEED

Format each question as:
Q: <question text>
- <option 1>
- <option 2>
"""


def check_ambiguity(task: str) -> dict:
    """Return {"proceed": True} or {"proceed": False, "questions": [...]}.

    Each question: {"question": str, "options": [str, ...]}.
    """
    task = (task or "").strip()
    if not task:
        return {"proceed": True}

    if os.environ.get("JARVIS_CI") == "true":
        return {"proceed": True}

    try:
        from core.system.llm_adapter import call_llm
        from agents.model_router import get_model

        os.environ.setdefault("JARVIS_TEMPERATURE", "0.2")  # structured, deterministic
        result = call_llm(
            messages=[{"role": "user", "content": AMBIGUITY_PROMPT.format(task=task)}],
            model=get_model("orchestrator"),
        )
        raw = (result.get("content") if isinstance(result, dict) else str(result)) or ""
    except Exception as e:
        logger.warning(f"[clarifier] check failed, proceeding: {e}")
        return {"proceed": True}

    if "PROCEED" in raw.upper() and "Q:" not in raw:
        return {"proceed": True}

    questions = _parse_questions(raw)
    if not questions:
        # Couldn't extract structured questions -> fail open.
        return {"proceed": True}
    return {"proceed": False, "questions": questions[:3]}


def _parse_questions(raw: str) -> list[dict]:
    """Parse 'Q: ...' blocks with following '- option' bullet lines."""
    questions = []
    current = None
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^Q[:.)]\s*(.+)$", s, re.IGNORECASE)
        if m:
            if current:
                questions.append(current)
            current = {"question": m.group(1).strip(), "options": []}
        elif current is not None and re.match(r"^[-*•]\s+", s):
            current["options"].append(re.sub(r"^[-*•]\s+", "", s).strip())
    if current:
        questions.append(current)
    return questions
